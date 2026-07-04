"""Reaper service for detecting stale workers and recovering expired job leases."""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.enums import JobStatus, LogLevel, WorkerStatus
from app.models.dlq_entry import DLQEntry
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.queue import Queue
from app.models.worker import Worker
from app.services.retry_service import calculate_retry_delay

logger = logging.getLogger(__name__)


async def reap_stale_workers(session: AsyncSession) -> int:
    """Detect online workers whose last_seen_at exceeded stale threshold and mark them DEAD."""
    stmt = (
        select(Worker)
        .where(
            Worker.status == WorkerStatus.ONLINE,
            Worker.last_seen_at < text("NOW() - (:threshold * INTERVAL '1 second')").bindparams(
                threshold=settings.WORKER_STALE_THRESHOLD_SECONDS
            ),
        )
        .with_for_update(skip_locked=True)
    )
    stale_workers = (await session.execute(stmt)).scalars().all()
    if not stale_workers:
        return 0

    count = 0
    for w in stale_workers:
        logger.warning("Worker %s (%s) is stale. Marking status as DEAD.", w.name, w.id)
        w.status = WorkerStatus.DEAD
        w.stopped_at = text("NOW()")
        count += 1

    await session.commit()
    return count


async def reap_expired_jobs(session: AsyncSession, limit: int = 100) -> int:
    """Recover jobs whose lease_expires_at <= NOW().

    For claimed jobs with no started execution: requeue without consuming attempt.
    For running interrupted jobs: finalize execution with WorkerLostError, then retry or DLQ.
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent concurrent reapers from double-recovering.
    """
    stmt = (
        select(Job)
        .where(
            Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
            Job.lease_expires_at <= text("NOW()"),
        )
        .order_by(Job.lease_expires_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    expired_jobs = (await session.execute(stmt)).scalars().all()
    if not expired_jobs:
        return 0

    count = 0
    for job in expired_jobs:
        logger.warning("Recovering expired job %s (status=%s, attempt=%d)", job.id, job.status.value, job.attempt_count)
        if job.status == JobStatus.CLAIMED:
            # Claimed but never started -> requeue without consuming attempt
            job.status = JobStatus.QUEUED
            job.worker_id = None
            job.claim_token = None
            job.claimed_at = None
            job.lease_expires_at = None

            log = JobLog(
                job_id=job.id,
                level=LogLevel.WARNING,
                message="Recovered claimed job with expired lease. Requeued without consuming attempt.",
            )
            session.add(log)
        elif job.status == JobStatus.RUNNING:
            # Running interrupted job -> finalize execution with WorkerLostError
            exec_stmt = (
                select(JobExecution)
                .where(
                    JobExecution.job_id == job.id,
                    JobExecution.attempt_number == job.attempt_count,
                    JobExecution.status == "running",
                )
                .with_for_update()
            )
            execution = (await session.execute(exec_stmt)).scalar_one_or_none()
            exec_id = None
            if execution:
                execution.status = "interrupted"
                execution.error_type = "WorkerLostError"
                execution.error_message = "Worker running this execution lost lease or crashed"
                execution.finished_at = text("NOW()")
                execution.duration_ms = text("CAST(EXTRACT(EPOCH FROM (NOW() - job_executions.started_at)) * 1000 AS BIGINT)")
                exec_id = execution.id

            job.last_error = {
                "type": "WorkerLostError",
                "message": "Worker running this execution lost lease or crashed",
                "attempt": job.attempt_count,
            }

            if job.attempt_count < job.max_attempts:
                # Route to retry_wait
                queue_stmt = select(Queue).where(Queue.id == job.queue_id)
                queue = (await session.execute(queue_stmt)).scalar_one()
                if queue.retry_policy:
                    delay = calculate_retry_delay(
                        strategy=queue.retry_policy.strategy,
                        attempt_number=job.attempt_count,
                        base_delay_seconds=queue.retry_policy.base_delay_seconds,
                        max_delay_seconds=queue.retry_policy.max_delay_seconds,
                        jitter=queue.retry_policy.jitter,
                        jitter_factor=queue.retry_policy.jitter_factor,
                    )
                else:
                    delay = float(settings.JOB_LEASE_DURATION_SECONDS)

                job.status = JobStatus.RETRY_WAIT
                job.available_at = text("NOW() + (:delay * INTERVAL '1 second')").bindparams(delay=delay)
                job.worker_id = None
                job.claim_token = None
                job.claimed_at = None
                job.lease_expires_at = None

                log = JobLog(
                    job_id=job.id,
                    execution_id=exec_id,
                    level=LogLevel.WARNING,
                    message=f"Job interrupted on attempt {job.attempt_count} (WorkerLostError). Scheduling retry in {delay}s.",
                )
                session.add(log)
            else:
                # Exhausted -> DLQ
                job.status = JobStatus.DEAD_LETTERED
                job.failed_at = text("NOW()")
                job.worker_id = None
                job.claim_token = None
                job.claimed_at = None
                job.lease_expires_at = None

                dlq_entry = DLQEntry(
                    job_id=job.id,
                    queue_id=job.queue_id,
                    final_execution_id=exec_id,
                    reason=f"Exhausted {job.max_attempts} attempts. Last error: WorkerLostError",
                    error_snapshot=job.last_error,
                    attempts=job.attempt_count,
                    dead_lettered_at=text("NOW()"),
                )
                session.add(dlq_entry)

                log = JobLog(
                    job_id=job.id,
                    execution_id=exec_id,
                    level=LogLevel.ERROR,
                    message=f"Job dead-lettered after WorkerLostError on attempt {job.attempt_count}.",
                )
                session.add(log)
        count += 1

    await session.commit()
    if count > 0:
        logger.info("Recovered %d expired jobs.", count)
    return count


class ReaperScheduler:
    """Background scheduler loop for reaping stale workers and expired job leases."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 15.0,
        batch_limit: int = 100,
    ) -> None:
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.batch_limit = batch_limit
        self.is_running = False

    async def start(self) -> None:
        """Start the reaper loop."""
        self.is_running = True
        logger.info("Starting reaper loop (interval=%.2fs)...", self.interval_seconds)
        try:
            while self.is_running:
                try:
                    async with self.session_factory() as session:
                        await reap_stale_workers(session)
                    async with self.session_factory() as session:
                        await reap_expired_jobs(session, limit=self.batch_limit)
                except Exception as exc:
                    logger.error("Error in reaper loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval_seconds)
        finally:
            logger.info("Reaper loop stopped.")

    def stop(self) -> None:
        """Stop the reaper loop."""
        self.is_running = False
