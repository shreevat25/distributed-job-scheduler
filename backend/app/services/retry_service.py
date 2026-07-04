"""Pure retry math and delay calculation service."""

import random
from typing import Callable, Optional

from app.core.enums import RetryStrategy


def calculate_retry_delay(
    strategy: RetryStrategy | str,
    attempt_number: int,
    base_delay_seconds: int,
    max_delay_seconds: Optional[int] = None,
    jitter: bool = False,
    jitter_factor: float = 0.1,
    random_func: Optional[Callable[[], float]] = None,
) -> float:
    """Calculate the retry delay in seconds for a failed job attempt.

    Args:
        strategy: 'fixed', 'linear', or 'exponential'
        attempt_number: The attempt number that just failed (e.g., 1 for attempt 1 failing)
        base_delay_seconds: Base delay in seconds
        max_delay_seconds: Optional cap on the calculated delay
        jitter: Whether to apply randomized jitter
        jitter_factor: Fraction of jitter to apply (0.0 to 1.0)
        random_func: Optional random generator function returning float in [0.0, 1.0) for testing

    Returns:
        Delay in seconds as a float.
    """
    if attempt_number < 1:
        attempt_number = 1

    if strategy == RetryStrategy.FIXED or strategy == "fixed":
        delay = float(base_delay_seconds)
    elif strategy == RetryStrategy.LINEAR or strategy == "linear":
        delay = float(base_delay_seconds * attempt_number)
    elif strategy == RetryStrategy.EXPONENTIAL or strategy == "exponential":
        delay = float(base_delay_seconds * (2 ** (attempt_number - 1)))
    else:
        delay = float(base_delay_seconds)

    if max_delay_seconds is not None and delay > max_delay_seconds:
        delay = float(max_delay_seconds)

    if jitter and jitter_factor > 0.0:
        rand = random_func() if random_func is not None else random.random()
        # Jitter bounded by jitter_factor: [-delay * jitter_factor, +delay * jitter_factor]
        offset = delay * jitter_factor * (2.0 * rand - 1.0)
        delay = max(0.0, delay + offset)

    return round(delay, 4)
