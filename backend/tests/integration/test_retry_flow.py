"""Integration tests for job failure and retry scheduling."""

import uuid
import pytest
from sqlalchemy import select
from app.core.enums import JobStatus, RetryStrategy, WorkerStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.project import Project
from app.models.queue import Queue
from app.models.retry_policy import RetryPolicy
from app.models.user import User
from app.models.worker import Worker
from app.services import claim_service
from app.worker import lifecycle


@pytest.mark.asyncio
class TestRetryFlow:
    """Verify job failure transitions to RETRY_WAIT with correct backoff delay."""

    async def test_job_failure_triggers_retry_wait(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"retry-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            policy = RetryPolicy(
                project_id=project.id,
                name="policy",
                strategy=RetryStrategy.FIXED,
                max_attempts=3,
                base_delay_seconds=60,
            )
            session.add(policy)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10, retry_policy_id=policy.id)
            session.add(queue)
            await session.flush()
            worker = Worker(name="worker", status=WorkerStatus.ONLINE, concurrency=5)
            session.add(worker)
            await session.flush()
            job = Job(queue_id=queue.id, type="fail", payload={"message": "boom"}, status=JobStatus.QUEUED, max_attempts=3)
            session.add(job)
            await session.commit()
            job_id = job.id
            worker_id = worker.id

        # Claim and start
        async with (await independent_session_factory()) as session:
            claimed = await claim_service.claim_jobs(session, queue.id, worker_id, 1, 30)
            await session.commit()
            job = claimed[0]
            await lifecycle.start_execution(session, job.id, worker_id, job.claim_token)
            await session.commit()

        # Fail job on attempt 1 (out of 3)
        async with (await independent_session_factory()) as session:
            exc = RuntimeError("Intentional boom")
            failed_job = await lifecycle.fail_job(session, job_id, worker_id, job.claim_token, exc)
            assert failed_job.status == JobStatus.RETRY_WAIT
            assert failed_job.worker_id is None
            assert failed_job.claim_token is None
            assert failed_job.claimed_at is None
            assert failed_job.last_error["message"] == "Intentional boom"
            await session.commit()

        # Verify durable execution row marked failed
        async with (await independent_session_factory()) as session:
            stmt = select(JobExecution).where(JobExecution.job_id == job_id)
            execs = (await session.execute(stmt)).scalars().all()
            assert len(execs) == 1
            assert execs[0].status == "failed"
            assert execs[0].error_message == "Intentional boom"
