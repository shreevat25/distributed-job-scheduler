"""Integration test for queue concurrency limit under concurrent claim races.

Uses real PostgreSQL with independent sessions to prove that the
queue's concurrency_limit is never exceeded, even when multiple
workers race to claim jobs simultaneously.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus, WorkerStatus
from app.core.security import hash_password
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.services import claim_service


class TestQueueConcurrencyLimit:
    """Prove that queue concurrency limits are enforced under contention."""

    async def test_concurrency_limit_enforced_under_race(
        self, independent_session_factory
    ):
        """Queue concurrency_limit=2, 10 jobs, multiple concurrent claim races.

        Assert:
        - Total active (claimed + running) jobs never exceeds 2
        - Only 2 jobs are claimed initially
        - After one active job leaves active state, a new slot opens
        """
        # === SETUP ===
        async with (await independent_session_factory()) as setup_session:
            user = User(
                email=f"conc-test-{uuid.uuid4().hex[:8]}@test.com",
                password_hash=hash_password("testpass123"),
            )
            setup_session.add(user)
            await setup_session.flush()

            project = Project(
                owner_id=user.id,
                name=f"conc-project-{uuid.uuid4().hex[:8]}",
            )
            setup_session.add(project)
            await setup_session.flush()

            # STRICT concurrency limit of 2
            queue = Queue(
                project_id=project.id,
                name=f"conc-queue-{uuid.uuid4().hex[:8]}",
                concurrency_limit=2,
            )
            setup_session.add(queue)
            await setup_session.flush()
            queue_id = queue.id

            # Create 3 workers
            workers = []
            for i in range(3):
                w = Worker(
                    name=f"conc-worker-{i}",
                    status=WorkerStatus.ONLINE,
                    concurrency=5,
                )
                setup_session.add(w)
                workers.append(w)
            await setup_session.flush()
            worker_ids = [w.id for w in workers]

            # Create 10 queued jobs
            for i in range(10):
                job = Job(
                    queue_id=queue_id,
                    type="concurrency.test",
                    payload={"index": i},
                    status=JobStatus.QUEUED,
                    max_attempts=3,
                )
                setup_session.add(job)

            await setup_session.commit()

        # === RACE: 3 workers try to claim 5 each simultaneously ===
        async def claim_from_worker(worker_id: uuid.UUID):
            async with (await independent_session_factory()) as session:
                claimed = await claim_service.claim_jobs(
                    session,
                    queue_id=queue_id,
                    worker_id=worker_id,
                    requested_limit=5,
                    lease_duration_seconds=30,
                )
                await session.commit()
                return [j.id for j in claimed]

        results = await asyncio.gather(
            *[claim_from_worker(wid) for wid in worker_ids]
        )

        # === ASSERTION 1: Total claimed <= concurrency_limit ===
        all_claimed = []
        for r in results:
            all_claimed.extend(r)

        # No duplicates
        assert len(all_claimed) == len(set(all_claimed)), "Duplicate claims detected!"

        # Total claimed must be exactly 2 (concurrency_limit)
        assert len(all_claimed) == 2, (
            f"Expected exactly 2 claimed (concurrency_limit=2), "
            f"got {len(all_claimed)}: {[len(r) for r in results]}"
        )

        # === ASSERTION 2: Verify DB state ===
        async with (await independent_session_factory()) as verify_session:
            active_count_stmt = (
                select(func.count())
                .select_from(Job)
                .where(
                    Job.queue_id == queue_id,
                    Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
                )
            )
            result = await verify_session.execute(active_count_stmt)
            active_count = result.scalar_one()
            assert active_count == 2, f"Active count should be 2, got {active_count}"

        # === SIMULATE: One job completes (leaves active state) ===
        async with (await independent_session_factory()) as update_session:
            job_to_complete = all_claimed[0]
            stmt = (
                update(Job)
                .where(Job.id == job_to_complete)
                .values(status=JobStatus.COMPLETED)
            )
            await update_session.execute(stmt)
            await update_session.commit()

        # === CLAIM AGAIN: One new slot should be available ===
        async with (await independent_session_factory()) as reclaim_session:
            new_claimed = await claim_service.claim_jobs(
                reclaim_session,
                queue_id=queue_id,
                worker_id=worker_ids[0],
                requested_limit=5,
                lease_duration_seconds=30,
            )
            await reclaim_session.commit()

        # Exactly 1 new job should be claimed (filling the freed slot)
        assert len(new_claimed) == 1, (
            f"Expected 1 new claim after freeing a slot, got {len(new_claimed)}"
        )

        # === FINAL VERIFICATION: Active count is back to 2 ===
        async with (await independent_session_factory()) as final_session:
            result = await final_session.execute(active_count_stmt)
            final_active = result.scalar_one()
            assert final_active == 2, f"Final active count should be 2, got {final_active}"

    async def test_zero_slots_returns_empty(
        self, independent_session_factory
    ):
        """When concurrency limit is fully used, claim returns empty list."""
        async with (await independent_session_factory()) as setup_session:
            user = User(
                email=f"zero-test-{uuid.uuid4().hex[:8]}@test.com",
                password_hash=hash_password("testpass123"),
            )
            setup_session.add(user)
            await setup_session.flush()

            project = Project(
                owner_id=user.id,
                name=f"zero-project-{uuid.uuid4().hex[:8]}",
            )
            setup_session.add(project)
            await setup_session.flush()

            queue = Queue(
                project_id=project.id,
                name=f"zero-queue-{uuid.uuid4().hex[:8]}",
                concurrency_limit=1,
            )
            setup_session.add(queue)
            await setup_session.flush()
            queue_id = queue.id

            worker = Worker(
                name="zero-worker",
                status=WorkerStatus.ONLINE,
                concurrency=5,
            )
            setup_session.add(worker)
            await setup_session.flush()
            worker_id = worker.id

            # Create 1 already-claimed job (filling the slot)
            from datetime import datetime, timedelta, UTC

            job = Job(
                queue_id=queue_id,
                type="blocker",
                payload={},
                status=JobStatus.CLAIMED,
                max_attempts=3,
                worker_id=worker_id,
                claimed_at=datetime.now(UTC),
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
            )
            setup_session.add(job)

            # Create 1 eligible queued job
            queued_job = Job(
                queue_id=queue_id,
                type="waiting",
                payload={},
                status=JobStatus.QUEUED,
                max_attempts=3,
            )
            setup_session.add(queued_job)
            await setup_session.commit()

        # Claim: should return empty because concurrency_limit=1 is full
        async with (await independent_session_factory()) as claim_session:
            claimed = await claim_service.claim_jobs(
                claim_session,
                queue_id=queue_id,
                worker_id=worker_id,
                requested_limit=5,
                lease_duration_seconds=30,
            )
            await claim_session.commit()

        assert len(claimed) == 0
