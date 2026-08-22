"""Project provisioning and membership management for project isolation."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from authentication import CurrentPrincipal
from authentication.dependencies import get_current_principal
from auditing import AuditAction, AuditOutcome, create_audit_event
from authorization import ProjectAccess, ProjectPermission, ProjectRole
from authorization.dependencies import require_project_permission


projects_router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    description: str | None = Field(default=None, max_length=1000)


class ProjectResponse(BaseModel):
    project_id: int
    role: ProjectRole


class GrantProjectRoleRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=255)
    role: ProjectRole


class ProjectMemberResponse(BaseModel):
    principal_id: str
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
    project = await request.app.project_model.create_project_with_creator_admin(
        description=payload.description,
        creator_principal_id=principal.subject,
    )
    await request.app.audit_logger.record(
        create_audit_event(
            principal_id=principal.subject,
            project_id=project.project_id,
            action=AuditAction.PROJECT_CREATED,
            outcome=AuditOutcome.SUCCEEDED,
            metadata={"role": ProjectRole.ADMIN.value},
        )
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
    access: Annotated[
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
    await request.app.audit_logger.record(
        create_audit_event(
            principal_id=access.principal_id,
            project_id=project_id,
            action=AuditAction.PROJECT_MEMBER_ROLE_GRANTED,
            outcome=AuditOutcome.SUCCEEDED,
            metadata={
                "role": payload.role.value,
                "target_principal_id": payload.principal_id.strip(),
            },
        )
    )
    return ProjectResponse(project_id=project_id, role=payload.role)


@projects_router.get(
    "/{project_id}/members",
    response_model=list[ProjectMemberResponse],
)
async def list_project_members(
    request: Request,
    project_id: int,
    _: Annotated[
        ProjectAccess,
        Depends(require_project_permission(ProjectPermission.MANAGE)),
    ],
) -> list[ProjectMemberResponse]:
    """List memberships only to project admins."""
    members = await request.app.project_membership_model.list_members(
        project_id=project_id
    )
    return [
        ProjectMemberResponse(
            principal_id=member.principal_id,
            role=ProjectRole(member.role),
        )
        for member in members
    ]


@projects_router.delete(
    "/{project_id}/members/{principal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_project_membership(
    request: Request,
    project_id: int,
    principal_id: str,
    access: Annotated[
        ProjectAccess,
        Depends(require_project_permission(ProjectPermission.MANAGE)),
    ],
) -> None:
    """Revoke a member; the next policy check takes effect immediately."""
    normalized_principal_id = principal_id.strip()
    membership = await request.app.project_membership_model.revoke_role(
        project_id=project_id,
        principal_id=normalized_principal_id,
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project membership was not found.",
        )
    await request.app.audit_logger.record(
        create_audit_event(
            principal_id=access.principal_id,
            project_id=project_id,
            action=AuditAction.PROJECT_MEMBER_REVOKED,
            outcome=AuditOutcome.SUCCEEDED,
            metadata={"target_principal_id": normalized_principal_id},
        )
    )
