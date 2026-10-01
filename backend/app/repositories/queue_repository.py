"""Queue repository — persistence operations for queues."""

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.repositories.job_repository import ACTIVE_STATUSES


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
            Job.status.in_(ACTIVE_STATUSES),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_owned(
    session: AsyncSession,
    queue_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Queue | None:
    """Fetch a queue whose project is owned by the given user."""
    stmt = (
        select(Queue)
        .join(Project, Queue.project_id == Project.id)
        .where(
            Queue.id == queue_id,
            Project.owner_id == owner_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_ids_for_owner(
    session: AsyncSession,
    owner_id: uuid.UUID,
) -> list[uuid.UUID]:
    """List IDs of every queue in projects owned by the given user."""
    stmt = (
        select(Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .where(Project.owner_id == owner_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_unpaused_ids(session: AsyncSession) -> list[uuid.UUID]:
    """List IDs of all queues that are not paused."""
    stmt = select(Queue.id).where(Queue.is_paused == False)  # noqa: E712
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_by_name(
    session: AsyncSession,
    project_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> Queue | None:
    """Find a project's queue by name, optionally excluding one queue."""
    stmt = select(Queue).where(
        Queue.project_id == project_id,
        Queue.name == name,
    )
    if exclude_id is not None:
        stmt = stmt.where(Queue.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
