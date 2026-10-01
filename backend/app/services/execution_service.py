"""Execution service — transactional start/complete/fail transitions for claimed jobs.

Every transition locks the job row, re-verifies ownership via
(worker_id, claim_token), and records an audit trail in job_executions and
job_logs. A worker that has lost ownership cannot move the job. Nothing here
commits; the caller owns the transaction.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus, LogLevel
from app.core.exceptions import (
    ExhaustedAttemptsError,
    InvalidTransitionError,
    LeaseExpiredError,
    OwnershipLostError,
)
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.repositories import execution_repository, job_log_repository, job_repository
from app.repositories.expressions import db_now
from app.services import retry_service


async def _lock_owned_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    worker_id: uuid.UUID,
    claim_token: uuid.UUID,
    *,
    expected_status: JobStatus,
    target_status: str,
    ownership_message: str,
) -> Job:
    """Lock a job and verify it is in expected_status and owned by this claim."""
    job = await job_repository.get_job_for_update(session, job_id)
    if not job:
        raise OwnershipLostError("Job not found")

    if job.status != expected_status:
        raise InvalidTransitionError("Job", job.status.value, target_status)

    if job.worker_id != worker_id or job.claim_token != claim_token:
        raise OwnershipLostError(ownership_message)

    return job


async def _lock_current_execution(session: AsyncSession, job: Job) -> JobExecution:
    """Lock the execution row for the job's current attempt."""
    execution = await execution_repository.get_attempt_for_update(
        session, job.id, job.attempt_count
    )
    if execution is None:
        raise OwnershipLostError(f"No execution record for attempt {job.attempt_count}")
    return execution


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
    job = await _lock_owned_job(
        session,
        job_id,
        worker_id,
        claim_token,
        expected_status=JobStatus.CLAIMED,
        target_status=JobStatus.RUNNING.value,
        ownership_message="Worker does not own this claimed job",
    )

    if await job_repository.is_lease_expired(session, job_id):
        raise LeaseExpiredError("Job lease expired before execution could start")

    if job.attempt_count >= job.max_attempts:
        raise ExhaustedAttemptsError(f"Job already reached max attempts ({job.max_attempts})")

    job.attempt_count += 1
    attempt_number = job.attempt_count

    execution = await execution_repository.create(
        session,
        JobExecution(
            job_id=job.id,
            attempt_number=attempt_number,
            worker_id=worker_id,
            claim_token=claim_token,
            status="running",
            started_at=db_now(),
        ),
    )

    job.status = JobStatus.RUNNING
    job.started_at = db_now()

    job_log_repository.add_log(
        session,
        job.id,
        LogLevel.INFO,
        f"Started execution attempt {attempt_number} on worker {worker_id}",
        execution_id=execution.id,
    )
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
    job = await _lock_owned_job(
        session,
        job_id,
        worker_id,
        claim_token,
        expected_status=JobStatus.RUNNING,
        target_status=JobStatus.COMPLETED.value,
        ownership_message="Worker lost ownership of this running job",
    )

    execution = await _lock_current_execution(session, job)
    execution_repository.mark_finished(execution, "completed", result=result)

    job.status = JobStatus.COMPLETED
    job.completed_at = db_now()
    job.result = result

    job_log_repository.add_log(
        session,
        job.id,
        LogLevel.INFO,
        f"Job completed successfully on attempt {job.attempt_count}",
        execution_id=execution.id,
    )
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
    job = await _lock_owned_job(
        session,
        job_id,
        worker_id,
        claim_token,
        expected_status=JobStatus.RUNNING,
        target_status="failed/retry_wait",
        ownership_message="Worker lost ownership of this running job",
    )

    # Sanitize error
    error_type = type(exc).__name__[:255]
    error_message = str(exc)[:2000]

    execution = await _lock_current_execution(session, job)
    execution_repository.mark_finished(
        execution,
        "failed",
        error_type=error_type,
        error_message=error_message,
        error_details={"exception": str(exc)},
    )

    job.last_error = {
        "type": error_type,
        "message": error_message,
        "attempt": job.attempt_count,
    }
    attempt = job.attempt_count

    await retry_service.retry_or_dead_letter(
        session,
        job,
        execution_id=execution.id,
        retry_log=lambda delay: (
            f"Attempt {attempt} failed ({error_type}: {error_message}). Scheduling retry in {delay}s."
        ),
        dead_letter_reason=f"Exhausted {job.max_attempts} attempts. Last error: {error_type}: {error_message}",
        dead_letter_log=(
            f"Job dead-lettered after exhausting {attempt} attempts. Error: {error_type}: {error_message}"
        ),
    )

    await session.flush()
    return job
