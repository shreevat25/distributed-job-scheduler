"""User repository — persistence operations for user accounts."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch a user by ID."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch an active user by ID."""
    stmt = select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_email(session: AsyncSession, normalized_email: str) -> User | None:
    """Fetch a user by their already-normalized email."""
    stmt = select(User).where(User.email == normalized_email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create(session: AsyncSession, user: User) -> User:
    """Persist a new user."""
    session.add(user)
    await session.flush()
    return user
