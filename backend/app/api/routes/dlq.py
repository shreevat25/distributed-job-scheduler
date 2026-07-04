"""DLQ API routes — listing, detail, and manual retry."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_dlq_entry
from app.core.enums import JobStatus, LogLevel
from app.core.exceptions import ConflictError, NotFoundError
from app.models.dlq_entry import DLQEntry
from app.models.job import Job
from app.models.job_log import JobLog
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.schemas.dlq import DLQEntryResponse

router = APIRouter(tags=["dlq"])


@router.get(
    "/dlq",
    response_model=list[DLQEntryResponse],
    summary="List dead-letter queue entries",
)
async def list_dlq_entries(
    queue_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[DLQEntryResponse]:
    """List dead-letter queue entries for projects owned by the current user."""
    stmt = (
        select(DLQEntry)
        .join(Queue, DLQEntry.queue_id == Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .where(Project.owner_id == current_user.id)
    )
    if queue_id:
        stmt = stmt.where(DLQEntry.queue_id == queue_id)
    stmt = stmt.order_by(DLQEntry.dead_lettered_at.desc())
    result = await session.execute(stmt)
    entries = result.scalars().all()
    return [DLQEntryResponse.model_validate(e) for e in entries]


@router.get(
    "/dlq/{id}",
    response_model=DLQEntryResponse,
    summary="Get DLQ entry details",
)
async def get_dlq_entry(
    entry: DLQEntry = Depends(get_owned_dlq_entry),
) -> DLQEntryResponse:
    """Get details of a specific dead-letter queue entry."""
    return DLQEntryResponse.model_validate(entry)


@router.post(
    "/dlq/{id}/retry",
    response_model=DLQEntryResponse,
    summary="Retry a dead-lettered job",
)
async def retry_dlq_job(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DLQEntryResponse:
    """Manually retry a dead-lettered job transactionally and concurrency-safely.

    - Resets job attempt_count to 0
    - Preserves all historical JobExecution rows
    - Requeues job
    - Marks DLQ entry retried_at and retried_by
    """
    stmt = (
        select(DLQEntry)
        .join(Queue, DLQEntry.queue_id == Queue.id)
        .join(Project, Queue.project_id == Project.id)
        .where(
            DLQEntry.id == id,
            Project.owner_id == current_user.id,
        )
        .with_for_update()
    )
    dlq_entry = (await session.execute(stmt)).scalar_one_or_none()
    if not dlq_entry:
        raise NotFoundError("DLQEntry", str(id))

    if dlq_entry.retried_at is not None:
        raise ConflictError("DLQ entry has already been retried")

    job_stmt = select(Job).where(Job.id == dlq_entry.job_id).with_for_update()
    job = (await session.execute(job_stmt)).scalar_one_or_none()
    if not job:
        raise NotFoundError("Job", str(dlq_entry.job_id))

    # Reset job attempt_count to 0 and requeue
    job.attempt_count = 0
    job.status = JobStatus.QUEUED
    job.available_at = text("NOW()")
    job.failed_at = None
    job.worker_id = None
    job.claim_token = None
    job.claimed_at = None
    job.lease_expires_at = None

    # Mark DLQ entry
    dlq_entry.retried_at = text("NOW()")
    dlq_entry.retried_by = current_user.id

    # Append job log
    log = JobLog(
        job_id=job.id,
        level=LogLevel.INFO,
        message=f"Job manually retried from DLQ by user {current_user.id} (attempt count reset to 0)",
    )
    session.add(log)

    await session.commit()
    await session.refresh(dlq_entry)
    return DLQEntryResponse.model_validate(dlq_entry)
