"""Queue API routes with pause/resume and real stats."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_project, get_owned_queue
from app.core.exceptions import ConflictError
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.repositories import queue_repository
from app.schemas.queue import QueueCreate, QueueResponse, QueueStatsResponse, QueueUpdate
from app.services import metrics_service

router = APIRouter(tags=["queues"])


@router.post(
    "/projects/{project_id}/queues",
    response_model=QueueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a queue",
)
async def create_queue(
    data: QueueCreate,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_db),
) -> QueueResponse:
    """Create a queue within a project."""
    if await queue_repository.find_by_name(session, project.id, data.name) is not None:
        raise ConflictError(f"Queue '{data.name}' already exists in this project")

    queue = await queue_repository.create_queue(
        session,
        Queue(
            project_id=project.id,
            retry_policy_id=data.retry_policy_id,
            name=data.name,
            description=data.description,
            priority=data.priority,
            concurrency_limit=data.concurrency_limit,
        ),
    )
    return QueueResponse.model_validate(queue)


@router.get(
    "/projects/{project_id}/queues",
    response_model=list[QueueResponse],
    summary="List queues for a project",
)
async def list_queues(
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_db),
) -> list[QueueResponse]:
    """List all queues belonging to a project."""
    queues = await queue_repository.get_queues_by_project(session, project.id)
    return [QueueResponse.model_validate(q) for q in queues]


@router.get(
    "/queues/{queue_id}",
    response_model=QueueResponse,
    summary="Get queue details",
)
async def get_queue(
    queue: Queue = Depends(get_owned_queue),
) -> QueueResponse:
    """Get a queue by ID (must belong to user's project)."""
    return QueueResponse.model_validate(queue)


@router.patch(
    "/queues/{queue_id}",
    response_model=QueueResponse,
    summary="Update a queue",
)
async def update_queue(
    data: QueueUpdate,
    queue: Queue = Depends(get_owned_queue),
    session: AsyncSession = Depends(get_db),
) -> QueueResponse:
    """Partially update a queue."""
    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is not None:
        duplicate = await queue_repository.find_by_name(
            session, queue.project_id, update_data["name"], exclude_id=queue.id
        )
        if duplicate is not None:
            raise ConflictError(f"Queue '{update_data['name']}' already exists")

    for key, value in update_data.items():
        setattr(queue, key, value)

    queue.updated_at = datetime.now(UTC)
    await session.flush()
    return QueueResponse.model_validate(queue)


@router.post(
    "/queues/{queue_id}/pause",
    response_model=QueueResponse,
    summary="Pause a queue",
)
async def pause_queue(
    queue: Queue = Depends(get_owned_queue),
    session: AsyncSession = Depends(get_db),
) -> QueueResponse:
    """Pause a queue — no new jobs may be claimed, but existing running jobs continue."""
    queue.is_paused = True
    queue.updated_at = datetime.now(UTC)
    await session.flush()
    return QueueResponse.model_validate(queue)


@router.post(
    "/queues/{queue_id}/resume",
    response_model=QueueResponse,
    summary="Resume a queue",
)
async def resume_queue(
    queue: Queue = Depends(get_owned_queue),
    session: AsyncSession = Depends(get_db),
) -> QueueResponse:
    """Resume a paused queue — jobs may be claimed again."""
    queue.is_paused = False
    queue.updated_at = datetime.now(UTC)
    await session.flush()
    return QueueResponse.model_validate(queue)


@router.get(
    "/queues/{queue_id}/stats",
    response_model=QueueStatsResponse,
    summary="Get queue statistics",
)
async def get_queue_stats(
    queue: Queue = Depends(get_owned_queue),
    session: AsyncSession = Depends(get_db),
) -> QueueStatsResponse:
    """Get real database-counted statistics for a queue."""
    return await metrics_service.get_queue_stats(session, queue.id)
