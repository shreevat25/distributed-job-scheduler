"""Job request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.enums import JobStatus


class JobCreate(BaseModel):
    """Create job request."""

    type: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    idempotency_key: str | None = Field(default=None, max_length=255)
    max_attempts: int | None = Field(default=None, ge=1)
    delay_seconds: int | None = Field(default=None, ge=0)
    available_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scheduling(self) -> "JobCreate":
        """Reject conflicting scheduling inputs."""
        if self.delay_seconds is not None and self.available_at is not None:
            raise ValueError(
                "Cannot specify both 'delay_seconds' and 'available_at'. Use one."
            )
        return self


class JobResponse(BaseModel):
    """Job response in list views."""

    id: uuid.UUID
    queue_id: uuid.UUID
    batch_id: uuid.UUID | None
    type: str
    payload: dict[str, Any]
    status: JobStatus
    priority: int
    available_at: datetime
    idempotency_key: str | None
    attempt_count: int
    max_attempts: int
    worker_id: uuid.UUID | None
    claim_token: uuid.UUID | None
    lease_version: int
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    result: dict[str, Any] | None
    last_error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClaimRequest(BaseModel):
    """Request to claim jobs from a queue."""

    worker_id: uuid.UUID
    limit: int = Field(default=1, ge=1, le=50)
    lease_duration_seconds: int | None = Field(default=None, ge=5, le=3600)


class ClaimResponse(BaseModel):
    """Response with claimed jobs."""

    claimed_jobs: list[JobResponse]
    claimed_count: int


class JobExecutionResponse(BaseModel):
    """Execution attempt record response."""

    id: uuid.UUID
    job_id: uuid.UUID
    attempt_number: int
    worker_id: uuid.UUID | None
    claim_token: uuid.UUID | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error_type: str | None
    error_message: str | None
    error_details: dict[str, Any] | None
    result: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobLogResponse(BaseModel):
    """Job log record response."""

    id: int
    job_id: uuid.UUID
    execution_id: uuid.UUID | None
    level: str
    message: str
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

