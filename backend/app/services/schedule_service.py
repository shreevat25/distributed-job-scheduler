"""Schedule service — cron math, delayed-job promotion, and schedule materialization.

``promote_due_jobs`` and ``materialize_due_schedules`` are driven by the
scheduler process. Both lock candidate rows with SKIP LOCKED so multiple
scheduler replicas never double-promote or double-fire.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import croniter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus, ScheduleType
from app.core.logging import get_logger
from app.models.job import Job
from app.models.scheduled_job import ScheduledJob
from app.repositories import job_repository, schedule_repository

logger = get_logger(__name__)


def next_cron_run(cron_expression: str, tz_name: str, after: datetime) -> datetime:
    """Next cron occurrence strictly after ``after``, evaluated in ``tz_name``, returned in UTC.

    Raises:
        Exception: If the cron expression or timezone is invalid.
    """
    tz = ZoneInfo(tz_name)
    next_local = croniter.croniter(cron_expression, after.astimezone(tz)).get_next(datetime)
    return next_local.astimezone(timezone.utc)


def is_valid_cron(cron_expression: str | None) -> bool:
    """Whether a cron expression is present and syntactically valid."""
    return bool(cron_expression) and croniter.croniter.is_valid(cron_expression)


def advance_next_run_if_past(schedule: ScheduledJob, now: datetime) -> None:
    """When resuming a cron schedule, skip occurrences missed while paused.

    Recalculates next_run_at from ``now`` if it is in the past, to avoid an
    immediate burst of catch-up runs.
    """
    if schedule.schedule_type == ScheduleType.CRON and schedule.next_run_at < now:
        schedule.next_run_at = next_cron_run(schedule.cron_expression, schedule.timezone, now)


async def promote_due_jobs(session: AsyncSession, limit: int = 100) -> int:
    """Promote scheduled and retry_wait jobs whose available_at <= NOW() to queued.

    Commits and returns the number of jobs promoted.
    """
    jobs = await job_repository.lock_due_for_promotion(session, limit)
    if not jobs:
        return 0

    for job in jobs:
        job.status = JobStatus.QUEUED

    await session.commit()
    logger.info("due_jobs_promoted", count=len(jobs))
    return len(jobs)


async def materialize_due_schedules(session: AsyncSession, limit: int = 100) -> int:
    """Materialize due schedules into concrete jobs.

    Each occurrence gets a deterministic idempotency key derived from the
    schedule ID and the occurrence timestamp, so a replayed occurrence can
    never create a duplicate job. Commits and returns the number of jobs
    created.
    """
    db_now = await schedule_repository.current_db_time(session)

    schedules = await schedule_repository.lock_due_schedules(session, limit)
    if not schedules:
        return 0

    for sched in schedules:
        idempotency_key = f"cron-{sched.id}-{int(sched.next_run_at.timestamp())}"
        session.add(
            Job(
                queue_id=sched.queue_id,
                type=sched.job_type,
                payload=sched.payload,
                status=JobStatus.QUEUED,
                idempotency_key=idempotency_key,
                max_attempts=3,
            )
        )

        sched.last_run_at = sched.next_run_at

        if sched.schedule_type == ScheduleType.CRON:
            try:
                next_run = next_cron_run(sched.cron_expression, sched.timezone, sched.next_run_at)
                # If we missed many occurrences, catch up to DB now
                if next_run < db_now:
                    next_run = next_cron_run(sched.cron_expression, sched.timezone, db_now)
                sched.next_run_at = next_run
            except Exception as exc:
                logger.error("schedule_cron_invalid", schedule_id=str(sched.id), error=str(exc))
                sched.is_active = False
        else:
            sched.is_active = False

    await session.commit()
    logger.info("schedules_materialized", count=len(schedules))
    return len(schedules)
