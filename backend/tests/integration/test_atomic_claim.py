"""NON-NEGOTIABLE: Integration test for atomic job claiming.

Uses real PostgreSQL with independent database sessions to prove
that concurrent claim operations via SELECT FOR UPDATE SKIP LOCKED
never produce duplicate claims.

Does NOT mock PostgreSQL locking.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus, WorkerStatus
from app.core.security import hash_password
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.services import claim_service


class TestAtomicClaim:
    """Prove that concurrent claim operations never duplicate-claim a job."""

    async def test_concurrent_claims_no_duplicates(
        self, independent_session_factory
    ):
        """Setup jobs and workers, then race two independent claim operations.

        Assertions:
        - No duplicate job IDs across claim results
        - No job has two owners
        - Total claimed count is correct
        - Each claimed job has worker_id, claim_token, claimed_at,
          lease_expires_at, and incremented lease_version
        """
        # === SETUP ===
        async with (await independent_session_factory()) as setup_session:
            user = User(
                email=f"claim-test-{uuid.uuid4().hex[:8]}@test.com",
                password_hash=hash_password("testpass123"),
            )
            setup_session.add(user)
            await setup_session.flush()

            project = Project(
                owner_id=user.id,
                name=f"claim-project-{uuid.uuid4().hex[:8]}",
            )
            setup_session.add(project)
            await setup_session.flush()

            queue = Queue(
                project_id=project.id,
                name=f"claim-queue-{uuid.uuid4().hex[:8]}",
                concurrency_limit=20,  # High enough to not block claims
            )
            setup_session.add(queue)
            await setup_session.flush()
            queue_id = queue.id

            # Create two workers
            worker1 = Worker(
                name="claim-worker-1",
                status=WorkerStatus.ONLINE,
                concurrency=10,
            )
            worker2 = Worker(
                name="claim-worker-2",
                status=WorkerStatus.ONLINE,
                concurrency=10,
            )
            setup_session.add_all([worker1, worker2])
            await setup_session.flush()
            worker1_id = worker1.id
            worker2_id = worker2.id

            # Create 10 queued jobs
            for i in range(10):
                job = Job(
                    queue_id=queue_id,
                    type="claim.test",
                    payload={"index": i},
                    status=JobStatus.QUEUED,
                    priority=i,  # Varied priorities
                    max_attempts=3,
                )
                setup_session.add(job)

            await setup_session.commit()

        # === RACE: Concurrent claims from independent sessions ===
        async def claim_from_session(worker_id: uuid.UUID, limit: int):
            """Claim jobs using a completely independent session."""
            async with (await independent_session_factory()) as session:
                claimed = await claim_service.claim_jobs(
                    session,
                    queue_id=queue_id,
                    worker_id=worker_id,
                    requested_limit=limit,
                    lease_duration_seconds=30,
                )
                await session.commit()
                return [(j.id, j.worker_id, j.claim_token, j.claimed_at,
                         j.lease_expires_at, j.lease_version) for j in claimed]

        # Both workers try to claim 7 jobs each (but only 10 total exist)
        results = await asyncio.gather(
            claim_from_session(worker1_id, 7),
            claim_from_session(worker2_id, 7),
        )

        worker1_claimed = results[0]
        worker2_claimed = results[1]

        # === ASSERTIONS ===

        # 1. No duplicate job IDs
        all_job_ids = [jid for jid, *_ in worker1_claimed] + [
            jid for jid, *_ in worker2_claimed
        ]
        assert len(all_job_ids) == len(set(all_job_ids)), (
            f"DUPLICATE CLAIMS DETECTED! "
            f"Total: {len(all_job_ids)}, Unique: {len(set(all_job_ids))}"
        )

        # 2. Total claimed is correct (at most 10, sum of both)
        total_claimed = len(worker1_claimed) + len(worker2_claimed)
        assert total_claimed == 10, f"Expected 10 total claimed, got {total_claimed}"

        # 3. Each claimed job has required fields
        for job_id, worker_id, claim_token, claimed_at, lease_expires_at, lease_version in (
            worker1_claimed + worker2_claimed
        ):
            assert worker_id is not None, f"Job {job_id} has no worker_id"
            assert claim_token is not None, f"Job {job_id} has no claim_token"
            assert claimed_at is not None, f"Job {job_id} has no claimed_at"
            assert lease_expires_at is not None, f"Job {job_id} has no lease_expires_at"
            assert lease_version >= 1, f"Job {job_id} has lease_version {lease_version}, expected >= 1"

        # 4. Verify in database: no job has two owners
        async with (await independent_session_factory()) as verify_session:
            stmt = select(Job).where(Job.queue_id == queue_id, Job.status == JobStatus.CLAIMED)
            result = await verify_session.execute(stmt)
            claimed_jobs = list(result.scalars().all())

            assert len(claimed_jobs) == 10

            # Each job should have exactly one worker
            for job in claimed_jobs:
                assert job.worker_id in (worker1_id, worker2_id)

            # Count per worker
            w1_count = sum(1 for j in claimed_jobs if j.worker_id == worker1_id)
            w2_count = sum(1 for j in claimed_jobs if j.worker_id == worker2_id)
            assert w1_count + w2_count == 10, f"w1={w1_count}, w2={w2_count}"

    async def test_claim_only_queued_jobs(
        self, independent_session_factory
    ):
        """Only jobs with status=queued and available_at <= NOW() are claimed."""
        async with (await independent_session_factory()) as setup_session:
            user = User(
                email=f"claim-filter-{uuid.uuid4().hex[:8]}@test.com",
                password_hash=hash_password("testpass123"),
            )
            setup_session.add(user)
            await setup_session.flush()

            project = Project(
                owner_id=user.id,
                name=f"filter-project-{uuid.uuid4().hex[:8]}",
            )
            setup_session.add(project)
            await setup_session.flush()

            queue = Queue(
                project_id=project.id,
                name=f"filter-queue-{uuid.uuid4().hex[:8]}",
                concurrency_limit=20,
            )
            setup_session.add(queue)
            await setup_session.flush()
            queue_id = queue.id

            worker = Worker(
                name="filter-worker",
                status=WorkerStatus.ONLINE,
                concurrency=10,
            )
            setup_session.add(worker)
            await setup_session.flush()
            worker_id = worker.id

            # Create 3 queued + 2 scheduled (future available_at)
            from datetime import datetime, timedelta, UTC

            for i in range(3):
                job = Job(
                    queue_id=queue_id,
                    type="eligible",
                    payload={"i": i},
                    status=JobStatus.QUEUED,
                    max_attempts=3,
                )
                setup_session.add(job)

            for i in range(2):
                job = Job(
                    queue_id=queue_id,
                    type="not-eligible",
                    payload={"i": i},
                    status=JobStatus.SCHEDULED,
                    available_at=datetime.now(UTC) + timedelta(hours=1),
                    max_attempts=3,
                )
                setup_session.add(job)

            await setup_session.commit()

        # Claim
        async with (await independent_session_factory()) as claim_session:
            claimed = await claim_service.claim_jobs(
                claim_session,
                queue_id=queue_id,
                worker_id=worker_id,
                requested_limit=10,
                lease_duration_seconds=30,
            )
            await claim_session.commit()

        # Only 3 eligible jobs should be claimed
        assert len(claimed) == 3
        for job in claimed:
            assert job.type == "eligible"
