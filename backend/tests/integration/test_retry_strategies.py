"""Integration and validation tests for retry strategies and backoff calculations."""

import pytest
from app.core.enums import RetryStrategy
from app.services.retry_service import calculate_retry_delay


class TestRetryStrategies:
    """Verify all 3 retry formulas, max delay cap, and controlled jitter behavior."""

    def test_fixed_retry_strategy(self):
        """Fixed delay should always return base_delay regardless of attempt number."""
        assert calculate_retry_delay(RetryStrategy.FIXED, 1, 10) == 10.0
        assert calculate_retry_delay(RetryStrategy.FIXED, 2, 10) == 10.0
        assert calculate_retry_delay(RetryStrategy.FIXED, 5, 10) == 10.0

    def test_linear_retry_strategy(self):
        """Linear delay should return base_delay * attempt_number."""
        assert calculate_retry_delay(RetryStrategy.LINEAR, 1, 10) == 10.0
        assert calculate_retry_delay(RetryStrategy.LINEAR, 2, 10) == 20.0
        assert calculate_retry_delay(RetryStrategy.LINEAR, 3, 10) == 30.0

    def test_exponential_retry_strategy(self):
        """Exponential delay should return base_delay * 2^(attempt_number - 1)."""
        assert calculate_retry_delay(RetryStrategy.EXPONENTIAL, 1, 10) == 10.0
        assert calculate_retry_delay(RetryStrategy.EXPONENTIAL, 2, 10) == 20.0
        assert calculate_retry_delay(RetryStrategy.EXPONENTIAL, 3, 10) == 40.0
        assert calculate_retry_delay(RetryStrategy.EXPONENTIAL, 4, 10) == 80.0

    def test_max_delay_cap(self):
        """Calculated delay should never exceed max_delay_seconds when provided."""
        assert calculate_retry_delay(RetryStrategy.EXPONENTIAL, 5, 10, max_delay_seconds=100) == 100.0
        assert calculate_retry_delay(RetryStrategy.LINEAR, 10, 20, max_delay_seconds=50) == 50.0

    def test_jitter_disabled_is_deterministic(self):
        """When jitter is False, subsequent calls return identical deterministic results."""
        res1 = calculate_retry_delay(RetryStrategy.EXPONENTIAL, 3, 10, jitter=False)
        res2 = calculate_retry_delay(RetryStrategy.EXPONENTIAL, 3, 10, jitter=False)
        assert res1 == res2 == 40.0

    def test_jitter_enabled_with_controlled_randomness(self):
        """Verify jitter bounding using controlled random generator functions."""
        # Minimum jitter when rand=0.0 -> offset = delay * 0.1 * (0 - 1) = -10%
        min_delay = calculate_retry_delay(
            RetryStrategy.FIXED, 1, 100, jitter=True, jitter_factor=0.1, random_func=lambda: 0.0
        )
        assert min_delay == 90.0

        # Maximum jitter when rand=1.0 -> offset = delay * 0.1 * (2 - 1) = +10%
        max_delay = calculate_retry_delay(
            RetryStrategy.FIXED, 1, 100, jitter=True, jitter_factor=0.1, random_func=lambda: 1.0
        )
        assert max_delay == 110.0

        # Neutral jitter when rand=0.5 -> offset = 0
        mid_delay = calculate_retry_delay(
            RetryStrategy.FIXED, 1, 100, jitter=True, jitter_factor=0.1, random_func=lambda: 0.5
        )
        assert mid_delay == 100.0
