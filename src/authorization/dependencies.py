"""FastAPI policy-enforcement point for project-scoped routes."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from authentication.dependencies import authenticate_bearer_credentials
from authorization.project_access import (
    ProjectAccess,
    ProjectAccessDenied,
    ProjectPermission,
)
from helpers.config import Settings, get_settings


_bearer_scheme = HTTPBearer(auto_error=False)


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

        principal = authenticate_bearer_credentials(credentials, settings)
        authorizer = getattr(request.app, "project_authorizer", None)
        if authorizer is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Project authorization is not configured.",
            )
        try:
            return await authorizer.require_permission(
                principal=principal,
                project_id=project_id,
                permission=permission,
            )
        except ProjectAccessDenied:
            # Do not reveal whether a project exists to an unauthorized caller.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this project.",
            ) from None

    return dependency
