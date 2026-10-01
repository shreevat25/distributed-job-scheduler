"""Worker repository — worker registry and heartbeat persistence."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import WorkerStatus
from app.models.worker import Worker
from app.models.worker_heartbeat import WorkerHeartbeat
from app.repositories.expressions import db_now, db_now_minus_seconds


async def get_by_id(session: AsyncSession, worker_id: uuid.UUID) -> Worker | None:
    """Fetch a worker by ID."""
    stmt = select(Worker).where(Worker.id == worker_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession) -> list[Worker]:
    """List all registered workers, most recently started first."""
    stmt = select(Worker).order_by(Worker.started_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_status(
    session: AsyncSession,
    worker_id: uuid.UUID,
    status: WorkerStatus,
) -> None:
    """Set a worker's lifecycle status, stamping stopped_at for terminal states."""
    values = {"status": status, "last_seen_at": db_now()}
    if status in (WorkerStatus.OFFLINE, WorkerStatus.DEAD):
        values["stopped_at"] = db_now()

    stmt = update(Worker).where(Worker.id == worker_id).values(**values)
    await session.execute(stmt)


async def touch_last_seen(session: AsyncSession, worker_id: uuid.UUID) -> None:
    """Advance a worker's last_seen_at to the DB clock."""
    stmt = (
        update(Worker)
        .where(Worker.id == worker_id)
        .values(last_seen_at=db_now())
    )
    await session.execute(stmt)


def add_heartbeat(
    session: AsyncSession,
    worker_id: uuid.UUID,
    active_job_count: int,
) -> WorkerHeartbeat:
    """Stage a heartbeat snapshot row."""
    hb = WorkerHeartbeat(
        worker_id=worker_id,
        active_job_count=active_job_count,
        created_at=db_now(),
    )
    session.add(hb)
    return hb


async def lock_stale_online_workers(
    session: AsyncSession,
    threshold_seconds: int,
) -> list[Worker]:
    """Lock ONLINE workers not seen within threshold_seconds (SKIP LOCKED)."""
    stmt = (
        select(Worker)
        .where(
            Worker.status == WorkerStatus.ONLINE,
            Worker.last_seen_at < db_now_minus_seconds(threshold_seconds),
        )
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
