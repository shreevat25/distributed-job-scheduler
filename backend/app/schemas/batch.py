"""Batch creation request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import JobStatus


class BatchJobItem(BaseModel):
    """Single job within a batch creation request."""

    type: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    idempotency_key: str | None = Field(default=None, max_length=255)
    delay_seconds: int | None = Field(default=None, ge=0)
    max_attempts: int | None = Field(default=None, ge=1)


class BatchCreate(BaseModel):
    """Create batch request — all jobs created atomically."""

    name: str | None = Field(default=None, max_length=255)
    jobs: list[BatchJobItem] = Field(min_length=1, max_length=1000)


class BatchResponse(BaseModel):
    """Batch creation response."""

    id: uuid.UUID
    queue_id: uuid.UUID
    name: str | None
    total_jobs: int
    job_ids: list[uuid.UUID]
    created_at: datetime


class BatchStatusCount(BaseModel):
    """Aggregate count of jobs by status within a batch."""

    status: JobStatus
    count: int


class BatchDetailResponse(BaseModel):
    """Batch detail with real aggregate status counts."""

    id: uuid.UUID
    queue_id: uuid.UUID
    created_by: uuid.UUID
    name: str | None
    total_jobs: int
    status_counts: list[BatchStatusCount]
    created_at: datetime
