"""Integration tests for worker heartbeat monitoring against real PostgreSQL."""

import asyncio
import uuid
import pytest
from sqlalchemy import select
from app.core.enums import WorkerStatus
from app.models.worker import Worker
from app.models.worker_heartbeat import WorkerHeartbeat
from app.worker import heartbeat


@pytest.mark.asyncio
class TestHeartbeat:
    """Verify worker registration and heartbeat time advancement."""

    async def test_heartbeat_advances_clock_and_creates_history(self, independent_session_factory):
        worker_id = uuid.uuid4()
        async with (await independent_session_factory()) as session:
            worker = await heartbeat.register_worker(
                session, worker_id=worker_id, name="hb-worker", concurrency=5
            )
            assert worker.status == WorkerStatus.ONLINE
            initial_last_seen = worker.last_seen_at

        # Sleep briefly so DB timestamp advances
        await asyncio.sleep(0.1)

        async with (await independent_session_factory()) as session:
            await heartbeat.record_heartbeat(session, worker_id=worker_id, active_job_count=2)

        async with (await independent_session_factory()) as session:
            stmt = select(Worker).where(Worker.id == worker_id)
            worker = (await session.execute(stmt)).scalar_one()
            assert worker.last_seen_at >= initial_last_seen

            hb_stmt = select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id)
            history = (await session.execute(hb_stmt)).scalars().all()
            assert len(history) == 1
            assert history[0].active_job_count == 2
