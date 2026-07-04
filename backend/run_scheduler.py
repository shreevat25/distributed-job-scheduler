#!/usr/bin/env python
"""Promotion scheduler entry point."""

import asyncio
import logging
import signal
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.worker.scheduler import PromotionScheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize session factory and run promotion scheduler loop."""
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting Distributed Job Scheduler Promotion Scheduler...")

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    scheduler = PromotionScheduler(
        session_factory=session_factory,
        interval_seconds=1.0,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, scheduler.stop)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await scheduler.start()
    finally:
        await engine.dispose()
        logger.info("Promotion scheduler terminated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")
        sys.exit(0)
