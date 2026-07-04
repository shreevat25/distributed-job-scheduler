"""Project API routes with ownership-scoped authorization."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_project
from app.core.exceptions import ConflictError
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Create a project owned by the current user."""
    # Check for duplicate name within user's projects
    stmt = select(Project).where(
        Project.owner_id == current_user.id,
        Project.name == data.name,
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise ConflictError(f"Project '{data.name}' already exists")

    project = Project(
        owner_id=current_user.id,
        name=data.name,
        description=data.description,
    )
    session.add(project)
    await session.flush()
    return ProjectResponse.model_validate(project)


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="List user's projects",
)
async def list_projects(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    """List all projects owned by the current user."""
    stmt = (
        select(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(Project.created_at)
    )
    result = await session.execute(stmt)
    projects = result.scalars().all()
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details",
)
async def get_project(
    project: Project = Depends(get_owned_project),
) -> ProjectResponse:
    """Get a project by ID (must be owned by current user)."""
    return ProjectResponse.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update a project",
)
async def update_project(
    data: ProjectUpdate,
    project: Project = Depends(get_owned_project),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Partially update a project (must be owned by current user)."""
    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is not None:
        # Check for duplicate name
        stmt = select(Project).where(
            Project.owner_id == project.owner_id,
            Project.name == update_data["name"],
            Project.id != project.id,
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise ConflictError(f"Project '{update_data['name']}' already exists")

    for key, value in update_data.items():
        setattr(project, key, value)

    project.updated_at = datetime.now(UTC)
    await session.flush()
    return ProjectResponse.model_validate(project)
