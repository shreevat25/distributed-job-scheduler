"""Job API routes — creation, listing, detail, and claiming."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_job, get_owned_queue, get_user_queue_ids
from app.core.enums import JobStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.queue import Queue
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.job import (
    ClaimRequest,
    ClaimResponse,
    JobCreate,
    JobExecutionResponse,
    JobLogResponse,
    JobResponse,
)
from app.services import claim_service, job_service

router = APIRouter(tags=["jobs"])


@router.post(
    "/queues/{queue_id}/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job",
)
async def create_job(
    data: JobCreate,
    queue: Queue = Depends(get_owned_queue),
    session: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Create a job in a queue.

    - **Immediate**: status=queued, available_at=now (default)
    - **Delayed**: if `delay_seconds` or future `available_at` is supplied,
      status=scheduled, available_at=future

    Cannot specify both `delay_seconds` and `available_at`.

    If `idempotency_key` is provided and a matching job exists:
    - Same type/payload: returns the existing job (idempotent)
    - Different type/payload: returns 409 IDEMPOTENCY_CONFLICT
    """
    job, is_new = await job_service.create_job(session, queue, data)
    response = JobResponse.model_validate(job)
    return response


@router.get(
    "/jobs",
    response_model=PaginatedResponse[JobResponse],
    summary="List jobs with filters",
)
async def list_jobs(
    queue_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    batch_id: uuid.UUID | None = Query(default=None),
    type: str | None = Query(default=None),
    min_priority: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    allowed_queue_ids: list[uuid.UUID] = Depends(get_user_queue_ids),
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[JobResponse]:
    """List jobs with filtering and pagination.

    All jobs are authorization-scoped — only jobs in queues owned by
    the current user's projects are returned.
    """
    return await job_service.list_jobs_paginated(
        session,
        allowed_queue_ids=allowed_queue_ids,
        queue_id=queue_id,
        status=status_filter,
        batch_id=batch_id,
        job_type=type,
        min_priority=min_priority,
        page=page,
        limit=limit,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get job details",
)
async def get_job(
    job_id: uuid.UUID,
    allowed_queue_ids: list[uuid.UUID] = Depends(get_user_queue_ids),
    session: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Get a job by ID.

    Authorization enforced through: job → queue → project → owner.
    """
    job = await job_service.get_job_authorized(
        session, job_id, uuid.uuid4(), allowed_queue_ids
    )
    return JobResponse.model_validate(job)


@router.post(
    "/queues/{queue_id}/claim",
    response_model=ClaimResponse,
    summary="Claim jobs from a queue",
)
async def claim_jobs(
    data: ClaimRequest,
    queue: Queue = Depends(get_owned_queue),
    session: AsyncSession = Depends(get_db),
) -> ClaimResponse:
    """Atomically claim jobs from a queue.

    Uses PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` for correctness.
    Enforces the queue's concurrency limit.
    """
    claimed = await claim_service.claim_jobs(
        session,
        queue_id=queue.id,
        worker_id=data.worker_id,
        requested_limit=data.limit,
        lease_duration_seconds=data.lease_duration_seconds,
    )
    return ClaimResponse(
        claimed_jobs=[JobResponse.model_validate(j) for j in claimed],
        claimed_count=len(claimed),
    )


@router.get(
    "/jobs/{job_id}/executions",
    response_model=list[JobExecutionResponse],
    summary="List job execution attempts",
)
async def list_job_executions(
    job: Job = Depends(get_owned_job),
    session: AsyncSession = Depends(get_db),
) -> list[JobExecutionResponse]:
    """List all execution attempt records for a job."""
    stmt = select(JobExecution).where(JobExecution.job_id == job.id).order_by(JobExecution.attempt_number.asc())
    result = await session.execute(stmt)
    executions = result.scalars().all()
    return [JobExecutionResponse.model_validate(e) for e in executions]


@router.get(
    "/jobs/{job_id}/logs",
    response_model=list[JobLogResponse],
    summary="List job logs",
)
async def list_job_logs(
    job: Job = Depends(get_owned_job),
    session: AsyncSession = Depends(get_db),
) -> list[JobLogResponse]:
    """List all structured log records for a job."""
    stmt = select(JobLog).where(JobLog.job_id == job.id).order_by(JobLog.created_at.asc())
    result = await session.execute(stmt)
    logs = result.scalars().all()
    return [JobLogResponse.model_validate(log) for log in logs]

