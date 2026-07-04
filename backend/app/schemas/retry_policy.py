"""Retry policy request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.enums import RetryStrategy


class RetryPolicyCreate(BaseModel):
    """Create retry policy request."""

    name: str = Field(min_length=1, max_length=255)
    strategy: RetryStrategy
    max_attempts: int = Field(ge=1)
    base_delay_seconds: int = Field(ge=0)
    max_delay_seconds: int | None = Field(default=None, ge=0)
    jitter: bool = True
    jitter_factor: float = Field(default=0.1, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_delays(self) -> "RetryPolicyCreate":
        """Ensure max_delay_seconds >= base_delay_seconds when both specified."""
        if (
            self.max_delay_seconds is not None
            and self.max_delay_seconds < self.base_delay_seconds
        ):
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")
        return self


class RetryPolicyUpdate(BaseModel):
    """Partial update retry policy request."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    strategy: RetryStrategy | None = None
    max_attempts: int | None = Field(default=None, ge=1)
    base_delay_seconds: int | None = Field(default=None, ge=0)
    max_delay_seconds: int | None = Field(default=None, ge=0)
    jitter: bool | None = None
    jitter_factor: float | None = Field(default=None, ge=0.0, le=1.0)


class RetryPolicyResponse(BaseModel):
    """Retry policy response."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    strategy: RetryStrategy
    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int | None
    jitter: bool
    jitter_factor: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
