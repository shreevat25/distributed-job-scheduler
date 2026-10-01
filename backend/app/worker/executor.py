"""Job executor — runs a single claimed job end to end.

For each job the executor:

1. starts execution transactionally (verifies claim ownership and lease),
2. renews the job lease in the background while the handler runs,
3. runs the handler, then
4. completes the job, or fails it into retry_wait / the DLQ.

Each step uses its own short-lived session so no transaction is held open
while user code runs.
"""

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.services import claim_service, execution_service
from app.worker import handlers
from app.worker.shutdown import cancel_and_wait

logger = logging.getLogger(__name__)


class JobExecutor:
    """Executes claimed jobs on behalf of one worker."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        worker_id: uuid.UUID,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.lease_renew_tasks: dict[uuid.UUID, asyncio.Task] = {}

    async def execute(
        self,
        job_id: uuid.UUID,
        job_type: str,
        payload: dict[str, Any],
        claim_token: uuid.UUID,
    ) -> None:
        """Execute a claimed job in its own independent database sessions."""
        # 1. Start execution transactionally
        async with self.session_factory() as session:
            try:
                job, _ = await execution_service.start_execution(
                    session=session,
                    job_id=job_id,
                    worker_id=self.worker_id,
                    claim_token=claim_token,
                )
                await session.commit()
                attempt_number = job.attempt_count
            except Exception as exc:
                logger.warning("Failed to start execution for job %s: %s", job_id, exc)
                await session.rollback()
                return

        # 2. Start background lease renewal task
        renew_task = asyncio.create_task(self._lease_renew_loop(job_id, claim_token))
        self.lease_renew_tasks[job_id] = renew_task

        # 3. Run handler
        try:
            result = await handlers.execute_job_handler(job_type, payload, attempt_number)
            # Authoritatively complete
            async with self.session_factory() as session:
                await execution_service.complete_job(
                    session=session,
                    job_id=job_id,
                    worker_id=self.worker_id,
                    claim_token=claim_token,
                    result=result,
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Job %s handler failed on attempt %d: %s", job_id, attempt_number, exc)
            # Transactional fail (retry or DLQ)
            async with self.session_factory() as session:
                try:
                    await execution_service.fail_job(
                        session=session,
                        job_id=job_id,
                        worker_id=self.worker_id,
                        claim_token=claim_token,
                        exc=exc,
                    )
                    await session.commit()
                except Exception as fail_exc:
                    logger.error("Error failing job %s: %s", job_id, fail_exc)
                    await session.rollback()
        finally:
            self.lease_renew_tasks.pop(job_id, None)
            await cancel_and_wait([renew_task])

    async def cancel_lease_renewals(self) -> None:
        """Stop every in-flight lease renewal loop."""
        await cancel_and_wait(list(self.lease_renew_tasks.values()))

    async def _lease_renew_loop(self, job_id: uuid.UUID, claim_token: uuid.UUID) -> None:
        """Periodically renew the lease for an active job until ownership is lost."""
        interval = float(settings.JOB_LEASE_RENEW_INTERVAL_SECONDS)
        while True:
            await asyncio.sleep(interval)
            async with self.session_factory() as session:
                try:
                    renewed = await claim_service.renew_lease(
                        session=session,
                        job_id=job_id,
                        worker_id=self.worker_id,
                        claim_token=claim_token,
                        lease_duration_seconds=settings.JOB_LEASE_DURATION_SECONDS,
                    )
                    if not renewed:
                        logger.warning("Lease renewal failed for job %s (ownership lost). Stopping renewal.", job_id)
                        break
                except Exception as exc:
                    logger.warning("Transient error renewing lease for job %s: %s", job_id, exc)
                    await session.rollback()
