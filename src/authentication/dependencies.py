"""FastAPI dependencies that establish an authenticated request identity."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from helpers.config import Settings, get_settings

from .jwt_tokens import JWTAuthenticationError, JWTTokenVerifier
from .principal import CurrentPrincipal


_bearer_scheme = HTTPBearer(auto_error=False)


def _authentication_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication is not configured for this deployment.",
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentPrincipal:
    """Return a trusted identity or reject the request before business logic."""
    if not settings.AUTH_ENABLED:
        raise _authentication_unavailable()
    return authenticate_bearer_credentials(credentials, settings)


def authenticate_bearer_credentials(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> CurrentPrincipal:
    """Verify credentials for dependencies that need conditional AuthZ."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        verifier = JWTTokenVerifier(
            secret=settings.AUTH_JWT_SECRET,
            algorithm=settings.AUTH_JWT_ALGORITHM,
            issuer=settings.AUTH_JWT_ISSUER,
            audience=settings.AUTH_JWT_AUDIENCE,
            leeway_seconds=settings.AUTH_JWT_LEEWAY_SECONDS,
        )
        return verifier.verify(credentials.credentials)
    except (JWTAuthenticationError, ValueError):
        raise _unauthorized() from None
