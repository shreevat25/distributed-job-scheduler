"""Integration tests for job lease renewal and ownership enforcement."""

import uuid
import pytest
from sqlalchemy import select
from app.core.enums import JobStatus, WorkerStatus
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.services import claim_service
from app.worker import lifecycle


@pytest.mark.asyncio
class TestLeaseRenewal:
    """Verify lease renewal bound SQL and wrong worker/token rejection."""

    async def test_lease_renewal_and_wrong_token_rejection(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"lease-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
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
            job = Job(queue_id=queue.id, type="sleep", payload={"duration": 1}, status=JobStatus.QUEUED, max_attempts=3)
            session.add(job)
            await session.commit()
            job_id = job.id
            worker_id = worker.id

        # Claim job
        async with (await independent_session_factory()) as session:
            claimed = await claim_service.claim_jobs(session, queue.id, worker_id, 1, 30)
            await session.commit()
            job = claimed[0]
            claim_token = job.claim_token
            assert claim_token is not None

        # Renew with valid token -> returns True, increments lease_version
        async with (await independent_session_factory()) as session:
            renewed = await lifecycle.renew_lease(session, job_id, worker_id, claim_token, 60)
            assert renewed is True
            stmt = select(Job).where(Job.id == job_id)
            updated_job = (await session.execute(stmt)).scalar_one()
            assert updated_job.lease_version == 2  # 1 from claim, 2 from renew

        # Renew with wrong token -> returns False (ownership lost)
        async with (await independent_session_factory()) as session:
            wrong_token = uuid.uuid4()
            renewed = await lifecycle.renew_lease(session, job_id, worker_id, wrong_token, 60)
            assert renewed is False
