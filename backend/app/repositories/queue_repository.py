"""Queue repository — persistence operations for queues."""

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus
from app.models.job import Job
from app.models.queue import Queue
from app.schemas.queue import QueueStatsResponse


async def get_queue_for_update(
    session: AsyncSession,
    queue_id: uuid.UUID,
) -> Queue | None:
    """Lock and fetch a queue row using SELECT FOR UPDATE.

    This serializes concurrent claim-capacity allocation for the same queue,
    ensuring the concurrency limit is enforced correctly under contention.
    Different queues can still be locked concurrently.
    """
    stmt = (
        select(Queue)
        .where(Queue.id == queue_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_queue_by_id(
    session: AsyncSession,
    queue_id: uuid.UUID,
) -> Queue | None:
    """Fetch a queue without locking."""
    stmt = select(Queue).where(Queue.id == queue_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_queues_by_project(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> list[Queue]:
    """List all queues belonging to a project."""
    stmt = select(Queue).where(Queue.project_id == project_id).order_by(Queue.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_queue(session: AsyncSession, queue: Queue) -> Queue:
    """Persist a new queue."""
    session.add(queue)
    await session.flush()
    return queue


async def count_active_jobs(
    session: AsyncSession,
    queue_id: uuid.UUID,
) -> int:
    """Count jobs in active states (claimed or running) for a queue.

    This must be called within the same transaction that holds
    the queue FOR UPDATE lock to ensure consistency.
    """
    stmt = (
        select(func.count())
        .select_from(Job)
        .where(
            Job.queue_id == queue_id,
            Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_queue_stats(
    session: AsyncSession,
    queue_id: uuid.UUID,
) -> QueueStatsResponse:
    """Compute real database counts of jobs by status for a queue."""
    stmt = (
        select(Job.status, func.count().label("count"))
        .where(Job.queue_id == queue_id)
        .group_by(Job.status)
    )
    result = await session.execute(stmt)
    rows = result.all()

    counts: dict[str, int] = {}
    total = 0
    for status_val, count in rows:
        status_name = status_val.value if hasattr(status_val, "value") else str(status_val)
        counts[status_name] = count
        total += count

    return QueueStatsResponse(
        queue_id=queue_id,
        queued=counts.get("queued", 0),
        scheduled=counts.get("scheduled", 0),
        claimed=counts.get("claimed", 0),
        running=counts.get("running", 0),
        retry_wait=counts.get("retry_wait", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        dead_lettered=counts.get("dead_lettered", 0),
        total=total,
    )
