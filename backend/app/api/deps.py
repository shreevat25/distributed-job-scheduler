"""FastAPI dependency injection helpers for auth, DB, and ownership."""

import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.models.dlq_entry import DLQEntry
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.repositories import (
    dlq_repository,
    job_repository,
    project_repository,
    queue_repository,
    user_repository,
)

bearer_scheme = HTTPBearer()


async def get_db(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncSession:
    """Provide an async database session."""
    return session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the JWT bearer token.

    This verifies the token, extracts the user ID, and fetches the user
    from the database (not relying solely on JWT claims for authorization).

    Raises:
        HTTPException 401: If token is invalid or user not found.
    """
    try:
        payload = decode_access_token(credentials.credentials)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user = await user_repository.get_active_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return user


async def get_owned_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Project:
    """Fetch a project, ensuring it belongs to the current user.

    Uses an authorization-scoped query (filters by owner_id in the WHERE clause)
    rather than fetching globally and checking ownership after.

    Raises:
        NotFoundError: If project doesn't exist or isn't owned by user.
    """
    project = await project_repository.get_owned(session, project_id, current_user.id)
    if project is None:
        raise NotFoundError("Project", str(project_id))

    return project


async def get_owned_queue(
    queue_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Queue:
    """Fetch a queue, ensuring it belongs to a project owned by the current user.

    Authorization chain: queue → project → owner.

    Raises:
        NotFoundError: If queue doesn't exist or user doesn't own its project.
    """
    queue = await queue_repository.get_owned(session, queue_id, current_user.id)
    if queue is None:
        raise NotFoundError("Queue", str(queue_id))

    return queue


async def get_user_queue_ids(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    """Get all queue IDs accessible by the current user (for job listing auth)."""
    return await queue_repository.list_ids_for_owner(session, current_user.id)


async def get_owned_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Job:
    """Fetch a job, ensuring it belongs to a project owned by current user."""
    job = await job_repository.get_owned(session, job_id, current_user.id)
    if job is None:
        raise NotFoundError("Job", str(job_id))
    return job


async def get_owned_dlq_entry(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DLQEntry:
    """Fetch a DLQ entry, ensuring it belongs to a project owned by current user."""
    entry = await dlq_repository.get_owned(session, id, current_user.id)
    if entry is None:
        raise NotFoundError("DLQEntry", str(id))
    return entry

