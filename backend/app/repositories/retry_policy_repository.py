"""Retry policy repository — persistence operations for retry policies."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.retry_policy import RetryPolicy


async def get_owned(
    session: AsyncSession,
    policy_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> RetryPolicy | None:
    """Fetch a retry policy whose project is owned by the given user."""
    stmt = (
        select(RetryPolicy)
        .join(Project, RetryPolicy.project_id == Project.id)
        .where(
            RetryPolicy.id == policy_id,
            Project.owner_id == owner_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def find_by_name(
    session: AsyncSession,
    project_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> RetryPolicy | None:
    """Find a project's retry policy by name, optionally excluding one policy."""
    stmt = select(RetryPolicy).where(
        RetryPolicy.project_id == project_id,
        RetryPolicy.name == name,
    )
    if exclude_id is not None:
        stmt = stmt.where(RetryPolicy.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_for_project(session: AsyncSession, project_id: uuid.UUID) -> list[RetryPolicy]:
    """List all retry policies belonging to a project, oldest first."""
    stmt = (
        select(RetryPolicy)
        .where(RetryPolicy.project_id == project_id)
        .order_by(RetryPolicy.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create(session: AsyncSession, policy: RetryPolicy) -> RetryPolicy:
    """Persist a new retry policy."""
    session.add(policy)
    await session.flush()
    return policy
