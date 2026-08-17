"""Project provisioning and membership management for project isolation."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from authentication import CurrentPrincipal
from authentication.dependencies import get_current_principal
from authorization import ProjectAccess, ProjectPermission, ProjectRole
from authorization.dependencies import require_project_permission
from models.db_schemes.mini_rag.schemes import Project


projects_router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    description: str | None = Field(default=None, max_length=1000)


class ProjectResponse(BaseModel):
    project_id: int
    role: ProjectRole


class GrantProjectRoleRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=255)
    role: ProjectRole


@projects_router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    request: Request,
    payload: CreateProjectRequest,
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> ProjectResponse:
    """Create a project and make its authenticated creator the first admin."""
    project = await request.app.project_model.create_project(
        Project(project_description=payload.description)
    )
    await request.app.project_membership_model.grant_role(
        project_id=project.project_id,
        principal_id=principal.subject,
        role=ProjectRole.ADMIN.value,
    )
    return ProjectResponse(project_id=project.project_id, role=ProjectRole.ADMIN)


@projects_router.put(
    "/{project_id}/members",
    response_model=ProjectResponse,
)
async def grant_project_role(
    request: Request,
    project_id: int,
    payload: GrantProjectRoleRequest,
    _: Annotated[
        ProjectAccess,
        Depends(require_project_permission(ProjectPermission.MANAGE)),
    ],
) -> ProjectResponse:
    """Grant or update a role; only project admins can manage membership."""
    await request.app.project_membership_model.grant_role(
        project_id=project_id,
        principal_id=payload.principal_id.strip(),
        role=payload.role.value,
    )
    return ProjectResponse(project_id=project_id, role=payload.role)
