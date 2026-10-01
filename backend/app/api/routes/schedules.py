"""Scheduled job API routes — one-time and cron schedules."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.enums import ScheduleType
from app.models.scheduled_job import ScheduledJob
from app.models.user import User
from app.repositories import queue_repository, schedule_repository
from app.schemas.scheduled_job import ScheduledJobCreate, ScheduledJobResponse
from app.services import schedule_service

router = APIRouter()


async def _get_schedule_or_404(
    db: AsyncSession,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ScheduledJob:
    schedule = await schedule_repository.get_for_creator(db, schedule_id, user_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("", response_model=ScheduledJobResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    schedule_in: ScheduledJobCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Create a new recurring or one-time scheduled job."""
    queue = await queue_repository.get_owned(db, schedule_in.queue_id, current_user.id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    if schedule_in.schedule_type == ScheduleType.CRON:
        if not schedule_service.is_valid_cron(schedule_in.cron_expression):
            raise HTTPException(status_code=422, detail="Invalid cron expression")
        try:
            next_run = schedule_service.next_cron_run(
                schedule_in.cron_expression, schedule_in.timezone, datetime.now(timezone.utc)
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid cron expression or timezone: {e}")
    else:
        if not schedule_in.run_at:
            raise HTTPException(status_code=422, detail="run_at is required for one-time schedules")
        next_run = schedule_in.run_at

    schedule = schedule_repository.add(
        db,
        ScheduledJob(
            queue_id=schedule_in.queue_id,
            name=schedule_in.name,
            job_type=schedule_in.job_type,
            payload=schedule_in.payload,
            schedule_type=schedule_in.schedule_type,
            run_at=schedule_in.run_at,
            cron_expression=schedule_in.cron_expression,
            timezone=schedule_in.timezone,
            next_run_at=next_run,
            created_by=current_user.id,
        ),
    )
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("", response_model=List[ScheduledJobResponse])
async def list_schedules(
    queue_id: Optional[uuid.UUID] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """List schedules for the current user's projects."""
    return await schedule_repository.list_for_creator(
        db, current_user.id, queue_id=queue_id, skip=skip, limit=limit
    )


@router.get("/{schedule_id}", response_model=ScheduledJobResponse)
async def get_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return await _get_schedule_or_404(db, schedule_id, current_user.id)


@router.post("/{schedule_id}/pause", response_model=ScheduledJobResponse)
async def pause_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    schedule = await _get_schedule_or_404(db, schedule_id, current_user.id)
    schedule.is_active = False
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.post("/{schedule_id}/resume", response_model=ScheduledJobResponse)
async def resume_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    schedule = await _get_schedule_or_404(db, schedule_id, current_user.id)
    schedule.is_active = True

    try:
        schedule_service.advance_next_run_if_past(schedule, datetime.now(timezone.utc))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid cron expression or timezone: {e}")

    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    schedule = await _get_schedule_or_404(db, schedule_id, current_user.id)
    await schedule_repository.delete(db, schedule)
    await db.commit()
