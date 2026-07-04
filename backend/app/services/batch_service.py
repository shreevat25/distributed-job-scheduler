"""Batch service — transactional multi-job creation."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import JobStatus
from app.core.exceptions import IdempotencyConflictError
from app.models.job import Job
from app.models.job_batch import JobBatch
from app.models.queue import Queue
from app.repositories import job_repository
from app.schemas.batch import (
    BatchCreate,
    BatchResponse,
    BatchDetailResponse,
    BatchStatusCount,
)


async def create_batch(
    session: AsyncSession,
    queue: Queue,
    user_id: uuid.UUID,
    data: BatchCreate,
) -> BatchResponse:
    """Create a batch of jobs atomically in a single transaction.

    All jobs and the batch record are created together. If any job fails
    validation or persistence, the entire transaction rolls back —
    no partial batch remains.
    """
    now = datetime.now(UTC)

    try:
        # Create the batch record
        batch = JobBatch(
            queue_id=queue.id,
            created_by=user_id,
            name=data.name,
            total_jobs=len(data.jobs),
        )
        session.add(batch)
        await session.flush()  # Get batch.id

        job_ids: list[uuid.UUID] = []

        for item in data.jobs:
            # Determine scheduling
            if item.delay_seconds is not None and item.delay_seconds > 0:
                available_at = now + timedelta(seconds=item.delay_seconds)
                status = JobStatus.SCHEDULED
            else:
                available_at = now
                status = JobStatus.QUEUED

            # Resolve max_attempts
            max_attempts = item.max_attempts
            if max_attempts is None:
                if queue.retry_policy is not None:
                    max_attempts = queue.retry_policy.max_attempts
                else:
                    max_attempts = settings.DEFAULT_MAX_ATTEMPTS

            job = Job(
                queue_id=queue.id,
                batch_id=batch.id,
                type=item.type,
                payload=item.payload,
                status=status,
                priority=item.priority,
                available_at=available_at,
                idempotency_key=item.idempotency_key,
                max_attempts=max_attempts,
            )
            session.add(job)
            await session.flush()
            job_ids.append(job.id)
    except IntegrityError:
        await session.rollback()
        raise IdempotencyConflictError("Conflicting idempotency key or database constraint violation in batch")

    return BatchResponse(
        id=batch.id,
        queue_id=queue.id,
        name=data.name,
        total_jobs=batch.total_jobs,
        job_ids=job_ids,
        created_at=batch.created_at,
    )


async def get_batch_detail(
    session: AsyncSession,
    batch_id: uuid.UUID,
) -> BatchDetailResponse | None:
    """Fetch batch details with real aggregate status counts."""
    from sqlalchemy import select

    stmt = select(JobBatch).where(JobBatch.id == batch_id)
    result = await session.execute(stmt)
    batch = result.scalar_one_or_none()

    if batch is None:
        return None

    # Get real status counts
    rows = await job_repository.count_jobs_by_status_for_batch(session, batch_id)
    status_counts = [
        BatchStatusCount(status=status_val, count=count)
        for status_val, count in rows
    ]

    return BatchDetailResponse(
        id=batch.id,
        queue_id=batch.queue_id,
        created_by=batch.created_by,
        name=batch.name,
        total_jobs=batch.total_jobs,
        status_counts=status_counts,
        created_at=batch.created_at,
    )
