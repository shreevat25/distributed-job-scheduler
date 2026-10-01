"""Integration tests for worker crash detection and expired lease recovery."""

import uuid
import pytest
from sqlalchemy import select, text
from app.core.enums import JobStatus, WorkerStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.services.recovery_service import reap_expired_jobs, reap_stale_workers


@pytest.mark.asyncio
class TestWorkerCrash:
    """Verify stale worker detection and crashed running job lease recovery."""

    async def test_recover_crashed_running_job(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"crash-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10)
            session.add(queue)
            await session.flush()
            worker = Worker(
                name="crashed-worker",
                status=WorkerStatus.ONLINE,
                concurrency=5,
                last_seen_at=text("NOW() - INTERVAL '60 seconds'"),
            )
            session.add(worker)
            await session.flush()

            # Create a running job whose lease expired 10 seconds ago
            job = Job(
                queue_id=queue.id,
                type="sleep",
                payload={"duration": 10},
                status=JobStatus.RUNNING,
                attempt_count=1,
                max_attempts=3,
                worker_id=worker.id,
                claim_token=uuid.uuid4(),
                lease_expires_at=text("NOW() - INTERVAL '10 seconds'"),
                started_at=text("NOW() - INTERVAL '40 seconds'"),
            )
            session.add(job)
            await session.flush()

            # Create running execution record
            exec_record = JobExecution(
                job_id=job.id,
                attempt_number=1,
                worker_id=worker.id,
                claim_token=job.claim_token,
                status="running",
                started_at=text("NOW() - INTERVAL '40 seconds'"),
            )
            session.add(exec_record)
            await session.commit()
            job_id = job.id
            worker_id = worker.id
            exec_id = exec_record.id

        # 1. Reap stale workers
        async with (await independent_session_factory()) as session:
            stale_count = await reap_stale_workers(session)
            assert stale_count >= 1

        # Verify worker marked DEAD
        async with (await independent_session_factory()) as session:
            stmt = select(Worker).where(Worker.id == worker_id)
            w = (await session.execute(stmt)).scalar_one()
            assert w.status == WorkerStatus.DEAD

        # 2. Reap expired jobs
        async with (await independent_session_factory()) as session:
            job_count = await reap_expired_jobs(session)
            assert job_count >= 1

        # Verify execution finalized as interrupted with WorkerLostError and job routed to RETRY_WAIT
        async with (await independent_session_factory()) as session:
            stmt_job = select(Job).where(Job.id == job_id)
            j = (await session.execute(stmt_job)).scalar_one()
            assert j.status == JobStatus.RETRY_WAIT
            assert j.worker_id is None
            assert j.claim_token is None
            assert j.last_error["type"] == "WorkerLostError"

            stmt_exec = select(JobExecution).where(JobExecution.id == exec_id)
            e = (await session.execute(stmt_exec)).scalar_one()
            assert e.status == "interrupted"
            assert e.error_type == "WorkerLostError"
            assert e.finished_at is not None
