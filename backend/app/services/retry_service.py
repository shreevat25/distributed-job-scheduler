"""Retry service — retry delay math and the retry-or-dead-letter decision.

Every path that ends an attempt unsuccessfully (a handler failure reported by
the worker, or a lost lease recovered by the reaper) routes through
``retry_or_dead_letter`` so retry scheduling and DLQ handoff stay identical.
"""

import random
import uuid
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import JobStatus, LogLevel, RetryStrategy
from app.core.exceptions import ConflictError, NotFoundError
from app.models.dlq_entry import DLQEntry
from app.models.job import Job
from app.models.retry_policy import RetryPolicy
from app.repositories import dlq_repository, job_log_repository, job_repository, queue_repository
from app.repositories.expressions import db_now, db_now_plus_seconds


def calculate_retry_delay(
    strategy: RetryStrategy | str,
    attempt_number: int,
    base_delay_seconds: int,
    max_delay_seconds: Optional[int] = None,
    jitter: bool = False,
    jitter_factor: float = 0.1,
    random_func: Optional[Callable[[], float]] = None,
) -> float:
    """Calculate the retry delay in seconds for a failed job attempt.

    Args:
        strategy: 'fixed', 'linear', or 'exponential'
        attempt_number: The attempt number that just failed (e.g., 1 for attempt 1 failing)
        base_delay_seconds: Base delay in seconds
        max_delay_seconds: Optional cap on the calculated delay
        jitter: Whether to apply randomized jitter
        jitter_factor: Fraction of jitter to apply (0.0 to 1.0)
        random_func: Optional random generator function returning float in [0.0, 1.0) for testing

    Returns:
        Delay in seconds as a float.
    """
    if attempt_number < 1:
        attempt_number = 1

    if strategy == RetryStrategy.FIXED or strategy == "fixed":
        delay = float(base_delay_seconds)
    elif strategy == RetryStrategy.LINEAR or strategy == "linear":
        delay = float(base_delay_seconds * attempt_number)
    elif strategy == RetryStrategy.EXPONENTIAL or strategy == "exponential":
        delay = float(base_delay_seconds * (2 ** (attempt_number - 1)))
    else:
        delay = float(base_delay_seconds)

    if max_delay_seconds is not None and delay > max_delay_seconds:
        delay = float(max_delay_seconds)

    if jitter and jitter_factor > 0.0:
        rand = random_func() if random_func is not None else random.random()
        # Jitter bounded by jitter_factor: [-delay * jitter_factor, +delay * jitter_factor]
        offset = delay * jitter_factor * (2.0 * rand - 1.0)
        delay = max(0.0, delay + offset)

    return round(delay, 4)


def retry_delay_for_policy(policy: RetryPolicy | None, attempt_number: int) -> float:
    """Delay before the next attempt, from the queue's policy or the default."""
    if policy is None:
        return float(settings.JOB_LEASE_DURATION_SECONDS)
    return calculate_retry_delay(
        strategy=policy.strategy,
        attempt_number=attempt_number,
        base_delay_seconds=policy.base_delay_seconds,
        max_delay_seconds=policy.max_delay_seconds,
        jitter=policy.jitter,
        jitter_factor=policy.jitter_factor,
    )


async def retry_or_dead_letter(
    session: AsyncSession,
    job: Job,
    *,
    execution_id: uuid.UUID | None,
    retry_log: Callable[[float], str],
    dead_letter_reason: str,
    dead_letter_log: str,
) -> JobStatus:
    """Route a failed attempt to RETRY_WAIT, or to the DLQ once attempts are exhausted.

    The caller must hold the job row lock and have already set ``job.last_error``.
    Ownership and lease fields are cleared either way. Nothing is committed.

    Args:
        retry_log: Builds the retry log message from the computed delay.
        dead_letter_reason: Reason stored on the DLQ entry.
        dead_letter_log: Job log message written when dead-lettering.

    Returns:
        The job's new status.
    """
    job_repository.release_claim(job)

    if job.attempt_count < job.max_attempts:
        queue = await queue_repository.get_queue_by_id(session, job.queue_id)
        delay = retry_delay_for_policy(queue.retry_policy, job.attempt_count)

        job.status = JobStatus.RETRY_WAIT
        job.available_at = db_now_plus_seconds(delay)
        job_log_repository.add_log(
            session, job.id, LogLevel.WARNING, retry_log(delay), execution_id=execution_id
        )
        return job.status

    job.status = JobStatus.DEAD_LETTERED
    job.failed_at = db_now()
    dlq_repository.add_entry(
        session,
        job_id=job.id,
        queue_id=job.queue_id,
        final_execution_id=execution_id,
        reason=dead_letter_reason,
        error_snapshot=job.last_error,
        attempts=job.attempt_count,
    )
    job_log_repository.add_log(
        session, job.id, LogLevel.ERROR, dead_letter_log, execution_id=execution_id
    )
    return job.status


async def retry_dead_lettered_job(
    session: AsyncSession,
    entry_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DLQEntry:
    """Manually requeue a dead-lettered job, concurrency-safely.

    - Resets job attempt_count to 0
    - Preserves all historical JobExecution rows
    - Requeues job
    - Marks DLQ entry retried_at and retried_by

    Raises:
        NotFoundError: If the entry or its job doesn't exist for this user.
        ConflictError: If the entry has already been retried.
    """
    entry = await dlq_repository.get_owned(session, entry_id, user_id, for_update=True)
    if not entry:
        raise NotFoundError("DLQEntry", str(entry_id))

    if entry.retried_at is not None:
        raise ConflictError("DLQ entry has already been retried")

    job = await job_repository.get_job_for_update(session, entry.job_id)
    if not job:
        raise NotFoundError("Job", str(entry.job_id))

    # Reset job attempt_count to 0 and requeue
    job.attempt_count = 0
    job.status = JobStatus.QUEUED
    job.available_at = db_now()
    job.failed_at = None
    job_repository.release_claim(job)

    entry.retried_at = db_now()
    entry.retried_by = user_id

    job_log_repository.add_log(
        session,
        job.id,
        LogLevel.INFO,
        f"Job manually retried from DLQ by user {user_id} (attempt count reset to 0)",
    )
    return entry
