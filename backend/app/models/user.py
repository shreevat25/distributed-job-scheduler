"""User model for authentication and ownership."""

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Application user with secure password storage."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )

    # Relationships
    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        back_populates="owner",
        lazy="selectin",
    )

    @staticmethod
    def normalize_email(email: str) -> str:
        """Normalize email: lowercase and strip whitespace."""
        return email.strip().lower()
