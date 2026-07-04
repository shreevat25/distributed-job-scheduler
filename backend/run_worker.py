#!/usr/bin/env python
"""Worker process entry point."""

import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.worker.runner import WorkerRunner

logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize session factory and run worker engine."""
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting Distributed Job Scheduler Worker Process...")

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    runner = WorkerRunner(session_factory=session_factory)

    try:
        await runner.run()
    finally:
        await engine.dispose()
        logger.info("Worker process terminated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
        sys.exit(0)
