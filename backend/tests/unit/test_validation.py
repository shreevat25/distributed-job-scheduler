"""Unit tests for Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from app.core.enums import RetryStrategy
from app.schemas.auth import RegisterRequest
from app.schemas.job import JobCreate
from app.schemas.queue import QueueCreate
from app.schemas.retry_policy import RetryPolicyCreate


class TestRegisterRequestValidation:
    """Test email and password validation for registration."""

    def test_valid_registration(self):
        req = RegisterRequest(email="user@example.com", password="securepass123")
        assert req.email == "user@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="securepass123")

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="short")

    def test_minimum_password_length(self):
        req = RegisterRequest(email="user@example.com", password="12345678")
        assert len(req.password) == 8

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="")


class TestQueueCreateValidation:
    """Test queue creation validation."""

    def test_valid_queue(self):
        q = QueueCreate(name="my-queue", concurrency_limit=5)
        assert q.concurrency_limit == 5

    def test_zero_concurrency_rejected(self):
        with pytest.raises(ValidationError):
            QueueCreate(name="my-queue", concurrency_limit=0)

    def test_negative_concurrency_rejected(self):
        with pytest.raises(ValidationError):
            QueueCreate(name="my-queue", concurrency_limit=-1)

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            QueueCreate(name="", concurrency_limit=5)


class TestRetryPolicyCreateValidation:
    """Test retry policy validation constraints."""

    def test_valid_policy(self):
        p = RetryPolicyCreate(
            name="default",
            strategy=RetryStrategy.EXPONENTIAL,
            max_attempts=5,
            base_delay_seconds=10,
            jitter_factor=0.5,
        )
        assert p.max_attempts == 5

    def test_zero_max_attempts_rejected(self):
        with pytest.raises(ValidationError):
            RetryPolicyCreate(
                name="bad",
                strategy=RetryStrategy.FIXED,
                max_attempts=0,
                base_delay_seconds=10,
            )

    def test_negative_delay_rejected(self):
        with pytest.raises(ValidationError):
            RetryPolicyCreate(
                name="bad",
                strategy=RetryStrategy.FIXED,
                max_attempts=3,
                base_delay_seconds=-1,
            )

    def test_jitter_factor_above_one_rejected(self):
        with pytest.raises(ValidationError):
            RetryPolicyCreate(
                name="bad",
                strategy=RetryStrategy.FIXED,
                max_attempts=3,
                base_delay_seconds=10,
                jitter_factor=1.5,
            )

    def test_jitter_factor_negative_rejected(self):
        with pytest.raises(ValidationError):
            RetryPolicyCreate(
                name="bad",
                strategy=RetryStrategy.FIXED,
                max_attempts=3,
                base_delay_seconds=10,
                jitter_factor=-0.1,
            )

    def test_max_delay_less_than_base_rejected(self):
        with pytest.raises(ValidationError):
            RetryPolicyCreate(
                name="bad",
                strategy=RetryStrategy.EXPONENTIAL,
                max_attempts=3,
                base_delay_seconds=30,
                max_delay_seconds=10,
            )


class TestJobCreateValidation:
    """Test job creation validation."""

    def test_valid_immediate_job(self):
        j = JobCreate(type="email.send", payload={"to": "user@test.com"})
        assert j.type == "email.send"
        assert j.delay_seconds is None
        assert j.available_at is None

    def test_empty_type_rejected(self):
        with pytest.raises(ValidationError):
            JobCreate(type="", payload={})

    def test_conflicting_scheduling_rejected(self):
        """Cannot specify both delay_seconds and available_at."""
        from datetime import datetime, UTC

        with pytest.raises(ValidationError):
            JobCreate(
                type="test",
                payload={},
                delay_seconds=60,
                available_at=datetime.now(UTC),
            )

    def test_negative_delay_rejected(self):
        with pytest.raises(ValidationError):
            JobCreate(type="test", payload={}, delay_seconds=-10)

    def test_valid_delayed_job(self):
        j = JobCreate(type="test", payload={}, delay_seconds=300)
        assert j.delay_seconds == 300
