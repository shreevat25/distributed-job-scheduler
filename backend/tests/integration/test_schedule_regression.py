"""Focused regression tests for schedule API: authorization, validation, pause/resume, timezone."""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
import httpx
from sqlalchemy.ext.asyncio import AsyncSession


class TestScheduleRegression:
    """Regression tests verifying schedule API security and correctness."""

    @pytest.fixture
    async def user_b_headers(self, client: httpx.AsyncClient):
        """Create a second user and return their auth headers."""
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

    async def test_cross_user_schedule_creation_denied(
        self, client: httpx.AsyncClient, test_queue, user_b_headers
    ):
        """User B cannot create a schedule on User A's queue — security boundary test."""
        resp = await client.post(
            "/api/v1/schedules",
            json={
                "queue_id": str(test_queue.id),
                "name": "attacker-schedule",
                "job_type": "evil.job",
                "schedule_type": "cron",
                "cron_expression": "* * * * *",
                "payload": {},
            },
            headers=user_b_headers,
        )
        # Must be 404 (queue not visible to user B), not 201
        assert resp.status_code == 404, (
            f"Expected 404, got {resp.status_code}: {resp.text}"
        )

    async def test_invalid_cron_rejected(
        self, client: httpx.AsyncClient, test_queue, auth_headers
    ):
        """Invalid cron expression must return 422 with detail."""
        resp = await client.post(
            "/api/v1/schedules",
            json={
                "queue_id": str(test_queue.id),
                "name": "bad-cron",
                "job_type": "echo",
                "schedule_type": "cron",
                "cron_expression": "not a cron",
                "payload": {},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        # Either FastAPI validation or our explicit 422
        assert "detail" in body

    async def test_pause_and_resume_schedule(
        self, client: httpx.AsyncClient, test_queue, auth_headers
    ):
        """Pause then resume a schedule — is_active toggles correctly."""
        create_resp = await client.post(
            "/api/v1/schedules",
            json={
                "queue_id": str(test_queue.id),
                "name": "pause-resume-test",
                "job_type": "echo",
                "schedule_type": "cron",
                "cron_expression": "0 * * * *",
                "payload": {},
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        sched_id = create_resp.json()["id"]
        assert create_resp.json()["is_active"] is True

        # Pause
        pause_resp = await client.post(
            f"/api/v1/schedules/{sched_id}/pause",
            headers=auth_headers,
        )
        assert pause_resp.status_code == 200
        assert pause_resp.json()["is_active"] is False

        # Resume
        resume_resp = await client.post(
            f"/api/v1/schedules/{sched_id}/resume",
            headers=auth_headers,
        )
        assert resume_resp.status_code == 200
        assert resume_resp.json()["is_active"] is True

    async def test_timezone_aware_next_occurrence(
        self, client: httpx.AsyncClient
    ):
        """next_run_at is stored as UTC even when a non-UTC timezone is specified."""
        # Self-contained: register own user and create own queue
        email = f"tz_test_{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password123"},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        proj_resp = await client.post(
            "/api/v1/projects",
            json={"name": f"tz-proj-{uuid.uuid4().hex[:6]}"},
            headers=headers,
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        queue_resp = await client.post(
            f"/api/v1/projects/{project_id}/queues",
            json={"name": "tz-queue", "concurrency_limit": 2},
            headers=headers,
        )
        assert queue_resp.status_code == 201
        queue_id = queue_resp.json()["id"]

        resp = await client.post(
            "/api/v1/schedules",
            json={
                "queue_id": queue_id,
                "name": "tz-test",
                "job_type": "echo",
                "schedule_type": "cron",
                "cron_expression": "0 12 * * *",  # noon daily
                "timezone": "America/New_York",
                "payload": {},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "next_run_at" in body

        # Parse and verify it's a valid timestamp in the future
        next_run = datetime.fromisoformat(body["next_run_at"].replace("Z", "+00:00"))
        assert next_run > datetime.now(timezone.utc)
        # The timezone field in the response reflects what was submitted
        assert body["timezone"] == "America/New_York"

    async def test_invalid_timezone_rejected(
        self, client: httpx.AsyncClient
    ):
        """An invalid timezone name should return 422."""
        # Self-contained: register own user and create own queue
        email = f"badtz_{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password123"},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        proj_resp = await client.post(
            "/api/v1/projects",
            json={"name": f"badtz-proj-{uuid.uuid4().hex[:6]}"},
            headers=headers,
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        queue_resp = await client.post(
            f"/api/v1/projects/{project_id}/queues",
            json={"name": "badtz-queue", "concurrency_limit": 2},
            headers=headers,
        )
        assert queue_resp.status_code == 201
        queue_id = queue_resp.json()["id"]

        resp = await client.post(
            "/api/v1/schedules",
            json={
                "queue_id": queue_id,
                "name": "bad-tz-test",
                "job_type": "echo",
                "schedule_type": "cron",
                "cron_expression": "* * * * *",
                "timezone": "Not/ATimezone",
                "payload": {},
            },
            headers=headers,
        )
        assert resp.status_code == 422

