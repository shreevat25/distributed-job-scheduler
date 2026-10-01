"""Scheduler process loop: promotes due delayed/retry jobs and materializes schedules.

The scheduling logic itself lives in ``app.services.schedule_service``.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services import schedule_service

logger = logging.getLogger(__name__)


class PromotionScheduler:
    """Background scheduler loop for promoting delayed and retried jobs, and materializing schedules."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 1.0,
        batch_limit: int = 100,
    ) -> None:
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.batch_limit = batch_limit
        self.is_running = False

    async def run_once(self) -> tuple[int, int]:
        """Run one scheduling pass. Returns (jobs_promoted, schedules_materialized)."""
        async with self.session_factory() as session:
            promoted = await schedule_service.promote_due_jobs(session, limit=self.batch_limit)
        async with self.session_factory() as session:
            materialized = await schedule_service.materialize_due_schedules(session, limit=self.batch_limit)
        return promoted, materialized

    async def start(self) -> None:
        """Start the promotion loop."""
        self.is_running = True
        logger.info("Starting promotion scheduler loop (interval=%.2fs)...", self.interval_seconds)
        try:
            while self.is_running:
                try:
                    await self.run_once()
                except Exception as exc:
                    logger.error("Error in promotion scheduler loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval_seconds)
        finally:
            logger.info("Promotion scheduler stopped.")

    def stop(self) -> None:
        """Stop the promotion loop."""
        self.is_running = False
