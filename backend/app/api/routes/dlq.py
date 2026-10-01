"""DLQ API routes — listing, detail, and manual retry."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_dlq_entry
from app.models.dlq_entry import DLQEntry
from app.models.user import User
from app.repositories import dlq_repository
from app.schemas.dlq import DLQEntryResponse
from app.services import retry_service

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
    entries = await dlq_repository.list_for_owner(session, current_user.id, queue_id)
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
    dlq_entry = await retry_service.retry_dead_lettered_job(session, id, current_user.id)
    await session.commit()
    await session.refresh(dlq_entry)
    return DLQEntryResponse.model_validate(dlq_entry)
