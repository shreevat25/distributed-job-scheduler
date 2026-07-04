"""Integration tests for idempotency — including concurrent races."""

import asyncio
import uuid

import pytest
import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.core.security import hash_password
from app.models.worker import Worker
from app.core.enums import WorkerStatus


class TestIdempotency:
    """Test idempotency key behavior via API."""

    async def test_duplicate_key_returns_existing_job(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        payload = {
            "type": "email.send",
            "payload": {"to": "user@test.com"},
            "idempotency_key": "unique-key-1",
        }

        resp1 = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json=payload,
            headers=auth_headers,
        )
        assert resp1.status_code == 201
        job_id_1 = resp1.json()["id"]

        # Same request again
        resp2 = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json=payload,
            headers=auth_headers,
        )
        # Should still succeed with the existing job
        assert resp2.status_code == 201
        assert resp2.json()["id"] == job_id_1

    async def test_different_payload_same_key_returns_409(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={
                "type": "email.send",
                "payload": {"to": "user@test.com"},
                "idempotency_key": "conflict-key",
            },
            headers=auth_headers,
        )

        resp = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json={
                "type": "sms.send",  # Different type
                "payload": {"to": "user@test.com"},
                "idempotency_key": "conflict-key",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    async def test_null_key_always_creates_new(
        self, client: httpx.AsyncClient, auth_headers, test_queue
    ):
        payload = {"type": "test", "payload": {}}

        resp1 = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json=payload,
            headers=auth_headers,
        )
        resp2 = await client.post(
            f"/api/v1/queues/{test_queue.id}/jobs",
            json=payload,
            headers=auth_headers,
        )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] != resp2.json()["id"]


class TestIdempotencyConcurrency:
    """Test concurrent idempotency races using real PostgreSQL.

    Multiple concurrent requests with the same queue + idempotency_key
    must result in exactly one job row, enforced by the partial unique index.
    """

    async def test_concurrent_same_key_creates_one_job(
        self, independent_session_factory, test_engine
    ):
        """Race N concurrent job creations with the same idempotency key."""
        # Setup: create user, project, queue in a setup session
        async with (await independent_session_factory()) as setup_session:
            user = User(
                email=f"idemp-{uuid.uuid4().hex[:8]}@test.com",
                password_hash=hash_password("testpass123"),
            )
            setup_session.add(user)
            await setup_session.flush()

            project = Project(
                owner_id=user.id,
                name=f"idemp-project-{uuid.uuid4().hex[:8]}",
            )
            setup_session.add(project)
            await setup_session.flush()

            queue = Queue(
                project_id=project.id,
                name=f"idemp-queue-{uuid.uuid4().hex[:8]}",
                concurrency_limit=10,
            )
            setup_session.add(queue)
            await setup_session.flush()
            queue_id = queue.id
            await setup_session.commit()

        idemp_key = f"concurrent-key-{uuid.uuid4().hex[:8]}"

        async def create_job_with_key(session_factory):
            """Attempt to create a job with the shared idempotency key."""
            async with (await session_factory()) as session:
                job = Job(
                    queue_id=queue_id,
                    type="test.concurrent",
                    payload={"key": "value"},
                    status=JobStatus.QUEUED,
                    priority=0,
                    idempotency_key=idemp_key,
                    max_attempts=3,
                )
                try:
                    session.add(job)
                    await session.flush()
                    await session.commit()
                    return "created"
                except Exception:
                    await session.rollback()
                    return "conflict"

        # Race 5 concurrent creations
        results = await asyncio.gather(
            *[create_job_with_key(independent_session_factory) for _ in range(5)]
        )

        # Verify: exactly one succeeded
        created_count = results.count("created")
        assert created_count == 1, f"Expected exactly 1 created, got {created_count}. Results: {results}"

        # Verify: exactly one row in DB
        async with (await independent_session_factory()) as verify_session:
            stmt = select(func.count()).select_from(Job).where(
                Job.queue_id == queue_id,
                Job.idempotency_key == idemp_key,
            )
            result = await verify_session.execute(stmt)
            count = result.scalar_one()
            assert count == 1, f"Expected exactly 1 job row, found {count}"
