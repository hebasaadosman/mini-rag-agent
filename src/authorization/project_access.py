"""Pure policy decisions for project isolation and least privilege."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from authentication import CurrentPrincipal


class ProjectPermission(StrEnum):
    READ = "read"
    WRITE = "write"
    MANAGE = "manage"


class ProjectRole(StrEnum):
    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    ADMIN = "admin"


class ProjectMembershipReader(Protocol):
    async def get_role(self, *, project_id: int, principal_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ProjectAccess:
    project_id: int
    principal_id: str
    role: ProjectRole | None
    permission: ProjectPermission
    enforced: bool = True


class ProjectAccessDenied(PermissionError):
    """Raised when a principal has no permission for a project."""


class ProjectAuthorizer:
    """Evaluate membership roles without giving the LLM authorization power."""

    _ROLE_PERMISSIONS: dict[ProjectRole, frozenset[ProjectPermission]] = {
        ProjectRole.VIEWER: frozenset({ProjectPermission.READ}),
        ProjectRole.CONTRIBUTOR: frozenset(
            {ProjectPermission.READ, ProjectPermission.WRITE}
        ),
        ProjectRole.ADMIN: frozenset(
            {
                ProjectPermission.READ,
                ProjectPermission.WRITE,
                ProjectPermission.MANAGE,
            }
        ),
    }

    def __init__(self, membership_reader: ProjectMembershipReader) -> None:
        if not callable(getattr(membership_reader, "get_role", None)):
            raise TypeError("membership_reader must provide get_role.")
        self._membership_reader = membership_reader

    async def require_permission(
        self,
        *,
        principal: CurrentPrincipal,
        project_id: int,
        permission: ProjectPermission,
    ) -> ProjectAccess:
        if not isinstance(project_id, int) or project_id < 1:
            raise ProjectAccessDenied("The project identifier is invalid.")

        # A trusted identity provider can issue this narrowly controlled
        # operational role. It is not derived from user input or the LLM.
        if "platform_admin" in principal.roles:
            return ProjectAccess(
                project_id=project_id,
                principal_id=principal.subject,
                role=ProjectRole.ADMIN,
                permission=permission,
            )

        raw_role = await self._membership_reader.get_role(
            project_id=project_id,
            principal_id=principal.subject,
        )
        try:
            role = ProjectRole(raw_role)
        except (TypeError, ValueError):
            raise ProjectAccessDenied("The principal cannot access this project.") from None

        if permission not in self._ROLE_PERMISSIONS[role]:
            raise ProjectAccessDenied("The principal lacks this project permission.")

        return ProjectAccess(
            project_id=project_id,
            principal_id=principal.subject,
            role=role,
            permission=permission,
        )
