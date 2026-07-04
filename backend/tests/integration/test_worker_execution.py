"""Integration tests for safe deterministic job handlers and worker execution."""

import pytest
from app.worker.handlers import HANDLERS, HandlerError, execute_job_handler


@pytest.mark.asyncio
class TestWorkerExecutionHandlers:
    """Verify safe deterministic handlers and arbitrary code execution rejection."""

    async def test_echo_handler(self):
        payload = {"msg": "test_echo"}
        res = await execute_job_handler("echo", payload, 1)
        assert res == {"echoed": payload}

    async def test_add_handler(self):
        res = await execute_job_handler("add", {"a": 10.5, "b": 4.5}, 1)
        assert res == {"result": 15}

    async def test_sleep_handler_bounded(self):
        # Even if payload requests 100 seconds, handler caps at 10 (we request 0.01 for fast test)
        res = await execute_job_handler("sleep", {"duration": 0.01}, 1)
        assert res["slept_for"] == 0.01

    async def test_fail_handler(self):
        with pytest.raises(HandlerError) as exc_info:
            await execute_job_handler("fail", {"message": "Intentional boom"}, 1)
        assert "Intentional boom" in str(exc_info.value)

    async def test_flaky_handler(self):
        # Configured to fail until attempt 2
        with pytest.raises(HandlerError):
            await execute_job_handler("flaky", {"fail_until_attempt": 2}, 1)
        with pytest.raises(HandlerError):
            await execute_job_handler("flaky", {"fail_until_attempt": 2}, 2)
        res = await execute_job_handler("flaky", {"fail_until_attempt": 2}, 3)
        assert res == {"succeeded_on_attempt": 3}

    async def test_unknown_job_type_rejected_safely(self):
        """Unknown job types must fail safely without arbitrary code execution."""
        with pytest.raises(ValueError) as exc_info:
            await execute_job_handler("os.system('rm -rf /')", {}, 1)
        assert "Unknown job type" in str(exc_info.value)
