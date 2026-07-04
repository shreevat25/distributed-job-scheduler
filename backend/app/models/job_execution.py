"""Job execution history — one row per attempt, never overwritten."""

import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobExecution(Base):
    """Immutable record of a single job execution attempt."""

    __tablename__ = "job_executions"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number", name="uq_job_executions_job_id_attempt_number"),
        Index("ix_job_executions_job_id_attempt_number", "job_id", "attempt_number"),
        Index("ix_job_executions_worker_id_started_at", "worker_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="SET NULL"),
        nullable=True,
    )
    claim_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    error_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    result: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="executions")  # noqa: F821
