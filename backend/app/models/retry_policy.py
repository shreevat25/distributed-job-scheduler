"""Retry policy model for configurable backoff strategies."""

import uuid

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    TIMESTAMP,
    text,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RetryStrategy
from app.db.base import Base, TimestampMixin


class RetryPolicy(Base, TimestampMixin):
    """Configurable retry backoff policy attached to a project."""

    __tablename__ = "retry_policies"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_retry_policies_project_id_name"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_gte_1"),
        CheckConstraint("base_delay_seconds >= 0", name="base_delay_seconds_gte_0"),
        CheckConstraint("jitter_factor >= 0", name="jitter_factor_gte_0"),
        CheckConstraint("jitter_factor <= 1", name="jitter_factor_lte_1"),
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
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    strategy: Mapped[RetryStrategy] = mapped_column(
        Enum(
            RetryStrategy,
            name="retry_strategy_enum",
            create_constraint=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    base_delay_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    max_delay_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    jitter: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    jitter_factor: Mapped[float] = mapped_column(
        Float,
        default=0.1,
        server_default=text("0.1"),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="retry_policies")  # noqa: F821
