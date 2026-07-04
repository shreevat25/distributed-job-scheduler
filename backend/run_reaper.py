#!/usr/bin/env python
"""Reaper process entry point."""

import asyncio
import logging
import signal
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.worker.reaper import ReaperScheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize session factory and run reaper loop."""
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting Distributed Job Scheduler Reaper Process...")

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    reaper = ReaperScheduler(
        session_factory=session_factory,
        interval_seconds=float(settings.REAPER_INTERVAL_SECONDS),
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, reaper.stop)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await reaper.start()
    finally:
        await engine.dispose()
        logger.info("Reaper process terminated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Reaper stopped by user.")
        sys.exit(0)
