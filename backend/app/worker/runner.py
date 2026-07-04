"""Distributed worker execution engine and lifecycle runner."""

import asyncio
import logging
import os
import signal
import socket
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.enums import WorkerStatus
from app.models.queue import Queue
from app.services import claim_service
from app.worker import handlers, heartbeat, lifecycle

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
        self.lease_renew_tasks: dict[uuid.UUID, asyncio.Task] = {}

        self.is_running = False
        self.is_draining = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def run(self) -> None:
        """Start worker registration, heartbeat loop, and job claim loop."""
        self.is_running = True
        self.is_draining = False

        # 1. Register worker online
        async with self.session_factory() as session:
            await heartbeat.register_worker(
                session=session,
                worker_id=self.worker_id,
                name=self.name,
                concurrency=self.concurrency,
            )

        # 2. Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 3. Setup signal handlers if running in main thread
        self._setup_signal_handlers()

        logger.info("Worker %s (%s) started polling loop.", self.name, self.worker_id)

        try:
            while self.is_running and not self.is_draining:
                available_slots = self.concurrency - len(self.active_tasks)
                if available_slots <= 0:
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL_MS / 1000.0)
                    continue

                try:
                    await self._poll_and_claim(available_slots)
                except Exception as exc:
                    logger.error("Error during poll and claim loop: %s", exc, exc_info=True)

                await asyncio.sleep(settings.WORKER_POLL_INTERVAL_MS / 1000.0)
        finally:
            await self._shutdown_cleanup()

    async def shutdown(self) -> None:
        """Trigger graceful shutdown."""
        if not self.is_running or self.is_draining:
            return

        logger.info("Worker %s received shutdown signal. Entering draining state...", self.name)
        self.is_draining = True
        self._shutdown_event.set()

        try:
            async with self.session_factory() as session:
                await heartbeat.update_worker_status(session, self.worker_id, WorkerStatus.DRAINING)
        except Exception as exc:
            logger.warning("Failed to update worker status to draining: %s", exc)

    def _setup_signal_handlers(self) -> None:
        """Register SIGTERM and SIGINT signal handlers."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
            except (NotImplementedError, RuntimeError):
                # Windows or not main thread
                pass

    async def _poll_and_claim(self, available_slots: int) -> None:
        """Query unpaused queues and claim up to available_slots jobs."""
        async with self.session_factory() as session:
            stmt = select(Queue.id).where(Queue.is_paused == False)
            queue_ids = (await session.execute(stmt)).scalars().all()

        for q_id in queue_ids:
            if len(self.active_tasks) >= self.concurrency:
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
                    self._execute_job(
                        job_id=job.id,
                        job_type=job.type,
                        payload=job.payload,
                        claim_token=job.claim_token,
                    )
                )
                self.active_tasks.add(task)
                task.add_done_callback(lambda t: self._on_task_done(t))

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Callback when an execution task completes."""
        self.active_tasks.discard(task)
        self.semaphore.release()

    async def _execute_job(
        self,
        job_id: uuid.UUID,
        job_type: str,
        payload: dict[str, Any],
        claim_token: uuid.UUID,
    ) -> None:
        """Execute a claimed job in its own independent database session."""
        # 1. Start execution transactionally
        async with self.session_factory() as session:
            try:
                job, execution = await lifecycle.start_execution(
                    session=session,
                    job_id=job_id,
                    worker_id=self.worker_id,
                    claim_token=claim_token,
                )
                await session.commit()
                attempt_number = job.attempt_count
            except Exception as exc:
                logger.warning("Failed to start execution for job %s: %s", job_id, exc)
                await session.rollback()
                return

        # 2. Start background lease renewal task
        renew_task = asyncio.create_task(self._lease_renew_loop(job_id, claim_token))
        self.lease_renew_tasks[job_id] = renew_task

        # 3. Run handler
        try:
            result = await handlers.execute_job_handler(job_type, payload, attempt_number)
            # Authoritatively complete
            async with self.session_factory() as session:
                await lifecycle.complete_job(
                    session=session,
                    job_id=job_id,
                    worker_id=self.worker_id,
                    claim_token=claim_token,
                    result=result,
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Job %s handler failed on attempt %d: %s", job_id, attempt_number, exc)
            # Transactional fail (retry or DLQ)
            async with self.session_factory() as session:
                try:
                    await lifecycle.fail_job(
                        session=session,
                        job_id=job_id,
                        worker_id=self.worker_id,
                        claim_token=claim_token,
                        exc=exc,
                    )
                    await session.commit()
                except Exception as fail_exc:
                    logger.error("Error failing job %s: %s", job_id, fail_exc)
                    await session.rollback()
        finally:
            renew_task.cancel()
            self.lease_renew_tasks.pop(job_id, None)
            await asyncio.gather(renew_task, return_exceptions=True)

    async def _lease_renew_loop(self, job_id: uuid.UUID, claim_token: uuid.UUID) -> None:
        """Periodically renew lease for an active job."""
        interval = float(settings.JOB_LEASE_RENEW_INTERVAL_SECONDS)
        while True:
            await asyncio.sleep(interval)
            async with self.session_factory() as session:
                try:
                    renewed = await lifecycle.renew_lease(
                        session=session,
                        job_id=job_id,
                        worker_id=self.worker_id,
                        claim_token=claim_token,
                        lease_duration_seconds=settings.JOB_LEASE_DURATION_SECONDS,
                    )
                    if not renewed:
                        logger.warning("Lease renewal failed for job %s (ownership lost). Stopping renewal.", job_id)
                        break
                except Exception as exc:
                    logger.warning("Transient error renewing lease for job %s: %s", job_id, exc)
                    await session.rollback()

    async def _heartbeat_loop(self) -> None:
        """Periodically record worker heartbeat."""
        interval = float(settings.WORKER_HEARTBEAT_INTERVAL_SECONDS)
        while self.is_running:
            await asyncio.sleep(interval)
            async with self.session_factory() as session:
                try:
                    await heartbeat.record_heartbeat(
                        session=session,
                        worker_id=self.worker_id,
                        active_job_count=len(self.active_tasks),
                    )
                except Exception:
                    # Logged inside record_heartbeat
                    pass

    async def _shutdown_cleanup(self) -> None:
        """Perform graceful shutdown draining and offline marking."""
        logger.info("Starting shutdown cleanup for worker %s...", self.name)
        if self.active_tasks:
            logger.info(
                "Waiting up to %ds for %d active tasks to complete...",
                settings.WORKER_SHUTDOWN_GRACE_SECONDS,
                len(self.active_tasks),
            )
            done, pending = await asyncio.wait(
                self.active_tasks,
                timeout=float(settings.WORKER_SHUTDOWN_GRACE_SECONDS),
            )
            if pending:
                logger.warning("Grace period expired. Cancelling %d unfinished tasks...", len(pending))
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        self.is_running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)

        for r_task in self.lease_renew_tasks.values():
            if not r_task.done():
                r_task.cancel()
        if self.lease_renew_tasks:
            await asyncio.gather(*self.lease_renew_tasks.values(), return_exceptions=True)

        try:
            async with self.session_factory() as session:
                await heartbeat.update_worker_status(session, self.worker_id, WorkerStatus.OFFLINE)
        except Exception as exc:
            logger.error("Failed to mark worker offline: %s", exc)
        logger.info("Worker %s successfully shut down offline.", self.name)
