"""Distributed worker engine: the poll/claim loop that ties the worker modules together."""

import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.enums import WorkerStatus
from app.repositories import queue_repository
from app.services import claim_service
from app.worker import heartbeat
from app.worker.executor import JobExecutor
from app.worker.heartbeat import HeartbeatEmitter
from app.worker.shutdown import ShutdownCoordinator, drain_tasks, install_signal_handlers

logger = logging.getLogger(__name__)


class WorkerRunner:
    """Asyncio worker engine that claims jobs, manages concurrency, and handles lifecycle."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        worker_id: Optional[uuid.UUID] = None,
        name: Optional[str] = None,
        concurrency: Optional[int] = None,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id or uuid.uuid4()
        self.name = name or settings.WORKER_NAME or "worker-default"
        self.concurrency = concurrency or settings.WORKER_CONCURRENCY or 5

        self.semaphore = asyncio.Semaphore(self.concurrency)
        self.active_tasks: set[asyncio.Task] = set()

        self.is_running = False
        self.executor = JobExecutor(session_factory, self.worker_id)
        self.heartbeat = HeartbeatEmitter(
            session_factory=session_factory,
            worker_id=self.worker_id,
            active_job_count=lambda: len(self.active_tasks),
            interval_seconds=float(settings.WORKER_HEARTBEAT_INTERVAL_SECONDS),
        )
        self._shutdown = ShutdownCoordinator()

    @property
    def is_draining(self) -> bool:
        """True once graceful shutdown has begun."""
        return self._shutdown.is_draining

    async def run(self) -> None:
        """Start worker registration, heartbeat loop, and job claim loop."""
        self.is_running = True
        self._shutdown.reset()

        # 1. Register worker online
        async with self.session_factory() as session:
            await heartbeat.register_worker(
                session=session,
                worker_id=self.worker_id,
                name=self.name,
                concurrency=self.concurrency,
            )

        # 2. Start heartbeat loop
        self.heartbeat.start()

        # 3. Setup signal handlers if running in main thread
        install_signal_handlers(lambda: asyncio.create_task(self.shutdown()))

        logger.info("Worker %s (%s) started polling loop.", self.name, self.worker_id)

        poll_interval = settings.WORKER_POLL_INTERVAL_MS / 1000.0
        try:
            while self.is_running and not self._shutdown.should_stop:
                available_slots = self.concurrency - len(self.active_tasks)
                if available_slots > 0 and not self._shutdown.is_draining:
                    try:
                        await self._poll_and_claim()
                    except Exception as exc:
                        logger.error("Error during poll and claim loop: %s", exc, exc_info=True)

                # Interruptible: returns as soon as shutdown is signalled.
                await self._shutdown.wait(poll_interval)
        finally:
            await self._shutdown_cleanup()

    async def shutdown(self) -> None:
        """Trigger graceful shutdown: stop claiming, record DRAINING, then wake the loop."""
        if not self.is_running or not self._shutdown.begin_draining():
            return

        logger.info("Worker %s received shutdown signal. Entering draining state...", self.name)
        try:
            async with self.session_factory() as session:
                await heartbeat.update_worker_status(session, self.worker_id, WorkerStatus.DRAINING)
        except Exception as exc:
            logger.warning("Failed to update worker status to draining: %s", exc)
        finally:
            self._shutdown.signal_stop()

    async def _poll_and_claim(self) -> None:
        """Query unpaused queues and claim jobs up to this worker's free slots."""
        async with self.session_factory() as session:
            queue_ids = await queue_repository.list_unpaused_ids(session)

        for q_id in queue_ids:
            if self._shutdown.is_draining:
                break
            slots_left = self.concurrency - len(self.active_tasks)
            if slots_left <= 0:
                break

            async with self.session_factory() as session:
                try:
                    jobs = await claim_service.claim_jobs(
                        session=session,
                        queue_id=q_id,
                        worker_id=self.worker_id,
                        requested_limit=slots_left,
                        lease_duration_seconds=settings.JOB_LEASE_DURATION_SECONDS,
                    )
                    await session.commit()
                except Exception as exc:
                    logger.debug("Could not claim from queue %s: %s", q_id, exc)
                    await session.rollback()
                    continue

            for job in jobs:
                if job.claim_token is None:
                    continue
                await self.semaphore.acquire()
                task = asyncio.create_task(
                    self.executor.execute(
                        job_id=job.id,
                        job_type=job.type,
                        payload=job.payload,
                        claim_token=job.claim_token,
                    )
                )
                self.active_tasks.add(task)
                task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Callback when an execution task completes."""
        self.active_tasks.discard(task)
        self.semaphore.release()

    async def _shutdown_cleanup(self) -> None:
        """Drain in-flight jobs, stop background loops, and mark the worker offline."""
        logger.info("Starting shutdown cleanup for worker %s...", self.name)
        await drain_tasks(self.active_tasks, float(settings.WORKER_SHUTDOWN_GRACE_SECONDS))

        self.is_running = False
        await self.heartbeat.stop()
        await self.executor.cancel_lease_renewals()

        try:
            async with self.session_factory() as session:
                await heartbeat.update_worker_status(session, self.worker_id, WorkerStatus.OFFLINE)
        except Exception as exc:
            logger.error("Failed to mark worker offline: %s", exc)
        logger.info("Worker %s successfully shut down offline.", self.name)
