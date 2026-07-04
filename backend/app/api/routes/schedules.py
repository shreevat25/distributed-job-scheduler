import uuid
from typing import List, Optional
from datetime import datetime, timezone
import croniter

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.enums import ScheduleType
from app.models.scheduled_job import ScheduledJob
from app.models.queue import Queue
from app.models.user import User
from app.schemas.scheduled_job import ScheduledJobCreate, ScheduledJobResponse

router = APIRouter()


from app.models.project import Project

@router.post("", response_model=ScheduledJobResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    schedule_in: ScheduledJobCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Create a new recurring or one-time scheduled job."""
    # Validate queue belongs to user
    stmt = (
        select(Queue)
        .join(Project, Queue.project_id == Project.id)
        .where(Queue.id == schedule_in.queue_id, Project.owner_id == current_user.id)
    )
    queue = (await db.execute(stmt)).scalar_one_or_none()
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    if schedule_in.schedule_type == ScheduleType.CRON:
        if not schedule_in.cron_expression or not croniter.croniter.is_valid(schedule_in.cron_expression):
            raise HTTPException(status_code=422, detail="Invalid cron expression")
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(schedule_in.timezone)
            now = datetime.now(timezone.utc)
            base_time = now.astimezone(tz)
            next_run_local = croniter.croniter(schedule_in.cron_expression, base_time).get_next(datetime)
            next_run = next_run_local.astimezone(timezone.utc)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid cron expression or timezone: {e}")
    else:
        if not schedule_in.run_at:
            raise HTTPException(status_code=422, detail="run_at is required for one-time schedules")
        next_run = schedule_in.run_at

    schedule = ScheduledJob(
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
    )
    db.add(schedule)
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
    stmt = (
        select(ScheduledJob)
        .join(Queue)
        .where(ScheduledJob.created_by == current_user.id)
        .order_by(ScheduledJob.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if queue_id:
        stmt = stmt.where(ScheduledJob.queue_id == queue_id)
        
    schedules = (await db.execute(stmt)).scalars().all()
    return list(schedules)


@router.get("/{schedule_id}", response_model=ScheduledJobResponse)
async def get_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    stmt = select(ScheduledJob).where(
        ScheduledJob.id == schedule_id, ScheduledJob.created_by == current_user.id
    )
    schedule = (await db.execute(stmt)).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("/{schedule_id}/pause", response_model=ScheduledJobResponse)
async def pause_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    stmt = select(ScheduledJob).where(
        ScheduledJob.id == schedule_id, ScheduledJob.created_by == current_user.id
    )
    schedule = (await db.execute(stmt)).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
        
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
    stmt = select(ScheduledJob).where(
        ScheduledJob.id == schedule_id, ScheduledJob.created_by == current_user.id
    )
    schedule = (await db.execute(stmt)).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
        
    schedule.is_active = True
    
    # Recalculate next_run_at if it's in the past to avoid immediate burst
    now = datetime.now(timezone.utc)
    if schedule.schedule_type == ScheduleType.CRON and schedule.next_run_at < now:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(schedule.timezone)
            base_time = now.astimezone(tz)
            next_run_local = croniter.croniter(schedule.cron_expression, base_time).get_next(datetime)
            schedule.next_run_at = next_run_local.astimezone(timezone.utc)
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
    stmt = select(ScheduledJob).where(
        ScheduledJob.id == schedule_id, ScheduledJob.created_by == current_user.id
    )
    schedule = (await db.execute(stmt)).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
        
    await db.delete(schedule)
    await db.commit()
