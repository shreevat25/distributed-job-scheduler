"""Integration tests for job lifecycle transitions against real PostgreSQL."""

import uuid
import pytest
from sqlalchemy import select
from app.core.enums import JobStatus, WorkerStatus
from app.core.exceptions import InvalidTransitionError, OwnershipLostError
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.services import claim_service
from app.services import execution_service


@pytest.mark.asyncio
class TestJobLifecycle:
    """Verify complete queued -> claimed -> running -> completed execution_service."""

    async def test_complete_job_lifecycle(self, independent_session_factory):
        """Test full happy path execution lifecycle with attempt tracking."""
        async with (await independent_session_factory()) as session:
            user = User(email=f"life-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            project = Project(owner_id=user.id, name=f"life-proj-{uuid.uuid4().hex[:8]}")
            session.add(project)
            await session.flush()

            queue = Queue(project_id=project.id, name=f"life-q-{uuid.uuid4().hex[:8]}", concurrency_limit=10)
            session.add(queue)
            await session.flush()

            worker = Worker(name="life-worker", status=WorkerStatus.ONLINE, concurrency=5)
            session.add(worker)
            await session.flush()

            job = Job(
                queue_id=queue.id,
                type="echo",
                payload={"data": "hello"},
                status=JobStatus.QUEUED,
                max_attempts=3,
            )
            session.add(job)
            await session.commit()
            job_id = job.id
            worker_id = worker.id

        # 1. Claim job
        async with (await independent_session_factory()) as session:
            claimed = await claim_service.claim_jobs(session, queue.id, worker_id, 1, 30)
            assert len(claimed) == 1
            job = claimed[0]
            assert job.status == JobStatus.CLAIMED
            assert job.worker_id == worker_id
            claim_token = job.claim_token
            assert claim_token is not None
            await session.commit()

        # 2. Start execution
        async with (await independent_session_factory()) as session:
            job, execution = await execution_service.start_execution(session, job_id, worker_id, claim_token)
            await session.refresh(job)
            await session.refresh(execution)
            assert job.status == JobStatus.RUNNING
            assert job.attempt_count == 1
            assert execution.attempt_number == 1
            assert execution.status == "running"
            assert execution.started_at is not None
            await session.commit()

        # 3. Complete job
        async with (await independent_session_factory()) as session:
            result = {"echoed": {"data": "hello"}}
            job = await execution_service.complete_job(session, job_id, worker_id, claim_token, result)
            await session.refresh(job)
            assert job.status == JobStatus.COMPLETED
            assert job.completed_at is not None
            assert job.result == result
            await session.commit()

        # Verify durable execution record in DB
        async with (await independent_session_factory()) as session:
            stmt = select(JobExecution).where(JobExecution.job_id == job_id)
            execs = (await session.execute(stmt)).scalars().all()
            assert len(execs) == 1
            assert execs[0].attempt_number == 1
            assert execs[0].status == "completed"
            assert execs[0].result == result
            assert execs[0].duration_ms is not None

    async def test_wrong_token_cannot_complete(self, independent_session_factory):
        """A worker that lost ownership (wrong token) must not authoritatively complete a job."""
        async with (await independent_session_factory()) as session:
            user = User(email=f"life-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10)
            session.add(queue)
            await session.flush()
            worker = Worker(name="worker", status=WorkerStatus.ONLINE, concurrency=5)
            session.add(worker)
            await session.flush()
            job = Job(queue_id=queue.id, type="echo", payload={}, status=JobStatus.QUEUED, max_attempts=3)
            session.add(job)
            await session.commit()

            claimed = await claim_service.claim_jobs(session, queue.id, worker.id, 1, 30)
            await session.commit()
            job = claimed[0]
            await execution_service.start_execution(session, job.id, worker.id, job.claim_token)
            await session.commit()

            # Attempt complete with wrong token
            wrong_token = uuid.uuid4()
            with pytest.raises(OwnershipLostError):
                await execution_service.complete_job(session, job.id, worker.id, wrong_token, {"res": "ok"})
