"""Integration tests verifying strict multi-tenant authorization boundaries across all resources.

Proves that User B cannot access User A's:
- project
- retry policy
- queue
- job
- batch
even when guessing or knowing the exact UUIDs.
"""

import uuid
import pytest
import httpx


class TestAuthorizationBoundaries:
    """Verify cross-user isolation across the entire API."""

    @pytest.fixture
    async def user_b_headers(self, client: httpx.AsyncClient):
        """Create a second user (User B) and return their auth headers."""
        email = f"user_b_{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password123"},
        )
        token = login_resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_user_b_cannot_access_user_a_project(
        self, client: httpx.AsyncClient, test_project, user_b_headers
    ):
        """User B attempts to get and patch User A's project."""
        # Get project
        resp_get = await client.get(
            f"/api/v1/projects/{test_project.id}",
            headers=user_b_headers,
        )
        assert resp_get.status_code == 404

        # Patch project
        resp_patch = await client.patch(
            f"/api/v1/projects/{test_project.id}",
            json={"name": "Hacked Project"},
            headers=user_b_headers,
        )
        assert resp_patch.status_code == 404

    async def test_user_b_cannot_access_user_a_retry_policy(
        self, client: httpx.AsyncClient, auth_headers, test_project, user_b_headers
    ):
        """User B attempts to access a retry policy owned by User A."""
        # User A creates a retry policy
        create_resp = await client.post(
            f"/api/v1/projects/{test_project.id}/retry-policies",
            json={
                "name": "User A Policy",
                "max_attempts": 5,
                "strategy": "exponential",
                "base_delay_seconds": 10,
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        policy_id = create_resp.json()["id"]

        # User B tries to get it
        resp_get = await client.get(
            f"/api/v1/retry-policies/{policy_id}",
            headers=user_b_headers,
        )
        assert resp_get.status_code == 404

    async def test_user_b_cannot_access_user_a_queue(
        self, client: httpx.AsyncClient, test_queue, user_b_headers
    ):
        """User B attempts to get, update, pause, or claim from User A's queue."""
        # Get queue
        resp_get = await client.get(
            f"/api/v1/queues/{test_queue.id}",
            headers=user_b_headers,
        )
        assert resp_get.status_code == 404

        # Pause queue
        resp_pause = await client.post(
            f"/api/v1/queues/{test_queue.id}/pause",
            headers=user_b_headers,
        )
        assert resp_pause.status_code == 404

        # Claim from queue
        resp_claim = await client.post(
            f"/api/v1/queues/{test_queue.id}/claim",
            json={"worker_id": str(uuid.uuid4()), "limit": 1},
            headers=user_b_headers,
        )
        assert resp_claim.status_code == 404

    async def test_user_b_cannot_access_user_a_job(
        self, client: httpx.AsyncClient, auth_headers, test_queue, user_b_headers
    ):
        """User B attempts to get User A's job."""
        # User A creates a job
        create_resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={"type": "secret.job", "payload": {"data": "top-secret"}},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        # User B tries to get the job
        resp_get = await client.get(
            f"/api/v1/jobs/{job_id}",
            headers=user_b_headers,
        )
        assert resp_get.status_code == 403

    async def test_user_b_cannot_access_user_a_batch(
        self, client: httpx.AsyncClient, auth_headers, test_queue, user_b_headers
    ):
        """User B attempts to get User A's batch."""
        # User A creates a batch
        create_resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/batches",
            json={
                "name": "Secret Batch",
                "jobs": [{"type": "job1", "payload": {}}],
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        batch_id = create_resp.json()["id"]

        # User B tries to get the batch
        resp_get = await client.get(
            f"/api/v1/batches/{batch_id}",
            headers=user_b_headers,
        )
        assert resp_get.status_code == 403
