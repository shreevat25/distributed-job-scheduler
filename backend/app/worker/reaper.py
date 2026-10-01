"""Reaper process loop: periodically recovers stale workers and expired job leases.

The recovery logic itself lives in ``app.services.recovery_service``.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services import recovery_service

logger = logging.getLogger(__name__)


class ReaperScheduler:
    """Background scheduler loop for reaping stale workers and expired job leases."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 15.0,
        batch_limit: int = 100,
    ) -> None:
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.batch_limit = batch_limit
        self.is_running = False

    async def run_once(self) -> tuple[int, int]:
        """Run one recovery pass. Returns (workers_marked_dead, jobs_recovered)."""
        async with self.session_factory() as session:
            dead = await recovery_service.reap_stale_workers(session)
        async with self.session_factory() as session:
            recovered = await recovery_service.reap_expired_jobs(session, limit=self.batch_limit)
        return dead, recovered

    async def start(self) -> None:
        """Start the reaper loop."""
        self.is_running = True
        logger.info("Starting reaper loop (interval=%.2fs)...", self.interval_seconds)
        try:
            while self.is_running:
                try:
                    await self.run_once()
                except Exception as exc:
                    logger.error("Error in reaper loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval_seconds)
        finally:
            logger.info("Reaper loop stopped.")

    def stop(self) -> None:
        """Stop the reaper loop."""
        self.is_running = False
