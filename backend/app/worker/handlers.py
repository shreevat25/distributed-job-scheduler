"""Safe deterministic job handlers for worker execution."""

import asyncio
from typing import Any, Callable, Coroutine


class HandlerError(Exception):
    """Exception raised by handlers when execution fails."""
    pass


async def handle_echo(payload: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    """Echo the payload back in the result."""
    return {"echoed": payload}


async def handle_add(payload: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    """Add two numbers 'a' and 'b' from payload."""
    try:
        a = float(payload.get("a", 0))
        b = float(payload.get("b", 0))
        # Return int if both are integers
        if a.is_integer() and b.is_integer():
            res = int(a) + int(b)
        else:
            res = a + b
        return {"result": res}
    except (ValueError, TypeError) as exc:
        raise HandlerError(f"Invalid parameters for add handler: {exc}") from exc


async def handle_sleep(payload: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    """Sleep for a bounded duration (max 10 seconds)."""
    try:
        duration = float(payload.get("duration", 1.0))
    except (ValueError, TypeError):
        duration = 1.0

    # Bound duration between 0 and 10 seconds for safety
    duration = max(0.0, min(duration, 10.0))
    await asyncio.sleep(duration)
    return {"slept_for": duration}


async def handle_fail(payload: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    """Always fail with an exception."""
    msg = payload.get("message", "Intentional failure from fail handler")
    raise HandlerError(str(msg))


async def handle_flaky(payload: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    """Fail until attempt_number > fail_until_attempt."""
    try:
        fail_until = int(payload.get("fail_until_attempt", 1))
    except (ValueError, TypeError):
        fail_until = 1

    if attempt_number <= fail_until:
        raise HandlerError(f"Flaky failure on attempt {attempt_number} (configured to fail until attempt {fail_until})")
    
    return {"succeeded_on_attempt": attempt_number}


# Registry of known safe deterministic handlers
HANDLERS: dict[str, Callable[[dict[str, Any], int], Coroutine[Any, Any, dict[str, Any]]]] = {
    "echo": handle_echo,
    "add": handle_add,
    "sleep": handle_sleep,
    "fail": handle_fail,
    "flaky": handle_flaky,
}


async def execute_job_handler(job_type: str, payload: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    """Execute the handler for the given job type.

    Raises ValueError if job_type is unknown.
    Raises HandlerError or Exception if execution fails.
    """
    handler = HANDLERS.get(job_type.lower())
    if not handler:
        raise ValueError(f"Unknown job type: '{job_type}'. Arbitrary code execution is disallowed.")
    
    return await handler(payload, attempt_number)
