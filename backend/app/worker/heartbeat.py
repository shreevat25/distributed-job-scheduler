"""Worker registration and heartbeat monitoring."""

import logging
import os
import socket
import uuid
from typing import Optional

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import WorkerStatus
from app.models.worker import Worker
from app.models.worker_heartbeat import WorkerHeartbeat

logger = logging.getLogger(__name__)


async def register_worker(
    session: AsyncSession,
    worker_id: uuid.UUID,
    name: str,
    concurrency: int,
    hostname: Optional[str] = None,
    pid: Optional[int] = None,
) -> Worker:
    """Register a new worker process in the database."""
    if not hostname:
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "localhost"
    if not pid:
        pid = os.getpid()

    stmt = select(Worker).where(Worker.id == worker_id)
    worker = (await session.execute(stmt)).scalar_one_or_none()
    if worker:
        worker.name = name
        worker.hostname = hostname[:255]
        worker.process_id = pid
        worker.status = WorkerStatus.ONLINE
        worker.concurrency = concurrency
        worker.started_at = text("NOW()")
        worker.last_seen_at = text("NOW()")
        worker.stopped_at = None
    else:
        worker = Worker(
            id=worker_id,
            name=name,
            hostname=hostname[:255],
            process_id=pid,
            status=WorkerStatus.ONLINE,
            concurrency=concurrency,
            started_at=text("NOW()"),
            last_seen_at=text("NOW()"),
        )
        session.add(worker)
    await session.commit()
    await session.refresh(worker)
    logger.info("Registered worker online: %s (id=%s, concurrency=%d)", name, worker_id, concurrency)
    return worker


async def update_worker_status(
    session: AsyncSession,
    worker_id: uuid.UUID,
    status: WorkerStatus,
) -> None:
    """Update worker lifecycle status."""
    values = {"status": status, "last_seen_at": text("NOW()")}
    if status in (WorkerStatus.OFFLINE, WorkerStatus.DEAD):
        values["stopped_at"] = text("NOW()")

    stmt = update(Worker).where(Worker.id == worker_id).values(**values)
    await session.execute(stmt)
    await session.commit()
    logger.info("Updated worker %s status to %s", worker_id, status.value)


async def record_heartbeat(
    session: AsyncSession,
    worker_id: uuid.UUID,
    active_job_count: int,
) -> None:
    """Record a heartbeat snapshot and update last_seen_at using DB clock."""
    try:
        # Update worker last_seen_at
        stmt = (
            update(Worker)
            .where(Worker.id == worker_id)
            .values(last_seen_at=text("NOW()"))
        )
        await session.execute(stmt)

        # Insert heartbeat record
        hb = WorkerHeartbeat(
            worker_id=worker_id,
            active_job_count=active_job_count,
            created_at=text("NOW()"),
        )
        session.add(hb)
        await session.commit()
        logger.debug("Recorded heartbeat for worker %s (active_jobs=%d)", worker_id, active_job_count)
    except Exception as exc:
        logger.warning("Transient heartbeat failure for worker %s: %s", worker_id, exc, exc_info=True)
        await session.rollback()
        raise
