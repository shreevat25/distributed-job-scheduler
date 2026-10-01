"""Project repository — persistence operations for projects."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


async def get_owned(
    session: AsyncSession,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Project | None:
    """Fetch a project scoped to its owner (authorization in the WHERE clause)."""
    stmt = select(Project).where(
        Project.id == project_id,
        Project.owner_id == owner_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def find_by_name(
    session: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> Project | None:
    """Find an owner's project by name, optionally excluding one project."""
    stmt = select(Project).where(
        Project.owner_id == owner_id,
        Project.name == name,
    )
    if exclude_id is not None:
        stmt = stmt.where(Project.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[Project]:
    """List all projects owned by a user, oldest first."""
    stmt = (
        select(Project)
        .where(Project.owner_id == owner_id)
        .order_by(Project.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create(session: AsyncSession, project: Project) -> Project:
    """Persist a new project."""
    session.add(project)
    await session.flush()
    return project
