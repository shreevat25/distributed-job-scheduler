"""Queue model for job scheduling with concurrency limits."""

import uuid

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Queue(Base, TimestampMixin):
    """A named queue within a project, with concurrency limits and pause control."""

    __tablename__ = "queues"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_queues_project_id_name"),
        CheckConstraint("concurrency_limit > 0", name="concurrency_limit_gt_0"),
        Index("ix_queues_project_id", "project_id"),
        Index("ix_queues_project_id_is_paused", "project_id", "is_paused"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    retry_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retry_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    concurrency_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    is_paused: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="queues")  # noqa: F821
    # Note on lazy="selectin": Under asyncpg/SQLAlchemy 2.0, standard lazy loading raises MissingGreenlet
    # because it attempts synchronous I/O. Using selectin eager loading automatically issues an
    # additional SELECT query within the same async transaction immediately after loading the queue,
    # making queue.retry_policy safely accessible without async greenlet errors.
    retry_policy: Mapped["RetryPolicy | None"] = relationship(lazy="selectin")  # noqa: F821
    jobs: Mapped[list["Job"]] = relationship(back_populates="queue", lazy="noload")  # noqa: F821
