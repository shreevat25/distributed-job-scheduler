"""Integration tests for dead-letter queue (DLQ) transitions and manual retry."""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.core.enums import JobStatus, WorkerStatus
from app.main import app
from app.models.dlq_entry import DLQEntry
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.services import claim_service
from app.worker import lifecycle


@pytest.mark.asyncio
class TestDLQFlow:
    """Verify exhausted attempts dead-lettering and history-preserving manual retry."""

    async def test_dlq_creation_and_manual_retry(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"dlq-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
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
            # Job with max_attempts=1 so 1st failure dead-letters it
            job = Job(queue_id=queue.id, type="fail", payload={}, status=JobStatus.QUEUED, max_attempts=1)
            session.add(job)
            await session.commit()
            job_id = job.id
            worker_id = worker.id
            user_id = user.id

        # Claim and start
        async with (await independent_session_factory()) as session:
            claimed = await claim_service.claim_jobs(session, queue.id, worker_id, 1, 30)
            await session.commit()
            job = claimed[0]
            await lifecycle.start_execution(session, job.id, worker_id, job.claim_token)
            await session.commit()

        # Fail job -> attempt 1 == max_attempts 1 -> DEAD_LETTERED
        async with (await independent_session_factory()) as session:
            exc = RuntimeError("Fatal error")
            failed_job = await lifecycle.fail_job(session, job_id, worker_id, job.claim_token, exc)
            await session.commit()
            assert failed_job.status == JobStatus.DEAD_LETTERED

        # Verify exactly one DLQ entry in DB
        async with (await independent_session_factory()) as session:
            stmt = select(DLQEntry).where(DLQEntry.job_id == job_id)
            dlq_entries = (await session.execute(stmt)).scalars().all()
            assert len(dlq_entries) == 1
            dlq_entry = dlq_entries[0]
            assert dlq_entry.attempts == 1
            assert "Fatal error" in dlq_entry.reason
            dlq_id = dlq_entry.id

        # Verify JobExecution preserved
        async with (await independent_session_factory()) as session:
            stmt = select(JobExecution).where(JobExecution.job_id == job_id)
            execs = (await session.execute(stmt)).scalars().all()
            assert len(execs) == 1
            assert execs[0].status == "failed"

        # Perform manual retry via API endpoint
        async with (await independent_session_factory()) as session:
            from app.core.security import create_access_token
            token = create_access_token(str(user_id))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/v1/dlq/{dlq_id}/retry", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["retried_at"] is not None

        # Verify job is requeued and attempt_count reset to 0, history preserved
        async with (await independent_session_factory()) as session:
            stmt = select(Job).where(Job.id == job_id)
            job = (await session.execute(stmt)).scalar_one()
            assert job.status == JobStatus.QUEUED
            assert job.attempt_count == 0

            stmt_exec = select(JobExecution).where(JobExecution.job_id == job_id)
            execs_after = (await session.execute(stmt_exec)).scalars().all()
            assert len(execs_after) == 1  # Historical execution preserved!
