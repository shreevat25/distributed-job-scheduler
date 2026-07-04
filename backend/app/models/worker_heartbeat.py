"""Worker heartbeat model for health monitoring."""

from datetime import datetime

from sqlalchemy import BigInteger, Integer, Float, ForeignKey, Index, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

import uuid
from app.db.base import Base


class WorkerHeartbeat(Base):
    """Periodic health snapshot from a worker process."""

    __tablename__ = "worker_heartbeats"
    __table_args__ = (
        Index("ix_worker_heartbeats_worker_id_created_at", "worker_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="CASCADE"),
        nullable=False,
    )
    active_job_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    cpu_percent: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    memory_percent: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
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
