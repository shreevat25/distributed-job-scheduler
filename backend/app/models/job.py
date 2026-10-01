"""Job model — the central entity of the scheduling system."""

import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    ForeignKey,
    Index,
    Enum,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import JobStatus
from app.db.base import Base, TimestampMixin


class Job(Base, TimestampMixin):
    """A schedulable unit of work within a queue."""

    __tablename__ = "jobs"
    __table_args__ = (
        # Primary claim query index: eligible jobs ordered for claiming
        Index(
            "ix_jobs_claim_query",
            "queue_id",
            "status",
            "available_at",
            text("priority DESC"),
            "created_at",
        ),
        # Worker active job lookup
        Index("ix_jobs_worker_id_status", "worker_id", "status"),
        # Promotion scan: scheduled/retry_wait jobs that have become due
        Index(
            "ix_jobs_due_for_promotion",
            "available_at",
            postgresql_where=text("status IN ('scheduled', 'retry_wait')"),
        ),
        # Lease expiry scan
        Index("ix_jobs_status_lease_expires_at", "status", "lease_expires_at"),
        # Queue timeline
        Index("ix_jobs_queue_id_created_at", "queue_id", "created_at"),
        # Batch lookup
        Index("ix_jobs_batch_id", "batch_id"),
        # Partial unique index for idempotency — only where key is not null
        Index(
            "ix_jobs_queue_id_idempotency_key",
            "queue_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
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
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default=text("'queued'"),
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    max_attempts: Mapped[int] = mapped_column(
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
    lease_version: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    result: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    last_error: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    queue: Mapped["Queue"] = relationship(back_populates="jobs")  # noqa: F821
    batch: Mapped["JobBatch | None"] = relationship(back_populates="jobs")  # noqa: F821
    executions: Mapped[list["JobExecution"]] = relationship(  # noqa: F821
        back_populates="job", lazy="noload"
    )
