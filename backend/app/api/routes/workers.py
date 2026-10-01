"""Worker API routes — status and health monitoring."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories import worker_repository
from app.schemas.worker import WorkerResponse

router = APIRouter(tags=["workers"])


@router.get(
    "/workers",
    response_model=list[WorkerResponse],
    summary="List registered workers",
)
async def list_workers(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[WorkerResponse]:
    """List all registered worker processes."""
    workers = await worker_repository.list_all(session)
    return [WorkerResponse.model_validate(w) for w in workers]


@router.get(
    "/workers/{id}",
    response_model=WorkerResponse,
    summary="Get worker details",
)
async def get_worker(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> WorkerResponse:
    """Get details of a specific worker process."""
    worker = await worker_repository.get_by_id(session, id)
    if not worker:
        raise NotFoundError("Worker", str(id))
    return WorkerResponse.model_validate(worker)
