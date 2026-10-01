"""Retry policy API routes."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_project
from app.core.exceptions import ConflictError, NotFoundError, ForbiddenError
from app.models.project import Project
from app.models.retry_policy import RetryPolicy
from app.models.user import User
from app.repositories import retry_policy_repository
from app.schemas.retry_policy import (
    RetryPolicyCreate,
    RetryPolicyResponse,
    RetryPolicyUpdate,
)

router = APIRouter(tags=["retry-policies"])


@router.post(
    "/projects/{project_id}/retry-policies",
    response_model=RetryPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a retry policy",
)
async def create_retry_policy(
    data: RetryPolicyCreate,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_db),
) -> RetryPolicyResponse:
    """Create a retry policy within a project."""
    if await retry_policy_repository.find_by_name(session, project.id, data.name) is not None:
        raise ConflictError(f"Retry policy '{data.name}' already exists in this project")

    policy = await retry_policy_repository.create(
        session,
        RetryPolicy(
            project_id=project.id,
            name=data.name,
            strategy=data.strategy,
            max_attempts=data.max_attempts,
            base_delay_seconds=data.base_delay_seconds,
            max_delay_seconds=data.max_delay_seconds,
            jitter=data.jitter,
            jitter_factor=data.jitter_factor,
        ),
    )
    return RetryPolicyResponse.model_validate(policy)


@router.get(
    "/projects/{project_id}/retry-policies",
    response_model=list[RetryPolicyResponse],
    summary="List retry policies for a project",
)
async def list_retry_policies(
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_db),
) -> list[RetryPolicyResponse]:
    """List all retry policies belonging to a project."""
    policies = await retry_policy_repository.list_for_project(session, project.id)
    return [RetryPolicyResponse.model_validate(p) for p in policies]


@router.get(
    "/retry-policies/{policy_id}",
    response_model=RetryPolicyResponse,
    summary="Get retry policy details",
)
async def get_retry_policy(
    policy_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RetryPolicyResponse:
    """Get a retry policy by ID, ensuring project ownership."""
    policy = await retry_policy_repository.get_owned(session, policy_id, current_user.id)
    if policy is None:
        raise NotFoundError("RetryPolicy", str(policy_id))
    return RetryPolicyResponse.model_validate(policy)


@router.patch(
    "/retry-policies/{policy_id}",
    response_model=RetryPolicyResponse,
    summary="Update a retry policy",
)
async def update_retry_policy(
    policy_id: uuid.UUID,
    data: RetryPolicyUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RetryPolicyResponse:
    """Partially update a retry policy, ensuring project ownership."""
    policy = await retry_policy_repository.get_owned(session, policy_id, current_user.id)
    if policy is None:
        raise NotFoundError("RetryPolicy", str(policy_id))

    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is not None:
        duplicate = await retry_policy_repository.find_by_name(
            session, policy.project_id, update_data["name"], exclude_id=policy.id
        )
        if duplicate is not None:
            raise ConflictError(f"Retry policy '{update_data['name']}' already exists")

    for key, value in update_data.items():
        setattr(policy, key, value)

    policy.updated_at = datetime.now(UTC)
    await session.flush()
    return RetryPolicyResponse.model_validate(policy)
