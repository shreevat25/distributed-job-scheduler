"""Pytest fixtures for integration tests against real PostgreSQL."""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set test environment before importing app modules
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://djs_user:djs_password@127.0.0.1:54321/djs_test_db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

from app.core.enums import WorkerStatus
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker


TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create a test database engine (session-scoped)."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after all tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh async session that rolls back after each test."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def independent_session_factory(test_engine):
    """Factory for creating independent DB sessions (for concurrency tests).

    Each session gets its own connection and transaction,
    simulating real concurrent workers.
    """
    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def create_session() -> AsyncSession:
        return factory()

    return create_session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an async HTTP test client with DB session override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def auth_token(test_user: User) -> str:
    """Create a JWT token for the test user."""
    return create_access_token(subject=str(test_user.id))


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> dict[str, str]:
    """Create authorization headers for the test user."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def test_project(db_session: AsyncSession, test_user: User) -> Project:
    """Create a test project."""
    project = Project(
        owner_id=test_user.id,
        name="Test Project",
        description="A project for testing",
    )
    db_session.add(project)
    await db_session.flush()
    return project


@pytest_asyncio.fixture
async def test_queue(db_session: AsyncSession, test_project: Project) -> Queue:
    """Create a test queue with concurrency limit of 10."""
    queue = Queue(
        project_id=test_project.id,
        name="test-queue",
        concurrency_limit=10,
    )
    db_session.add(queue)
    await db_session.flush()
    return queue


@pytest_asyncio.fixture
async def test_worker(db_session: AsyncSession) -> Worker:
    """Create a test worker."""
    worker = Worker(
        name="test-worker-1",
        hostname="localhost",
        process_id=1234,
        status=WorkerStatus.ONLINE,
        concurrency=5,
    )
    db_session.add(worker)
    await db_session.flush()
    return worker


@pytest_asyncio.fixture
async def second_worker(db_session: AsyncSession) -> Worker:
    """Create a second test worker for concurrency tests."""
    worker = Worker(
        name="test-worker-2",
        hostname="localhost",
        process_id=5678,
        status=WorkerStatus.ONLINE,
        concurrency=5,
    )
    db_session.add(worker)
    await db_session.flush()
    return worker
