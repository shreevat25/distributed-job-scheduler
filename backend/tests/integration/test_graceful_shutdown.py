"""Integration tests for worker graceful shutdown and draining behavior."""

import asyncio
import uuid
import pytest
from sqlalchemy import select, update
from app.core.enums import JobStatus, WorkerStatus
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.worker.runner import WorkerRunner


@pytest.mark.asyncio
class TestGracefulShutdown:
    """Verify that a draining worker stops claiming new work and transitions offline."""

    async def test_draining_worker_stops_claiming(self, independent_session_factory, test_engine):
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        worker_id = uuid.uuid4()
        runner = WorkerRunner(
            session_factory=session_maker,
            worker_id=worker_id,
            name="draining-test-worker",
            concurrency=5,
        )

        async with (await independent_session_factory()) as session:
            user = User(email=f"drain-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10, is_paused=True)
            session.add(queue)
            await session.flush()

            # Create 5 queued jobs
            jobs = [
                Job(queue_id=queue.id, type="sleep", payload={"duration": 0.1}, status=JobStatus.QUEUED, max_attempts=3)
                for _ in range(5)
            ]
            session.add_all(jobs)
            await session.commit()
            queue_id = queue.id

        # Start runner (queue is paused so it claims 0 jobs)
        runner_task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.1)

        # Trigger graceful shutdown
        await runner.shutdown()

        # Unpause queue while shutting down
        async with (await independent_session_factory()) as session:
            stmt = update(Queue).where(Queue.id == queue_id).values(is_paused=False)
            await session.execute(stmt)
            await session.commit()

        await asyncio.sleep(0.2)

        # Verify runner exited without claiming any jobs
        async with (await independent_session_factory()) as session:
            stmt = select(Job).where(Job.queue_id == queue_id, Job.status == JobStatus.CLAIMED)
            claimed = (await session.execute(stmt)).scalars().all()
            assert len(claimed) == 0

            # Verify worker marked OFFLINE after clean shutdown
            stmt_w = select(Worker).where(Worker.id == worker_id)
            w = (await session.execute(stmt_w)).scalar_one()
            assert w.status == WorkerStatus.OFFLINE
