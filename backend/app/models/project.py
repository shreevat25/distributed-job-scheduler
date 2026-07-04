"""Project model for grouping queues, policies, and jobs."""

import uuid

from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, Index, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    """A project owned by a single user, containing queues and policies."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_projects_owner_id_name"),
        Index("ix_projects_owner_id", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    queues: Mapped[list["Queue"]] = relationship(back_populates="project", lazy="selectin")  # noqa: F821
    retry_policies: Mapped[list["RetryPolicy"]] = relationship(  # noqa: F821
        back_populates="project", lazy="selectin"
    )
