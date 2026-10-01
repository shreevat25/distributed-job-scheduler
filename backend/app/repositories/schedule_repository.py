"""Scheduled job repository — persistence operations for schedules."""

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob
from app.repositories.expressions import db_now


async def current_db_time(session: AsyncSession) -> datetime:
    """Read the authoritative database timestamp."""
    result = await session.execute(text("SELECT CURRENT_TIMESTAMP"))
    return result.scalar_one()


async def lock_due_schedules(session: AsyncSession, limit: int) -> list[ScheduledJob]:
    """Lock active schedules whose next_run_at has passed (SKIP LOCKED)."""
    stmt = (
        select(ScheduledJob)
        .where(
            ScheduledJob.is_active == True,  # noqa: E712
            ScheduledJob.next_run_at <= db_now(),
        )
        .order_by(ScheduledJob.next_run_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_for_creator(
    session: AsyncSession,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ScheduledJob | None:
    """Fetch a schedule created by the given user."""
    stmt = select(ScheduledJob).where(
        ScheduledJob.id == schedule_id,
        ScheduledJob.created_by == user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_for_creator(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    queue_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[ScheduledJob]:
    """List a user's schedules, newest first."""
    stmt = (
        select(ScheduledJob)
        .join(Queue)
        .where(ScheduledJob.created_by == user_id)
        .order_by(ScheduledJob.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if queue_id:
        stmt = stmt.where(ScheduledJob.queue_id == queue_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def add(session: AsyncSession, schedule: ScheduledJob) -> ScheduledJob:
    """Stage a new schedule."""
    session.add(schedule)
    return schedule


async def delete(session: AsyncSession, schedule: ScheduledJob) -> None:
    """Delete a schedule."""
    await session.delete(schedule)
