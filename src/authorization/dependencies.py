"""FastAPI policy-enforcement point for project-scoped routes."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from authentication.dependencies import get_current_principal
from authentication.principal import CurrentPrincipal
from auditing import AuditAction, AuditOutcome, create_audit_event
from authorization.project_access import (
    ProjectAccess,
    ProjectAccessDenied,
    ProjectPermission,
)
from helpers.config import Settings, get_settings


_bearer_scheme = HTTPBearer(auto_error=False)


async def _record_project_access(
    *,
    request: Request,
    principal_id: str,
    project_id: int,
    permission: ProjectPermission,
    outcome: AuditOutcome,
    role: str | None = None,
) -> None:
    """Persist a safe authorization decision; request content is excluded."""
    audit_logger = getattr(request.app, "audit_logger", None)
    if audit_logger is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit logging is not configured.",
        )
    metadata = {"permission": permission.value}
    # A denied request may reference a project that does not exist. Keeping
    # that identifier as JSON metadata avoids a foreign-key failure while
    # preserving an investigation trail without confirming project existence.
    if outcome is AuditOutcome.DENIED:
        metadata["requested_project_id"] = str(project_id)
    if role is not None:
        metadata["role"] = role
    try:
        await audit_logger.record(
            create_audit_event(
                principal_id=principal_id,
                project_id=None if outcome is AuditOutcome.DENIED else project_id,
                action=AuditAction.PROJECT_ACCESS,
                outcome=outcome,
                metadata=metadata,
            )
        )
    except Exception as exc:
        # A protected request must not become an unaudited request.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit logging is temporarily unavailable.",
        ) from exc


def require_project_permission(permission: ProjectPermission):
    """Create a route dependency that authorizes the path project_id."""

    async def dependency(
        request: Request,
        project_id: int,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(_bearer_scheme),
        ],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> ProjectAccess:
        # Keeps local development compatible while making production opt-in
        # explicit. AUTHZ_ENABLED must never be false in a protected deployment.
        if not settings.AUTHZ_ENABLED:
            return ProjectAccess(
                project_id=project_id,
                principal_id="unauthenticated-local",
                role=None,
                permission=permission,
                enforced=False,
            )
        if not settings.AUTH_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization requires authentication to be enabled.",
            )
        principal = await get_current_principal(request, credentials, settings)
        authorizer = getattr(request.app, "project_authorizer", None)
        if authorizer is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Project authorization is not configured.",
            )
        try:
            access = await authorizer.require_permission(
                principal=principal,
                project_id=project_id,
                permission=permission,
            )
        except ProjectAccessDenied:
            await _record_project_access(
                request=request,
                principal_id=principal.subject,
                project_id=project_id,
                permission=permission,
                outcome=AuditOutcome.DENIED,
            )
            # Do not reveal whether a project exists to an unauthorized caller.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this project.",
            ) from None
        await _record_project_access(
            request=request,
            principal_id=access.principal_id,
            project_id=project_id,
            permission=permission,
            outcome=AuditOutcome.ALLOWED,
            role=access.role.value if access.role else None,
        )
        return access

    return dependency
