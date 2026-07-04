"""Authentication API routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user with email and password.

    - Email is normalized (lowercased, trimmed) before storage
    - Password must be at least 8 characters
    - Duplicate emails are rejected
    """
    return await auth_service.register_user(session, data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT",
)
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email and password to receive a JWT bearer token.

    Returns a short-lived access token (default 30 minutes).
    Invalid credentials return a generic error to prevent user enumeration.
    """
    return await auth_service.authenticate_user(session, data)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the profile of the currently authenticated user.

    Requires a valid JWT bearer token in the Authorization header.
    Never returns password_hash.
    """
    return UserResponse.model_validate(current_user)
