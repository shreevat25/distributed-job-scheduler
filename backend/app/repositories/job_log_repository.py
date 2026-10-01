"""Job log repository — append-only structured job logs."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LogLevel
from app.models.job_log import JobLog


def add_log(
    session: AsyncSession,
    job_id: uuid.UUID,
    level: LogLevel,
    message: str,
    execution_id: uuid.UUID | None = None,
) -> JobLog:
    """Stage a log row in the current transaction (flushed with the caller's work)."""
    log = JobLog(
        job_id=job_id,
        execution_id=execution_id,
        level=level,
        message=message,
    )
    session.add(log)
    return log


async def list_for_job(session: AsyncSession, job_id: uuid.UUID) -> list[JobLog]:
    """List a job's logs in chronological order."""
    stmt = select(JobLog).where(JobLog.job_id == job_id).order_by(JobLog.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())
