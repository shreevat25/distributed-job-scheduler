"""Dead-letter queue repository — DLQ entry persistence."""

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dlq_entry import DLQEntry
from app.models.project import Project
from app.models.queue import Queue
from app.repositories.expressions import db_now


def _owned_entries(owner_id: uuid.UUID) -> Select[tuple[DLQEntry]]:
    """Base query for DLQ entries whose queue's project is owned by owner_id."""
    return (
        select(DLQEntry)
        .join(Queue, DLQEntry.queue_id == Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .where(Project.owner_id == owner_id)
    )


def add_entry(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    queue_id: uuid.UUID,
    final_execution_id: uuid.UUID | None,
    reason: str,
    error_snapshot: dict[str, Any] | None,
    attempts: int,
) -> DLQEntry:
    """Stage a new DLQ entry in the current transaction."""
    entry = DLQEntry(
        job_id=job_id,
        queue_id=queue_id,
        final_execution_id=final_execution_id,
        reason=reason,
        error_snapshot=error_snapshot,
        attempts=attempts,
        dead_lettered_at=db_now(),
    )
    session.add(entry)
    return entry


async def list_for_owner(
    session: AsyncSession,
    owner_id: uuid.UUID,
    queue_id: uuid.UUID | None = None,
) -> list[DLQEntry]:
    """List an owner's DLQ entries, newest first."""
    stmt = _owned_entries(owner_id)
    if queue_id:
        stmt = stmt.where(DLQEntry.queue_id == queue_id)
    stmt = stmt.order_by(DLQEntry.dead_lettered_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_owned(
    session: AsyncSession,
    entry_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> DLQEntry | None:
    """Fetch (optionally lock) a DLQ entry scoped to its owner."""
    stmt = _owned_entries(owner_id).where(DLQEntry.id == entry_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
