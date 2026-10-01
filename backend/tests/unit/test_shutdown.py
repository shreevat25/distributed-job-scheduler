"""Unit tests for worker shutdown coordination (no database required)."""

import asyncio
import time

import pytest

from app.worker.shutdown import ShutdownCoordinator, cancel_and_wait, drain_tasks


@pytest.mark.asyncio
class TestShutdownCoordinator:
    async def test_wait_returns_early_when_stop_signalled(self):
        coordinator = ShutdownCoordinator()
        asyncio.get_running_loop().call_later(0.05, coordinator.signal_stop)

        started = time.monotonic()
        stopped = await coordinator.wait(5.0)

        assert stopped is True
        assert time.monotonic() - started < 1.0

    async def test_wait_times_out_without_stop(self):
        coordinator = ShutdownCoordinator()
        assert await coordinator.wait(0.01) is False
        assert not coordinator.should_stop

    async def test_draining_precedes_stop(self):
        coordinator = ShutdownCoordinator()

        assert coordinator.begin_draining() is True
        assert coordinator.is_draining
        assert not coordinator.should_stop
        # Second request is a no-op
        assert coordinator.begin_draining() is False

        coordinator.signal_stop()
        assert coordinator.should_stop

        coordinator.reset()
        assert not coordinator.is_draining
        assert not coordinator.should_stop


@pytest.mark.asyncio
class TestDrainTasks:
    async def test_finished_tasks_complete_within_grace(self):
        task = asyncio.create_task(asyncio.sleep(0.01, result="done"))
        await drain_tasks({task}, grace_seconds=1.0)
        assert task.result() == "done"

    async def test_unfinished_tasks_cancelled_after_grace(self):
        task = asyncio.create_task(asyncio.sleep(10))
        await drain_tasks({task}, grace_seconds=0.01)
        assert task.cancelled()

    async def test_cancel_and_wait_ignores_none(self):
        task = asyncio.create_task(asyncio.sleep(10))
        await cancel_and_wait([task, None])
        assert task.cancelled()
