"""Batch repository — persistence operations for job batches."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_batch import JobBatch


async def create(session: AsyncSession, batch: JobBatch) -> JobBatch:
    """Persist a new batch (flushes so batch.id is available)."""
    session.add(batch)
    await session.flush()
    return batch


async def get_by_id(session: AsyncSession, batch_id: uuid.UUID) -> JobBatch | None:
    """Fetch a batch by ID."""
    stmt = select(JobBatch).where(JobBatch.id == batch_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
