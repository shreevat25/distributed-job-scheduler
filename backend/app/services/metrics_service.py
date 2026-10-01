"""Metrics service — aggregate job counts for queues and batches."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus
from app.repositories import job_repository
from app.schemas.batch import BatchStatusCount
from app.schemas.queue import QueueStatsResponse


def _status_name(status: JobStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


async def get_queue_stats(
    session: AsyncSession,
    queue_id: uuid.UUID,
) -> QueueStatsResponse:
    """Compute real database counts of jobs by status for a queue."""
    rows = await job_repository.count_jobs_by_status(session, queue_id=queue_id)
    counts = {_status_name(status): count for status, count in rows}

    return QueueStatsResponse(
        queue_id=queue_id,
        queued=counts.get("queued", 0),
        scheduled=counts.get("scheduled", 0),
        claimed=counts.get("claimed", 0),
        running=counts.get("running", 0),
        retry_wait=counts.get("retry_wait", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        dead_lettered=counts.get("dead_lettered", 0),
        total=sum(counts.values()),
    )


async def get_batch_status_counts(
    session: AsyncSession,
    batch_id: uuid.UUID,
) -> list[BatchStatusCount]:
    """Count a batch's jobs grouped by status."""
    rows = await job_repository.count_jobs_by_status(session, batch_id=batch_id)
    return [BatchStatusCount(status=status, count=count) for status, count in rows]
