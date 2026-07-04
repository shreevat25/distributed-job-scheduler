"""Authentication service — registration, login, and token validation."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse


async def register_user(
    session: AsyncSession,
    data: RegisterRequest,
) -> UserResponse:
    """Register a new user with normalized email and hashed password.

    Raises:
        ConflictError: If email is already registered.
    """
    normalized_email = User.normalize_email(data.email)

    # Check for existing user
    stmt = select(User).where(User.email == normalized_email)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise ConflictError("Email already registered")

    user = User(
        email=normalized_email,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await session.flush()

    return UserResponse.model_validate(user)


async def authenticate_user(
    session: AsyncSession,
    data: LoginRequest,
) -> TokenResponse:
    """Authenticate user credentials and return a JWT bearer token.

    Raises:
        AuthenticationError: If credentials are invalid (generic message).
    """
    normalized_email = User.normalize_email(data.email)

    stmt = select(User).where(User.email == normalized_email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        raise AuthenticationError()

    if not user.is_active:
        raise AuthenticationError()

    access_token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=access_token)


async def get_user_by_id(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User | None:
    """Fetch a user by ID."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
