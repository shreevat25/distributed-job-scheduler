"""SQLAlchemy declarative base and model imports for metadata registration."""

import uuid
from datetime import datetime, UTC

from sqlalchemy import MetaData, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import TIMESTAMP


# Naming convention for constraints to enable reliable Alembic autogenerate
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    metadata = MetaData(naming_convention=convention)


class TimestampMixin:
    """Mixin providing timezone-aware created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(UTC),
    )


# Import all models so that Base.metadata knows about them.
# This is critical for Alembic autogenerate to discover all tables.
from app.models.user import User  # noqa: E402, F401
from app.models.project import Project  # noqa: E402, F401
from app.models.retry_policy import RetryPolicy  # noqa: E402, F401
from app.models.queue import Queue  # noqa: E402, F401
from app.models.job_batch import JobBatch  # noqa: E402, F401
from app.models.worker import Worker  # noqa: E402, F401
from app.models.job import Job  # noqa: E402, F401
from app.models.job_execution import JobExecution  # noqa: E402, F401
from app.models.job_log import JobLog  # noqa: E402, F401
from app.models.scheduled_job import ScheduledJob  # noqa: E402, F401
from app.models.worker_heartbeat import WorkerHeartbeat  # noqa: E402, F401
from app.models.dlq_entry import DLQEntry  # noqa: E402, F401
