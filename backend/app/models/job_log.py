"""Append-only job log model for structured log entries."""

from datetime import datetime

from sqlalchemy import BigInteger, Text, ForeignKey, Index, Enum, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

import uuid
from app.core.enums import LogLevel
from app.db.base import Base


class JobLog(Base):
    """Append-only structured log entry for a job or execution."""

    __tablename__ = "job_logs"
    __table_args__ = (
        Index("ix_job_logs_job_id_created_at", "job_id", "created_at"),
        Index("ix_job_logs_execution_id_created_at", "execution_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    level: Mapped[LogLevel] = mapped_column(
        Enum(
            LogLevel,
            name="log_level_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
