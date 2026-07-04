"""Integration tests for transactional batch creation."""

import pytest
import httpx


class TestBatchCreation:
    """Test transactional batch job creation."""

    async def test_create_batch(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/batches",
            json={
                "name": "test-batch",
                "jobs": [
                    {"type": "email.send", "payload": {"to": "a@test.com"}},
                    {"type": "email.send", "payload": {"to": "b@test.com"}},
                    {"type": "email.send", "payload": {"to": "c@test.com"}},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-batch"
        assert data["total_jobs"] == 3
        assert len(data["job_ids"]) == 3

    async def test_batch_with_mixed_scheduling(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/batches",
            json={
                "jobs": [
                    {"type": "immediate.job", "payload": {}},
                    {"type": "delayed.job", "payload": {}, "delay_seconds": 300},
                    {"type": "priority.job", "payload": {}, "priority": 10},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["total_jobs"] == 3

    async def test_batch_empty_jobs_rejected(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/batches",
            json={"jobs": []},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_get_batch_detail(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        # Create batch
        create_resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/batches",
            json={
                "name": "detail-batch",
                "jobs": [
                    {"type": "job1", "payload": {}},
                    {"type": "job2", "payload": {}},
                ],
            },
            headers=auth_headers,
        )
        batch_id = create_resp.json()["id"]

        # Get detail
        resp = await client.get(
            f"/api/v1/batches/{batch_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_jobs"] == 2
        assert len(data["status_counts"]) >= 1
        # All should be queued initially
        total_from_counts = sum(sc["count"] for sc in data["status_counts"])
        assert total_from_counts == 2

    async def test_batch_rollback_on_persistence_failure(
        self, client: httpx.AsyncClient, auth_headers, test_queue, db_session
    ):
        """Prove that if a persistence operation fails during batch creation, no partial batch or jobs remain."""
        from sqlalchemy import select, func
        from app.models.job_batch import JobBatch
        from app.models.job import Job

        # Attempt to create a batch containing two jobs with the exact same idempotency_key in the same queue.
        # This causes PostgreSQL to raise an IntegrityError on the partial unique index during flush, triggering a rollback.
        dup_key = "batch-rollback-test-key"
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/batches",
            json={
                "name": "rollback-batch-must-not-exist",
                "jobs": [
                    {"type": "job.part1", "payload": {"step": 1}, "idempotency_key": dup_key},
                    {"type": "job.part2", "payload": {"step": 2}, "idempotency_key": dup_key},
                ],
            },
            headers=auth_headers,
        )
        # Expect creation to fail due to database constraint violation / conflict
        assert resp.status_code in (409, 400, 422, 500)

        # Query the database directly to demonstrate that NO partial batch row or job rows remain
        batch_stmt = select(func.count()).select_from(JobBatch).where(JobBatch.name == "rollback-batch-must-not-exist")
        batch_count = (await db_session.execute(batch_stmt)).scalar_one()
        assert batch_count == 0, f"Expected 0 batch rows after rollback, found {batch_count}"

        job_stmt = select(func.count()).select_from(Job).where(Job.idempotency_key == dup_key)
        job_count = (await db_session.execute(job_stmt)).scalar_one()
        assert job_count == 0, f"Expected 0 job rows after rollback, found {job_count}"
