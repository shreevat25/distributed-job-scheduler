"""Integration tests for concurrent reaper race conditions against real PostgreSQL."""

import asyncio
import uuid
import pytest
from sqlalchemy import text
from app.core.enums import JobStatus, WorkerStatus
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.services.recovery_service import reap_expired_jobs


@pytest.mark.asyncio
class TestReaperRace:
    """Verify that concurrent reapers using SELECT FOR UPDATE SKIP LOCKED never double-recover."""

    async def test_concurrent_reaper_race_no_double_recovery(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"reaper-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10)
            session.add(queue)
            await session.flush()
            worker = Worker(name="w", status=WorkerStatus.ONLINE, concurrency=5)
            session.add(worker)
            await session.flush()

            # Ensure the database is clean of any expired jobs left by other tests
            await session.execute(text("DELETE FROM jobs"))
            await session.flush()

            # Create 10 expired claimed jobs
            jobs = [
                Job(
                    queue_id=queue.id,
                    type="echo",
                    payload={},
                    status=JobStatus.CLAIMED,
                    worker_id=worker.id,
                    claim_token=uuid.uuid4(),
                    lease_expires_at=text("NOW() - INTERVAL '10 seconds'"),
                    max_attempts=3,
                )
                for _ in range(10)
            ]
            session.add_all(jobs)
            await session.commit()

        # Race two concurrent reapers with independent sessions
        barrier = asyncio.Barrier(2)

        async def reaper_task():
            async with (await independent_session_factory()) as s:
                await barrier.wait()
                return await reap_expired_jobs(s, limit=10)

        res1, res2 = await asyncio.gather(reaper_task(), reaper_task())

        # Total recovered across both reapers must be exactly 10, without double recovery
        assert res1 + res2 == 10
