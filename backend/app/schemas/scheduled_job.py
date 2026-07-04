import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import ScheduleType


class ScheduledJobCreate(BaseModel):
    queue_id: uuid.UUID
    name: str = Field(..., max_length=255)
    job_type: str = Field(..., max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    schedule_type: ScheduleType
    run_at: Optional[datetime] = None
    cron_expression: Optional[str] = Field(None, max_length=100)
    timezone: str = Field("UTC", max_length=50)


class ScheduledJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    queue_id: uuid.UUID
    name: str
    job_type: str
    payload: dict[str, Any]
    schedule_type: ScheduleType
    run_at: Optional[datetime]
    cron_expression: Optional[str]
    timezone: str
    next_run_at: datetime
    last_run_at: Optional[datetime]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
