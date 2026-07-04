"""Scheduled job model for future cron/one-time job support."""

import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    Index,
    CheckConstraint,
    Enum,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ScheduleType
from app.db.base import Base, TimestampMixin


class ScheduledJob(Base, TimestampMixin):
    """A recurring or one-time scheduled job definition (future phase)."""

    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        Index("ix_scheduled_jobs_is_active_next_run_at", "is_active", "next_run_at"),
        Index("ix_scheduled_jobs_queue_id", "queue_id"),
        CheckConstraint(
            "(schedule_type = 'one_time' AND run_at IS NOT NULL) OR "
            "(schedule_type = 'cron' AND cron_expression IS NOT NULL)",
            name="schedule_type_fields_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    schedule_type: Mapped[ScheduleType] = mapped_column(
        Enum(
            ScheduleType,
            name="schedule_type_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    run_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    cron_expression: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="UTC",
        server_default=text("'UTC'"),
        nullable=False,
    )
    next_run_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
