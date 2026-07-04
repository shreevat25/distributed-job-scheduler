"""Integration tests for job creation — immediate, delayed, and listing."""

import pytest
import httpx
from datetime import datetime, timedelta, UTC


class TestImmediateJobCreation:
    """Test creating immediate jobs."""

    async def test_create_immediate_job(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "email.send", "payload": {"to": "user@test.com"}},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "email.send"
        assert data["status"] == "queued"
        assert data["queue_id"] == str(test_queue.id)
        assert data["priority"] == 0

    async def test_create_job_with_priority(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "urgent.task", "payload": {}, "priority": 10},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["priority"] == 10

    async def test_create_job_with_max_attempts(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "test", "payload": {}, "max_attempts": 7},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["max_attempts"] == 7

    async def test_create_job_inherits_queue_retry_policy_without_missing_greenlet(
        self, client: httpx.AsyncClient, auth_headers, test_project
    ):
        """Verify that accessing queue.retry_policy during job creation works without MissingGreenlet errors."""
        # 1. Create a retry policy with max_attempts=12
        policy_resp = await client.post(
            f"/api/v1/projects/{test_project.id}/retry-policies",
            json={
                "name": "Inheritance Policy",
                "max_attempts": 12,
                "strategy": "exponential",
                "base_delay_seconds": 10,
            },
            headers=auth_headers,
        )
        assert policy_resp.status_code == 201
        policy_id = policy_resp.json()["id"]

        # 2. Create a queue linked to this retry policy
        queue_resp = await client.post(
            f"/api/v1/projects/{test_project.id}/queues",
            json={"name": "policy-queue", "retry_policy_id": policy_id, "concurrency_limit": 5},
            headers=auth_headers,
        )
        assert queue_resp.status_code == 201
        queue_id = queue_resp.json()["id"]

        # 3. Create a job WITHOUT max_attempts so it falls back to queue.retry_policy.max_attempts
        job_resp = await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            json={"type": "inherit.test", "payload": {"foo": "bar"}},
            headers=auth_headers,
        )
        assert job_resp.status_code == 201
        # If queue.retry_policy raised MissingGreenlet, this would return 500.
        # Verify it inherited max_attempts=12 from the policy!
        assert job_resp.json()["max_attempts"] == 12


class TestDelayedJobCreation:
    """Test creating delayed/scheduled jobs."""

    async def test_create_delayed_job(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "report.generate", "payload": {}, "delay_seconds": 3600},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "scheduled"

    async def test_create_job_with_future_available_at(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "scheduled.task", "payload": {}, "available_at": future},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "scheduled"


class TestJobListAndDetail:
    """Test job listing with filters and job detail retrieval."""

    async def test_list_jobs(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        # Create jobs
        for i in range(3):
            await client.post(
                f"/api/v1/queues/{test_queue.id}/jobs",
                json={"type": f"test.type{i}", "payload": {"i": i}},
                headers=auth_headers,
            )

        resp = await client.get(
            "/api/v1/jobs",
            params={"queue_id": str(test_queue.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["page"] == 1
        assert data["limit"] == 50

    async def test_list_jobs_with_status_filter(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "test", "payload": {}},
            headers=auth_headers,
        )

        resp = await client.get(
            "/api/v1/jobs",
            params={"queue_id": str(test_queue.id), "status": "queued"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["status"] == "queued"

    async def test_list_jobs_pagination(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        for i in range(5):
            await client.post(
                f"/api/v1/queues/{test_queue.id}/jobs",
                json={"type": "test", "payload": {"i": i}},
                headers=auth_headers,
            )

        resp = await client.get(
            "/api/v1/jobs",
            params={"queue_id": str(test_queue.id), "page": 1, "limit": 2},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    async def test_get_job_detail(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        create_resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "test.detail", "payload": {"key": "value"}},
            headers=auth_headers,
        )
        job_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/v1/jobs/{job_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "test.detail"
        assert resp.json()["payload"] == {"key": "value"}
