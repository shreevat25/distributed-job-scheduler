"""Job lifecycle management and transactional execution transitions."""

import uuid
from typing import Any

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import JobStatus, LogLevel
from app.core.exceptions import (
    ExhaustedAttemptsError,
    InvalidTransitionError,
    LeaseExpiredError,
    OwnershipLostError,
)
from app.models.dlq_entry import DLQEntry
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.queue import Queue
from app.services.retry_service import calculate_retry_delay


async def start_execution(
    session: AsyncSession,
    job_id: uuid.UUID,
    worker_id: uuid.UUID,
    claim_token: uuid.UUID,
) -> tuple[Job, JobExecution]:
    """Start execution of a claimed job transactionally.

    Verifies status, ownership, and lease expiration. Increments attempt_count
    and creates a JobExecution record.
    """
    stmt = select(Job).where(Job.id == job_id).with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if not job:
        raise OwnershipLostError("Job not found")

    if job.status != JobStatus.CLAIMED:
        raise InvalidTransitionError("Job", job.status.value, JobStatus.RUNNING.value)

    if job.worker_id != worker_id or job.claim_token != claim_token:
        raise OwnershipLostError("Worker does not own this claimed job")

    # Verify lease not expired using DB clock
    expired_stmt = select(Job.lease_expires_at <= text("NOW()")).where(Job.id == job_id)
    is_expired = (await session.execute(expired_stmt)).scalar()
    if is_expired:
        raise LeaseExpiredError("Job lease expired before execution could start")

    if job.attempt_count >= job.max_attempts:
        raise ExhaustedAttemptsError(f"Job already reached max attempts ({job.max_attempts})")

    # Increment attempt count
    job.attempt_count += 1
    attempt_number = job.attempt_count

    # Create JobExecution
    execution = JobExecution(
        job_id=job.id,
        attempt_number=attempt_number,
        worker_id=worker_id,
        claim_token=claim_token,
        status="running",
        started_at=text("NOW()"),
    )
    session.add(execution)
    await session.flush()  # get execution.id

    # Transition job
    job.status = JobStatus.RUNNING
    job.started_at = text("NOW()")

    # Append log
    log = JobLog(
        job_id=job.id,
        execution_id=execution.id,
        level=LogLevel.INFO,
        message=f"Started execution attempt {attempt_number} on worker {worker_id}",
    )
    session.add(log)
    await session.flush()

    return job, execution


async def complete_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    worker_id: uuid.UUID,
    claim_token: uuid.UUID,
    result: dict[str, Any],
) -> Job:
    """Authoritatively complete a running job transactionally.

    Verifies ownership and running state. A worker that lost ownership
    cannot complete the job.
    """
    stmt = select(Job).where(Job.id == job_id).with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if not job:
        raise OwnershipLostError("Job not found")

    if job.status != JobStatus.RUNNING:
        raise InvalidTransitionError("Job", job.status.value, JobStatus.COMPLETED.value)

    if job.worker_id != worker_id or job.claim_token != claim_token:
        raise OwnershipLostError("Worker lost ownership of this running job")

    # Find running execution
    exec_stmt = (
        select(JobExecution)
        .where(
            JobExecution.job_id == job_id,
            JobExecution.attempt_number == job.attempt_count,
        )
        .with_for_update()
    )
    execution = (await session.execute(exec_stmt)).scalar_one()
    execution.status = "completed"
    execution.result = result
    execution.finished_at = text("NOW()")
    execution.duration_ms = text("CAST(EXTRACT(EPOCH FROM (NOW() - job_executions.started_at)) * 1000 AS BIGINT)")

    # Transition job
    job.status = JobStatus.COMPLETED
    job.completed_at = text("NOW()")
    job.result = result

    # Append log
    log = JobLog(
        job_id=job.id,
        execution_id=execution.id,
        level=LogLevel.INFO,
        message=f"Job completed successfully on attempt {job.attempt_count}",
    )
    session.add(log)
    await session.flush()

    return job


async def fail_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    worker_id: uuid.UUID,
    claim_token: uuid.UUID,
    exc: Exception,
) -> Job:
    """Handle job execution failure transactionally.

    Sanitizes error, finalizes execution, and transitions job to retry_wait or dead_lettered.
    """
    stmt = select(Job).where(Job.id == job_id).with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if not job:
        raise OwnershipLostError("Job not found")

    if job.status != JobStatus.RUNNING:
        raise InvalidTransitionError("Job", job.status.value, "failed/retry_wait")

    if job.worker_id != worker_id or job.claim_token != claim_token:
        raise OwnershipLostError("Worker lost ownership of this running job")

    # Sanitize error
    error_type = type(exc).__name__[:255]
    error_message = str(exc)[:2000]
    error_details = {"exception": str(exc)}

    # Find running execution
    exec_stmt = (
        select(JobExecution)
        .where(
            JobExecution.job_id == job_id,
            JobExecution.attempt_number == job.attempt_count,
        )
        .with_for_update()
    )
    execution = (await session.execute(exec_stmt)).scalar_one()
    execution.status = "failed"
    execution.error_type = error_type
    execution.error_message = error_message
    execution.error_details = error_details
    execution.finished_at = text("NOW()")
    execution.duration_ms = text("CAST(EXTRACT(EPOCH FROM (NOW() - job_executions.started_at)) * 1000 AS BIGINT)")

    job.last_error = {
        "type": error_type,
        "message": error_message,
        "attempt": job.attempt_count,
    }

    if job.attempt_count < job.max_attempts:
        # Retry waiting
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
            execution_id=execution.id,
            level=LogLevel.WARNING,
            message=f"Attempt {job.attempt_count} failed ({error_type}: {error_message}). Scheduling retry in {delay}s.",
        )
        session.add(log)
    else:
        # Dead Letter Queue
        job.status = JobStatus.DEAD_LETTERED
        job.failed_at = text("NOW()")
        job.worker_id = None
        job.claim_token = None
        job.claimed_at = None
        job.lease_expires_at = None

        dlq_entry = DLQEntry(
            job_id=job.id,
            queue_id=job.queue_id,
            final_execution_id=execution.id,
            reason=f"Exhausted {job.max_attempts} attempts. Last error: {error_type}: {error_message}",
            error_snapshot=job.last_error,
            attempts=job.attempt_count,
            dead_lettered_at=text("NOW()"),
        )
        session.add(dlq_entry)

        log = JobLog(
            job_id=job.id,
            execution_id=execution.id,
            level=LogLevel.ERROR,
            message=f"Job dead-lettered after exhausting {job.attempt_count} attempts. Error: {error_type}: {error_message}",
        )
        session.add(log)

    await session.flush()
    return job


async def renew_lease(
    session: AsyncSession,
    job_id: uuid.UUID,
    worker_id: uuid.UUID,
    claim_token: uuid.UUID,
    lease_duration_seconds: int,
) -> bool:
    """Renew the lease on a claimed or running job using bound SQL parameters.

    Returns True if lease renewed successfully, False if ownership was lost.
    """
    stmt = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.worker_id == worker_id,
            Job.claim_token == claim_token,
            Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
        )
        .values(
            lease_expires_at=text("NOW() + (:duration * INTERVAL '1 second')").bindparams(
                duration=lease_duration_seconds
            ),
            lease_version=Job.lease_version + 1,
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0
