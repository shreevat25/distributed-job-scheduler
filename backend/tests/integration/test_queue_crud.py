"""Integration tests for queue CRUD, pause/resume, and stats."""

import pytest
import httpx


class TestQueueCRUD:
    """Test queue creation, listing, update, and retrieval."""

    async def test_create_queue(
        self, client: httpx.AsyncClient, auth_headers, test_project
    ):
        resp = await client.post(
            f"/api/v1/projects/{test_project.id}/queues",
            json={"name": "email-queue", "concurrency_limit": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "email-queue"
        assert data["concurrency_limit"] == 5
        assert data["is_paused"] is False

    async def test_create_duplicate_queue_rejected(
        self, client: httpx.AsyncClient, auth_headers, test_project, test_queue
    ):
        resp = await client.post(
            f"/api/v1/projects/{test_project.id}/queues",
            json={"name": "test-queue", "concurrency_limit": 3},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_list_queues(
        self, client: httpx.AsyncClient, auth_headers, test_project, test_queue
    ):
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/queues",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(q["name"] == "test-queue" for q in data)

    async def test_get_queue(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.get(
            f"/api/v1/queues/{test_queue.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-queue"

    async def test_update_queue(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.patch(
            f"/api/v1/queues/{test_queue.id}",
            json={"concurrency_limit": 20},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["concurrency_limit"] == 20


class TestQueuePauseResume:
    """Test queue pause and resume behavior."""

    async def test_pause_queue(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/pause",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_paused"] is True

    async def test_resume_queue(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        # Pause first
        await client.post(
            f"/api/v1/queues/{test_queue.id}/pause",
            headers=auth_headers,
        )
        # Then resume
        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/resume",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_paused"] is False


class TestQueueStats:
    """Test queue statistics endpoint."""

    async def test_stats_empty_queue(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        resp = await client.get(
            f"/api/v1/queues/{test_queue.id}/stats",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["queue_id"] == str(test_queue.id)
        assert data["total"] == 0
        assert data["queued"] == 0

    async def test_stats_with_jobs(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        # Create some jobs
        for i in range(3):
            await client.post(
                f"/api/v1/queues/{test_queue.id}/jobs",
                json={"type": "test.job", "payload": {"index": i}},
                headers=auth_headers,
            )

        resp = await client.get(
            f"/api/v1/queues/{test_queue.id}/stats",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["queued"] == 3


class TestQueueAuthorization:
    """Test cross-user queue access is denied."""

    async def test_other_user_cannot_access_queue(
        self, client: httpx.AsyncClient, test_queue
    ):
        # Register a second user
        await client.post(
            "/api/v1/auth/register",
            json={"email": "other@example.com", "password": "otherpass123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "other@example.com", "password": "otherpass123"},
        )
        other_token = login_resp.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # Try to access the first user's queue
        resp = await client.get(
            f"/api/v1/queues/{test_queue.id}",
            headers=other_headers,
        )
        assert resp.status_code == 404  # Not found for unauthorized user
