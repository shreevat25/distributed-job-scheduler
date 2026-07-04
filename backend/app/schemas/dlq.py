"""DLQ entry request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DLQEntryResponse(BaseModel):
    """Dead-letter queue entry response."""

    id: uuid.UUID
    job_id: uuid.UUID
    queue_id: uuid.UUID
    final_execution_id: uuid.UUID | None
    reason: str
    error_snapshot: dict[str, Any] | None
    attempts: int
    dead_lettered_at: datetime
    retried_at: datetime | None
    retried_by: uuid.UUID | None

    model_config = {"from_attributes": True}
