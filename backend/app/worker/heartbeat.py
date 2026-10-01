"""Worker registration, lifecycle status, and liveness heartbeats."""

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Callable
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import WorkerStatus
from app.models.worker import Worker
from app.repositories import worker_repository
from app.repositories.expressions import db_now
from app.worker.shutdown import cancel_and_wait

logger = logging.getLogger(__name__)


async def register_worker(
    session: AsyncSession,
    worker_id: uuid.UUID,
    name: str,
    concurrency: int,
    hostname: Optional[str] = None,
    pid: Optional[int] = None,
) -> Worker:
    """Register (or re-register) a worker process as ONLINE and commit."""
    if not hostname:
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "localhost"
    if not pid:
        pid = os.getpid()

    worker = await worker_repository.get_by_id(session, worker_id)
    if worker:
        worker.name = name
        worker.hostname = hostname[:255]
        worker.process_id = pid
        worker.status = WorkerStatus.ONLINE
        worker.concurrency = concurrency
        worker.started_at = db_now()
        worker.last_seen_at = db_now()
        worker.stopped_at = None
    else:
        worker = Worker(
            id=worker_id,
            name=name,
            hostname=hostname[:255],
            process_id=pid,
            status=WorkerStatus.ONLINE,
            concurrency=concurrency,
            started_at=db_now(),
            last_seen_at=db_now(),
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
    """Update worker lifecycle status and commit."""
    await worker_repository.update_status(session, worker_id, status)
    await session.commit()
    logger.info("Updated worker %s status to %s", worker_id, status.value)


async def record_heartbeat(
    session: AsyncSession,
    worker_id: uuid.UUID,
    active_job_count: int,
) -> None:
    """Record a heartbeat snapshot and update last_seen_at using DB clock."""
    try:
        await worker_repository.touch_last_seen(session, worker_id)
        worker_repository.add_heartbeat(session, worker_id, active_job_count)
        await session.commit()
        logger.debug("Recorded heartbeat for worker %s (active_jobs=%d)", worker_id, active_job_count)
    except Exception as exc:
        logger.warning("Transient heartbeat failure for worker %s: %s", worker_id, exc, exc_info=True)
        await session.rollback()
        raise


class HeartbeatEmitter:
    """Background task that records a heartbeat every ``interval_seconds``."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        worker_id: uuid.UUID,
        active_job_count: Callable[[], int],
        interval_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.active_job_count = active_job_count
        self.interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Start emitting heartbeats in the background."""
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop emitting heartbeats."""
        await cancel_and_wait([self._task])
        self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            async with self.session_factory() as session:
                try:
                    await record_heartbeat(
                        session=session,
                        worker_id=self.worker_id,
                        active_job_count=self.active_job_count(),
                    )
                except Exception:
                    # Logged inside record_heartbeat; transient failures must not kill the loop.
                    pass
