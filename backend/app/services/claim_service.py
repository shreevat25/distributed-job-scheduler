"""Claim service — business orchestration for atomic job claiming.

DESIGN TRADEOFF DOCUMENTED:

Locking the queue row with FOR UPDATE serializes claim-capacity allocation
for the same queue. This ensures the concurrency limit is enforced correctly
under contention but reduces claim parallelism for that specific queue.
Different queues can still be claimed concurrently since they lock different rows.

This is the correct tradeoff for a job scheduler where over-claiming
(exceeding concurrency limit) is worse than slightly reduced throughput.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, QueuePausedError
from app.core.logging import get_logger
from app.models.job import Job
from app.repositories import job_repository, queue_repository

logger = get_logger(__name__)


async def claim_jobs(
    session: AsyncSession,
    queue_id: uuid.UUID,
    worker_id: uuid.UUID,
    requested_limit: int,
    lease_duration_seconds: int | None = None,
) -> list[Job]:
    """Claim jobs from a queue with concurrency limit enforcement.

    This is the primary entry point for workers to claim work.

    Steps:
        1. Lock the queue row with FOR UPDATE
        2. Verify queue is not paused
        3. Count active jobs (claimed + running)
        4. Calculate available_slots = concurrency_limit - active_count
        5. claim_limit = min(requested_limit, available_slots)
        6. If <= 0, return empty list
        7. Atomically claim jobs via SELECT FOR UPDATE SKIP LOCKED
        8. Return claimed jobs

    Args:
        session: Active async session.
        queue_id: Queue to claim from.
        worker_id: Worker requesting jobs.
        requested_limit: Max jobs the worker wants.
        lease_duration_seconds: Custom lease duration, or default from settings.

    Returns:
        List of claimed Job instances (may be empty).

    Raises:
        NotFoundError: If queue doesn't exist.
        QueuePausedError: If queue is paused.
    """
    if lease_duration_seconds is None:
        lease_duration_seconds = settings.JOB_LEASE_DURATION_SECONDS

    # Step 1: Lock queue row
    queue = await queue_repository.get_queue_for_update(session, queue_id)
    if queue is None:
        raise NotFoundError("Queue", str(queue_id))

    # Step 2: Check pause state
    if queue.is_paused:
        logger.info(
            "claim_rejected_queue_paused",
            queue_id=str(queue_id),
            worker_id=str(worker_id),
        )
        raise QueuePausedError(str(queue_id))

    # Step 3: Count active jobs
    active_count = await queue_repository.count_active_jobs(session, queue_id)

    # Step 4: Calculate available slots
    available_slots = queue.concurrency_limit - active_count

    # Step 5: Determine claim limit
    claim_limit = min(requested_limit, available_slots)

    logger.info(
        "claim_capacity_check",
        queue_id=str(queue_id),
        worker_id=str(worker_id),
        concurrency_limit=queue.concurrency_limit,
        active_count=active_count,
        available_slots=available_slots,
        requested_limit=requested_limit,
        claim_limit=claim_limit,
    )

    # Step 6: Short-circuit if no slots
    if claim_limit <= 0:
        return []

    # Step 7: Atomically claim jobs
    claimed = await job_repository.claim_jobs_atomic(
        session,
        queue_id=queue_id,
        worker_id=worker_id,
        limit=claim_limit,
        lease_duration_seconds=lease_duration_seconds,
    )

    logger.info(
        "jobs_claimed",
        queue_id=str(queue_id),
        worker_id=str(worker_id),
        claimed_count=len(claimed),
        job_ids=[str(j.id) for j in claimed],
    )

    return claimed
