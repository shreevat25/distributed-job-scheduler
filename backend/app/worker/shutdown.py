"""Graceful shutdown coordination for worker processes.

Shutdown has two phases:

1. **Draining** — set as soon as shutdown is requested. The claim loop stops
   taking new work, but in-flight jobs keep running.
2. **Stop** — set once the DRAINING status has been recorded. The claim loop
   wakes immediately (instead of finishing its poll sleep), drains active
   tasks within the grace period, and marks the worker OFFLINE.

Separating the two keeps the OFFLINE write strictly after the DRAINING write.
"""

import asyncio
import logging
import signal
from collections.abc import Callable, Collection

logger = logging.getLogger(__name__)


class ShutdownCoordinator:
    """Tracks shutdown state and lets loops sleep until shutdown is requested."""

    def __init__(self) -> None:
        self._draining = False
        self._stop_event = asyncio.Event()

    @property
    def is_draining(self) -> bool:
        """True once shutdown was requested; no new work may be claimed."""
        return self._draining

    @property
    def should_stop(self) -> bool:
        """True once the worker loop should exit and drain."""
        return self._stop_event.is_set()

    def begin_draining(self) -> bool:
        """Enter the draining phase. Returns False if already draining."""
        if self._draining:
            return False
        self._draining = True
        return True

    def signal_stop(self) -> None:
        """Wake any loop waiting in ``wait`` and ask it to exit."""
        self._draining = True
        self._stop_event.set()

    def reset(self) -> None:
        """Clear shutdown state so the worker can run again."""
        self._draining = False
        self._stop_event.clear()

    async def wait(self, timeout: float) -> bool:
        """Sleep up to ``timeout`` seconds, returning early if stop is signalled.

        Returns True if stop was signalled.
        """
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return self._stop_event.is_set()


def install_signal_handlers(callback: Callable[[], None]) -> None:
    """Invoke ``callback`` on SIGINT/SIGTERM (no-op on Windows or outside the main thread)."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, callback)
        except (NotImplementedError, RuntimeError):
            pass


async def drain_tasks(tasks: Collection[asyncio.Task], grace_seconds: float) -> None:
    """Wait up to ``grace_seconds`` for tasks to finish, then cancel the rest."""
    if not tasks:
        return

    logger.info("Waiting up to %ds for %d active tasks to complete...", grace_seconds, len(tasks))
    _, pending = await asyncio.wait(set(tasks), timeout=grace_seconds)
    if pending:
        logger.warning("Grace period expired. Cancelling %d unfinished tasks...", len(pending))
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def cancel_and_wait(tasks: Collection[asyncio.Task]) -> None:
    """Cancel tasks and wait for them to finish unwinding."""
    tasks = [t for t in tasks if t is not None]
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
