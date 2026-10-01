"""Integration tests for delayed and retried job promotion."""

import uuid
import pytest
from sqlalchemy import select, text
from app.core.enums import JobStatus
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.services.schedule_service import promote_due_jobs


@pytest.mark.asyncio
class TestDelayedPromotion:
    """Verify promotion scheduler promotes only due jobs (scheduled/retry_wait -> queued)."""

    async def test_promote_due_jobs(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"promo-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10)
            session.add(queue)
            await session.flush()

            # Job 1: due scheduled job (available_at in past)
            job_due = Job(
                queue_id=queue.id,
                type="echo",
                payload={},
                status=JobStatus.SCHEDULED,
                available_at=text("NOW() - INTERVAL '10 seconds'"),
                max_attempts=3,
            )
            # Job 2: future scheduled job (not due yet)
            job_future = Job(
                queue_id=queue.id,
                type="echo",
                payload={},
                status=JobStatus.SCHEDULED,
                available_at=text("NOW() + INTERVAL '1 hour'"),
                max_attempts=3,
            )
            # Job 3: due retry_wait job
            job_retry_due = Job(
                queue_id=queue.id,
                type="echo",
                payload={},
                status=JobStatus.RETRY_WAIT,
                available_at=text("NOW() - INTERVAL '5 seconds'"),
                max_attempts=3,
            )
            session.add_all([job_due, job_future, job_retry_due])
            await session.commit()
            id_due = job_due.id
            id_future = job_future.id
            id_retry = job_retry_due.id

        # Run promotion
        async with (await independent_session_factory()) as session:
            count = await promote_due_jobs(session)
            assert count >= 2

        # Verify only due jobs were promoted to QUEUED
        async with (await independent_session_factory()) as session:
            stmt = select(Job).where(Job.id.in_([id_due, id_future, id_retry]))
            jobs = {j.id: j for j in (await session.execute(stmt)).scalars().all()}
            assert jobs[id_due].status == JobStatus.QUEUED
            assert jobs[id_retry].status == JobStatus.QUEUED
            assert jobs[id_future].status == JobStatus.SCHEDULED
