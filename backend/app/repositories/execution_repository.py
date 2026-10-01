"""Job execution repository — per-attempt execution records."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_execution import JobExecution
from app.repositories.expressions import db_now, execution_elapsed_ms


async def create(session: AsyncSession, execution: JobExecution) -> JobExecution:
    """Persist a new execution (flushes so execution.id is available)."""
    session.add(execution)
    await session.flush()
    return execution


async def get_attempt_for_update(
    session: AsyncSession,
    job_id: uuid.UUID,
    attempt_number: int,
    *,
    running_only: bool = False,
) -> JobExecution | None:
    """Lock and fetch the execution row for a specific attempt of a job."""
    stmt = select(JobExecution).where(
        JobExecution.job_id == job_id,
        JobExecution.attempt_number == attempt_number,
    )
    if running_only:
        stmt = stmt.where(JobExecution.status == "running")
    result = await session.execute(stmt.with_for_update())
    return result.scalar_one_or_none()


async def list_for_job(session: AsyncSession, job_id: uuid.UUID) -> list[JobExecution]:
    """List a job's execution attempts in attempt order."""
    stmt = (
        select(JobExecution)
        .where(JobExecution.job_id == job_id)
        .order_by(JobExecution.attempt_number.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def mark_finished(
    execution: JobExecution,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    error_details: dict[str, Any] | None = None,
) -> None:
    """Finalize an execution, stamping finish time and duration from the DB clock."""
    execution.status = status
    if result is not None:
        execution.result = result
    if error_type is not None:
        execution.error_type = error_type
    if error_message is not None:
        execution.error_message = error_message
    if error_details is not None:
        execution.error_details = error_details
    execution.finished_at = db_now()
    execution.duration_ms = execution_elapsed_ms()
