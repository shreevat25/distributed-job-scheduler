"""Integration tests for cron/recurring job materialization."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.core.enums import ScheduleType
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob
from app.models.user import User
from app.services.schedule_service import materialize_due_schedules


@pytest.mark.asyncio
class TestCronScheduler:

    async def test_materialize_due_cron_schedule(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"cron-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10)
            session.add(queue)
            await session.flush()

            now = datetime.now(timezone.utc)
            past = now - timedelta(minutes=1)

            sched = ScheduledJob(
                queue_id=queue.id,
                name="test-cron",
                job_type="echo",
                payload={"msg": "cron"},
                schedule_type=ScheduleType.CRON,
                cron_expression="* * * * *",  # Every minute
                next_run_at=past,
                created_by=user.id,
            )
            session.add(sched)
            await session.commit()
            sched_id = sched.id
            queue_id = queue.id

        # Materialize
        async with (await independent_session_factory()) as session:
            count = await materialize_due_schedules(session)
            assert count == 1

        # Verify job was created
        async with (await independent_session_factory()) as session:
            stmt = select(Job).where(Job.queue_id == queue_id)
            jobs = (await session.execute(stmt)).scalars().all()
            assert len(jobs) == 1
            assert jobs[0].idempotency_key.startswith(f"cron-{sched_id}-")

            # Verify schedule updated
            stmt_sched = select(ScheduledJob).where(ScheduledJob.id == sched_id)
            s = (await session.execute(stmt_sched)).scalar_one()
            assert s.last_run_at == past
            assert s.next_run_at > now
            assert s.is_active is True

    async def test_materialize_one_time_schedule(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"one-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="proj")
            session.add(project)
            await session.flush()
            queue = Queue(project_id=project.id, name="q", concurrency_limit=10)
            session.add(queue)
            await session.flush()

            past = datetime.now(timezone.utc) - timedelta(minutes=1)

            sched = ScheduledJob(
                queue_id=queue.id,
                name="test-one-time",
                job_type="echo",
                payload={},
                schedule_type=ScheduleType.ONE_TIME,
                run_at=past,
                next_run_at=past,
                created_by=user.id,
            )
            session.add(sched)
            await session.commit()
            sched_id = sched.id

        async with (await independent_session_factory()) as session:
            count = await materialize_due_schedules(session)
            assert count == 1

        async with (await independent_session_factory()) as session:
            stmt_sched = select(ScheduledJob).where(ScheduledJob.id == sched_id)
            s = (await session.execute(stmt_sched)).scalar_one()
            assert s.is_active is False
            assert s.last_run_at == past
