"""Queue request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class QueueCreate(BaseModel):
    """Create queue request."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: int = 0
    concurrency_limit: int = Field(gt=0)
    retry_policy_id: uuid.UUID | None = None


class QueueUpdate(BaseModel):
    """Partial update queue request."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: int | None = None
    concurrency_limit: int | None = Field(default=None, gt=0)
    retry_policy_id: uuid.UUID | None = None


class QueueResponse(BaseModel):
    """Queue response."""

    id: uuid.UUID
    project_id: uuid.UUID
    retry_policy_id: uuid.UUID | None
    name: str
    description: str | None
    priority: int
    concurrency_limit: int
    is_paused: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QueueStatsResponse(BaseModel):
    """Real database-counted queue statistics by status."""

    queue_id: uuid.UUID
    queued: int = 0
    scheduled: int = 0
    claimed: int = 0
    running: int = 0
    retry_wait: int = 0
    completed: int = 0
    failed: int = 0
    dead_lettered: int = 0
    total: int = 0
