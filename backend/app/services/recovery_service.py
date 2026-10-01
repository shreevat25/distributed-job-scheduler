"""Recovery service — crash detection and expired-lease recovery.

Used by the reaper process. Both operations lock candidate rows with
SELECT ... FOR UPDATE SKIP LOCKED so that any number of reaper replicas can
run concurrently without double-recovering the same worker or job.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import JobStatus, LogLevel, WorkerStatus
from app.core.logging import get_logger
from app.models.job import Job
from app.repositories import execution_repository, job_log_repository, job_repository, worker_repository
from app.repositories.expressions import db_now
from app.services import retry_service

logger = get_logger(__name__)

WORKER_LOST_ERROR = "WorkerLostError"
WORKER_LOST_MESSAGE = "Worker running this execution lost lease or crashed"


async def reap_stale_workers(
    session: AsyncSession,
    threshold_seconds: int | None = None,
) -> int:
    """Mark ONLINE workers whose last_seen_at exceeded the stale threshold as DEAD.

    Commits and returns the number of workers marked dead.
    """
    if threshold_seconds is None:
        threshold_seconds = settings.WORKER_STALE_THRESHOLD_SECONDS

    stale_workers = await worker_repository.lock_stale_online_workers(session, threshold_seconds)
    if not stale_workers:
        return 0

    for w in stale_workers:
        logger.warning("worker_marked_dead", worker_name=w.name, worker_id=str(w.id))
        w.status = WorkerStatus.DEAD
        w.stopped_at = db_now()

    await session.commit()
    return len(stale_workers)


async def _requeue_unstarted(session: AsyncSession, job: Job) -> None:
    """A claimed job that never started is requeued without consuming an attempt."""
    job.status = JobStatus.QUEUED
    job_repository.release_claim(job)
    job_log_repository.add_log(
        session,
        job.id,
        LogLevel.WARNING,
        "Recovered claimed job with expired lease. Requeued without consuming attempt.",
    )


async def _recover_interrupted(session: AsyncSession, job: Job) -> None:
    """A running job whose lease expired is failed with WorkerLostError, then retried or dead-lettered."""
    execution = await execution_repository.get_attempt_for_update(
        session, job.id, job.attempt_count, running_only=True
    )
    execution_id = None
    if execution:
        execution_repository.mark_finished(
            execution,
            "interrupted",
            error_type=WORKER_LOST_ERROR,
            error_message=WORKER_LOST_MESSAGE,
        )
        execution_id = execution.id

    job.last_error = {
        "type": WORKER_LOST_ERROR,
        "message": WORKER_LOST_MESSAGE,
        "attempt": job.attempt_count,
    }
    attempt = job.attempt_count

    await retry_service.retry_or_dead_letter(
        session,
        job,
        execution_id=execution_id,
        retry_log=lambda delay: (
            f"Job interrupted on attempt {attempt} ({WORKER_LOST_ERROR}). Scheduling retry in {delay}s."
        ),
        dead_letter_reason=f"Exhausted {job.max_attempts} attempts. Last error: {WORKER_LOST_ERROR}",
        dead_letter_log=f"Job dead-lettered after {WORKER_LOST_ERROR} on attempt {attempt}.",
    )


async def reap_expired_jobs(session: AsyncSession, limit: int = 100) -> int:
    """Recover jobs whose lease_expires_at <= NOW().

    For claimed jobs with no started execution: requeue without consuming attempt.
    For running interrupted jobs: finalize execution with WorkerLostError, then retry or DLQ.

    Commits and returns the number of jobs recovered.
    """
    expired_jobs = await job_repository.lock_expired_leases(session, limit)
    if not expired_jobs:
        return 0

    for job in expired_jobs:
        logger.warning(
            "recovering_expired_job",
            job_id=str(job.id),
            status=job.status.value,
            attempt=job.attempt_count,
        )
        if job.status == JobStatus.CLAIMED:
            await _requeue_unstarted(session, job)
        elif job.status == JobStatus.RUNNING:
            await _recover_interrupted(session, job)

    await session.commit()
    logger.info("expired_jobs_recovered", count=len(expired_jobs))
    return len(expired_jobs)
