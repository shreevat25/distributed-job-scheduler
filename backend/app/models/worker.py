"""Worker model for job processing agents."""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, Enum, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import WorkerStatus
from app.db.base import Base


class Worker(Base):
    """A worker process that claims and executes jobs."""

    __tablename__ = "workers"
    __table_args__ = (
        {"comment": "Registered worker processes for job execution"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    hostname: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    process_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[WorkerStatus] = mapped_column(
        Enum(
            WorkerStatus,
            name="worker_status_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=WorkerStatus.STARTING,
        server_default=text("'starting'"),
    )
    concurrency: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
