"""Authentication service — registration, login, and token validation."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories import user_repository
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

    if await user_repository.get_by_email(session, normalized_email) is not None:
        raise ConflictError("Email already registered")

    user = await user_repository.create(
        session,
        User(
            email=normalized_email,
            password_hash=hash_password(data.password),
        ),
    )

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

    user = await user_repository.get_by_email(session, normalized_email)

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
    return await user_repository.get_by_id(session, user_id)
