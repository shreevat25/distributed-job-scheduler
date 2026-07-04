import asyncio
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select, text
from app.core.enums import ScheduleType
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob
from app.models.user import User
from app.worker.scheduler import materialize_due_schedules

@pytest.mark.asyncio
class TestCronExtra:

    async def test_concurrent_materialization_deduplication(self, independent_session_factory):
        async with (await independent_session_factory()) as session:
            user = User(email=f"cron-dedup-{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
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
                name="test-cron-concurrent",
                job_type="echo",
                payload={},
                schedule_type=ScheduleType.CRON,
                cron_expression="* * * * *",
                next_run_at=past,
                created_by=user.id,
            )
            session.add(sched)
            await session.commit()
            queue_id = queue.id
            
        # Run two materializations concurrently
        async def run_mat():
            async with (await independent_session_factory()) as session:
                return await materialize_due_schedules(session)
                
        results = await asyncio.gather(run_mat(), run_mat())
        
        # Total jobs created should be 1
        assert sum(results) == 1

        async with (await independent_session_factory()) as session:
            stmt = select(Job).where(Job.queue_id == queue_id)
            jobs = (await session.execute(stmt)).scalars().all()
            assert len(jobs) == 1
