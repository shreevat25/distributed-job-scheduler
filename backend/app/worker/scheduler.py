"""Promotion scheduler for delayed and retried jobs."""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import JobStatus
from app.models.job import Job

logger = logging.getLogger(__name__)


async def promote_due_jobs(session: AsyncSession, limit: int = 100) -> int:
    """Promote scheduled and retry_wait jobs whose available_at <= NOW() to queued.

    Uses SELECT FOR UPDATE SKIP LOCKED to prevent multiple concurrent scheduler
    processes from double-promoting the same jobs.
    """
    stmt = (
        select(Job)
        .where(
            Job.status.in_([JobStatus.SCHEDULED, JobStatus.RETRY_WAIT]),
            Job.available_at <= text("NOW()"),
        )
        .order_by(Job.available_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    jobs = (await session.execute(stmt)).scalars().all()
    if not jobs:
        return 0

    count = 0
    for job in jobs:
        job.status = JobStatus.QUEUED
        count += 1

    await session.commit()
    if count > 0:
        logger.info("Promoted %d due jobs (scheduled/retry_wait -> queued)", count)
    return count


from datetime import datetime, timezone
import croniter
from zoneinfo import ZoneInfo
from app.core.enums import ScheduleType
from app.models.scheduled_job import ScheduledJob

async def materialize_due_schedules(session: AsyncSession, limit: int = 100) -> int:
    """Materialize due schedules into actual jobs."""
    # Get authoritative DB time
    db_now_result = await session.execute(text("SELECT CURRENT_TIMESTAMP"))
    db_now = db_now_result.scalar_one()

    stmt = (
        select(ScheduledJob)
        .where(
            ScheduledJob.is_active == True,
            ScheduledJob.next_run_at <= text("NOW()"),
        )
        .order_by(ScheduledJob.next_run_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    schedules = (await session.execute(stmt)).scalars().all()
    if not schedules:
        return 0

    count = 0
    for sched in schedules:
        # Deterministic identity based on schedule ID and expected occurrence timestamp
        idempotency_key = f"cron-{sched.id}-{int(sched.next_run_at.timestamp())}"
        job = Job(
            queue_id=sched.queue_id,
            type=sched.job_type,
            payload=sched.payload,
            status=JobStatus.QUEUED,
            idempotency_key=idempotency_key,
            max_attempts=3,
        )
        session.add(job)
        count += 1
        
        sched.last_run_at = sched.next_run_at
        
        # Calculate next_run_at
        if sched.schedule_type == ScheduleType.CRON:
            try:
                tz = ZoneInfo(sched.timezone)
                # Convert the UTC stored timestamp to the schedule's timezone for cron calculation
                base_time = sched.next_run_at.astimezone(tz)
                next_dt = croniter.croniter(sched.cron_expression, base_time).get_next(datetime)
                
                # If we missed many occurrences, catch up to DB now
                if next_dt < db_now:
                    next_dt = croniter.croniter(sched.cron_expression, db_now.astimezone(tz)).get_next(datetime)
                
                # Convert back to UTC for storage
                sched.next_run_at = next_dt.astimezone(timezone.utc)
            except Exception as exc:
                logger.error("Failed to parse cron for schedule %s: %s", sched.id, exc)
                sched.is_active = False
        else:
            sched.is_active = False

    await session.commit()
    if count > 0:
        logger.info("Materialized %d due schedules", count)
    return count


class PromotionScheduler:
    """Background scheduler loop for promoting delayed and retried jobs, and materializing schedules."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 1.0,
        batch_limit: int = 100,
    ) -> None:
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.batch_limit = batch_limit
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the promotion loop."""
        self.is_running = True
        logger.info("Starting promotion scheduler loop (interval=%.2fs)...", self.interval_seconds)
        try:
            while self.is_running:
                try:
                    async with self.session_factory() as session:
                        await promote_due_jobs(session, limit=self.batch_limit)
                    async with self.session_factory() as session:
                        await materialize_due_schedules(session, limit=self.batch_limit)
                except Exception as exc:
                    logger.error("Error in promotion scheduler loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval_seconds)
        finally:
            logger.info("Promotion scheduler stopped.")

    def stop(self) -> None:
        """Stop the promotion loop."""
        self.is_running = False
