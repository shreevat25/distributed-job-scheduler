"""Worker request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import WorkerStatus


class WorkerResponse(BaseModel):
    """Worker process response schema."""

    id: uuid.UUID
    name: str
    hostname: str | None
    process_id: int | None
    status: WorkerStatus
    concurrency: int
    started_at: datetime
    last_seen_at: datetime
    stopped_at: datetime | None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")

    model_config = {"from_attributes": True, "populate_by_name": True}
