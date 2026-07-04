"""Worker API routes — status and health monitoring."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.models.worker import Worker
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
    stmt = select(Worker).order_by(Worker.started_at.desc())
    result = await session.execute(stmt)
    workers = result.scalars().all()
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
    stmt = select(Worker).where(Worker.id == id)
    result = await session.execute(stmt)
    worker = result.scalar_one_or_none()
    if not worker:
        raise NotFoundError("Worker", str(id))
    return WorkerResponse.model_validate(worker)
