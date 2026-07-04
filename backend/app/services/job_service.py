"""Job service — creation, idempotency, listing, and authorization."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import JobStatus
from app.core.exceptions import (
    IdempotencyConflictError,
    NotFoundError,
    ForbiddenError,
)
from app.models.job import Job
from app.models.queue import Queue
from app.repositories import job_repository
from app.schemas.job import JobCreate, JobResponse
from app.schemas.common import PaginatedResponse


def _resolve_max_attempts(
    explicit: int | None,
    queue: Queue,
) -> int:
    """Determine max_attempts: explicit override > queue retry policy > default."""
    if explicit is not None:
        return explicit
    if queue.retry_policy is not None:
        return queue.retry_policy.max_attempts
    return settings.DEFAULT_MAX_ATTEMPTS


async def create_job(
    session: AsyncSession,
    queue: Queue,
    data: JobCreate,
) -> tuple[Job, bool]:
    """Create a new job, handling idempotency.

    Returns:
        Tuple of (job, is_new). is_new=False means an existing idempotent match.

    Raises:
        IdempotencyConflictError: If idempotency_key matches but type/payload differ.
    """
    now = datetime.now(UTC)

    # Determine scheduling
    if data.available_at is not None:
        available_at = data.available_at
        status = JobStatus.SCHEDULED if available_at > now else JobStatus.QUEUED
    elif data.delay_seconds is not None and data.delay_seconds > 0:
        available_at = now + timedelta(seconds=data.delay_seconds)
        status = JobStatus.SCHEDULED
    else:
        available_at = now
        status = JobStatus.QUEUED

    max_attempts = _resolve_max_attempts(data.max_attempts, queue)

    job = Job(
        queue_id=queue.id,
        type=data.type,
        payload=data.payload,
        status=status,
        priority=data.priority,
        available_at=available_at,
        idempotency_key=data.idempotency_key,
        max_attempts=max_attempts,
    )

    # If no idempotency key, just create
    if data.idempotency_key is None:
        await job_repository.create_job(session, job)
        return job, True

    # With idempotency key: try to create, handle race via DB unique index
    try:
        async with session.begin_nested():
            await job_repository.create_job(session, job)
        return job, True
    except IntegrityError:

        # Fetch the existing job
        existing = await job_repository.get_job_by_idempotency_key(
            session, queue.id, data.idempotency_key
        )
        if existing is None:
            raise  # Unexpected integrity error

        # Check for idempotency conflict (different type or payload)
        if existing.type != data.type or existing.payload != data.payload:
            raise IdempotencyConflictError(data.idempotency_key)

        return existing, False


async def get_job_authorized(
    session: AsyncSession,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    allowed_queue_ids: list[uuid.UUID],
) -> Job:
    """Fetch a job, ensuring it belongs to a queue owned by the user.

    Raises:
        NotFoundError: If job doesn't exist.
        ForbiddenError: If job's queue isn't in user's allowed queues.
    """
    job = await job_repository.get_job_by_id(session, job_id)
    if job is None:
        raise NotFoundError("Job", str(job_id))
    if job.queue_id not in allowed_queue_ids:
        raise ForbiddenError("Access denied to this job")
    return job


async def list_jobs_paginated(
    session: AsyncSession,
    *,
    allowed_queue_ids: list[uuid.UUID],
    queue_id: uuid.UUID | None = None,
    status: JobStatus | None = None,
    batch_id: uuid.UUID | None = None,
    job_type: str | None = None,
    min_priority: int | None = None,
    page: int = 1,
    limit: int = 50,
) -> PaginatedResponse[JobResponse]:
    """List jobs with filters, pagination, and authorization."""
    # If queue_id is specified, verify it's in allowed list
    if queue_id is not None and queue_id not in allowed_queue_ids:
        raise ForbiddenError("Access denied to this queue")

    jobs, total = await job_repository.list_jobs(
        session,
        queue_id=queue_id,
        status=status,
        batch_id=batch_id,
        job_type=job_type,
        min_priority=min_priority,
        page=page,
        limit=limit,
        allowed_queue_ids=allowed_queue_ids if queue_id is None else None,
    )

    return PaginatedResponse[JobResponse](
        items=[JobResponse.model_validate(j) for j in jobs],
        page=page,
        limit=limit,
        total=total,
    )
