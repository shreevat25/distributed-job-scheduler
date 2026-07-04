"""Batch API routes — transactional multi-job creation."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_queue, get_user_queue_ids
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.queue import Queue
from app.models.user import User
from app.schemas.batch import BatchCreate, BatchDetailResponse, BatchResponse
from app.services import batch_service

router = APIRouter(tags=["batches"])


@router.post(
    "/queues/{queue_id}/batches",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a batch of jobs",
)
async def create_batch(
    data: BatchCreate,
    queue: Queue = Depends(get_owned_queue),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BatchResponse:
    """Create a batch of jobs atomically in a single transaction.

    All jobs are validated and created together. If any job fails,
    the entire batch is rolled back — no partial batch remains.
    """
    return await batch_service.create_batch(session, queue, current_user.id, data)


@router.get(
    "/batches/{batch_id}",
    response_model=BatchDetailResponse,
    summary="Get batch details",
)
async def get_batch(
    batch_id: uuid.UUID,
    allowed_queue_ids: list[uuid.UUID] = Depends(get_user_queue_ids),
    session: AsyncSession = Depends(get_db),
) -> BatchDetailResponse:
    """Get batch details with real aggregate status counts.

    Authorization: batch → queue → project → owner.
    """
    detail = await batch_service.get_batch_detail(session, batch_id)
    if detail is None:
        raise NotFoundError("Batch", str(batch_id))

    # Verify authorization through queue ownership
    if detail.queue_id not in allowed_queue_ids:
        raise ForbiddenError("Access denied to this batch")

    return detail
