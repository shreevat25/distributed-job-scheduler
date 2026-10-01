"""Job repository — persistence primitives including atomic claim."""

import uuid

from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.repositories.expressions import db_now, db_now_plus_seconds

ACTIVE_STATUSES = (JobStatus.CLAIMED, JobStatus.RUNNING)
PROMOTABLE_STATUSES = (JobStatus.SCHEDULED, JobStatus.RETRY_WAIT)


async def claim_jobs_atomic(
    session: AsyncSession,
    queue_id: uuid.UUID,
    worker_id: uuid.UUID,
    limit: int,
    lease_duration_seconds: int,
) -> list[Job]:
    """Atomically claim eligible jobs using SELECT FOR UPDATE SKIP LOCKED.

    This is the core persistence primitive for job claiming. It must be called
    within a transaction that has already locked the queue row for concurrency
    limit enforcement.

    Eligible jobs:
        - status = queued
        - available_at <= NOW() (using authoritative DB clock)
        - belong to the specified queue

    Ordering:
        - priority DESC (higher priority first)
        - created_at ASC (FIFO within same priority)

    Each claimed job gets:
        - worker_id assigned
        - unique claim_token generated
        - status set to 'claimed'
        - claimed_at set to DB NOW()
        - lease_expires_at set to DB NOW() + interval
        - lease_version incremented

    Args:
        session: Active async session (must be within a transaction).
        queue_id: The queue to claim from.
        worker_id: The worker claiming the jobs.
        limit: Maximum number of jobs to claim.
        lease_duration_seconds: How long the lease is valid.

    Returns:
        List of claimed Job instances.
    """
    if limit <= 0:
        return []

    # SELECT eligible jobs with row-level locks using PostgreSQL database clock for distributed coordination
    stmt = (
        select(Job)
        .where(
            Job.queue_id == queue_id,
            Job.status == JobStatus.QUEUED,
            Job.available_at <= func.now(),
        )
        .order_by(Job.priority.desc(), Job.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(stmt)
    jobs = list(result.scalars().all())

    # Update each claimed job within the same transaction using database-side expressions
    # to ensure all workers evaluate lease timing and claim timestamps against the authoritative DB clock.
    for job in jobs:
        job.status = JobStatus.CLAIMED
        job.worker_id = worker_id
        job.claim_token = uuid.uuid4()
        job.claimed_at = db_now()
        job.lease_expires_at = db_now_plus_seconds(lease_duration_seconds)
        job.lease_version = Job.lease_version + 1

    await session.flush()

    # Refresh attributes from the DB so ORM models contain evaluated datetime objects (for Pydantic validation)
    for job in jobs:
        await session.refresh(job, ["claimed_at", "lease_expires_at", "lease_version", "updated_at"])

    return jobs


async def create_job(session: AsyncSession, job: Job) -> Job:
    """Persist a new job."""
    session.add(job)
    await session.flush()
    return job


async def get_job_by_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> Job | None:
    """Fetch a job by its ID."""
    stmt = select(Job).where(Job.id == job_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_job_by_idempotency_key(
    session: AsyncSession,
    queue_id: uuid.UUID,
    idempotency_key: str,
) -> Job | None:
    """Fetch a job by queue_id + idempotency_key."""
    stmt = select(Job).where(
        Job.queue_id == queue_id,
        Job.idempotency_key == idempotency_key,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_jobs(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    queue_id: uuid.UUID | None = None,
    status: JobStatus | None = None,
    batch_id: uuid.UUID | None = None,
    job_type: str | None = None,
    min_priority: int | None = None,
    page: int = 1,
    limit: int = 50,
    allowed_queue_ids: list[uuid.UUID] | None = None,
) -> tuple[list[Job], int]:
    """List jobs with filtering and pagination.

    Args:
        allowed_queue_ids: If provided, restrict to these queue IDs (authorization).
        Other args are filter parameters.

    Returns:
        Tuple of (jobs, total_count).
    """
    conditions = []

    if queue_id is not None:
        conditions.append(Job.queue_id == queue_id)
    elif allowed_queue_ids is not None:
        conditions.append(Job.queue_id.in_(allowed_queue_ids))

    if status is not None:
        conditions.append(Job.status == status)
    if batch_id is not None:
        conditions.append(Job.batch_id == batch_id)
    if job_type is not None:
        conditions.append(Job.type == job_type)
    if min_priority is not None:
        conditions.append(Job.priority >= min_priority)

    where_clause = and_(*conditions) if conditions else True

    # Count query
    count_stmt = select(func.count()).select_from(Job).where(where_clause)
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    # Data query
    offset = (page - 1) * limit
    data_stmt = (
        select(Job)
        .where(where_clause)
        .order_by(Job.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    data_result = await session.execute(data_stmt)
    jobs = list(data_result.scalars().all())

    return jobs, total


async def get_owned(
    session: AsyncSession,
    job_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Job | None:
    """Fetch a job whose queue's project is owned by the given user."""
    stmt = (
        select(Job)
        .join(Queue, Job.queue_id == Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .where(
            Job.id == job_id,
            Project.owner_id == owner_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_job_for_update(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> Job | None:
    """Lock and fetch a job row (FOR UPDATE) for a state transition."""
    stmt = select(Job).where(Job.id == job_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def is_lease_expired(session: AsyncSession, job_id: uuid.UUID) -> bool:
    """Whether the job's lease has expired according to the DB clock."""
    stmt = select(Job.lease_expires_at <= db_now()).where(Job.id == job_id)
    return bool((await session.execute(stmt)).scalar())


async def renew_lease(
    session: AsyncSession,
    job_id: uuid.UUID,
    worker_id: uuid.UUID,
    claim_token: uuid.UUID,
    lease_duration_seconds: int,
) -> bool:
    """Extend the lease of an active job still owned by worker_id/claim_token.

    Returns True if a row was updated, False if ownership was lost.
    """
    stmt = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.worker_id == worker_id,
            Job.claim_token == claim_token,
            Job.status.in_(ACTIVE_STATUSES),
        )
        .values(
            lease_expires_at=db_now_plus_seconds(lease_duration_seconds),
            lease_version=Job.lease_version + 1,
        )
    )
    result = await session.execute(stmt)
    return result.rowcount > 0


async def lock_due_for_promotion(session: AsyncSession, limit: int) -> list[Job]:
    """Lock scheduled/retry_wait jobs whose available_at has passed (SKIP LOCKED)."""
    stmt = (
        select(Job)
        .where(
            Job.status.in_(PROMOTABLE_STATUSES),
            Job.available_at <= db_now(),
        )
        .order_by(Job.available_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def lock_expired_leases(session: AsyncSession, limit: int) -> list[Job]:
    """Lock claimed/running jobs whose lease has expired (SKIP LOCKED)."""
    stmt = (
        select(Job)
        .where(
            Job.status.in_(ACTIVE_STATUSES),
            Job.lease_expires_at <= db_now(),
        )
        .order_by(Job.lease_expires_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def release_claim(job: Job) -> None:
    """Clear worker ownership and lease fields on a job."""
    job.worker_id = None
    job.claim_token = None
    job.claimed_at = None
    job.lease_expires_at = None


async def count_jobs_by_status(
    session: AsyncSession,
    *,
    queue_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> list[tuple[JobStatus, int]]:
    """Count jobs grouped by status, filtered by queue and/or batch."""
    stmt = select(Job.status, func.count().label("count"))
    if queue_id is not None:
        stmt = stmt.where(Job.queue_id == queue_id)
    if batch_id is not None:
        stmt = stmt.where(Job.batch_id == batch_id)
    result = await session.execute(stmt.group_by(Job.status))
    return list(result.all())
