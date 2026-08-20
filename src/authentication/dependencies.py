"""FastAPI dependencies for BFF sessions and explicit development bearer auth."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from helpers.config import Settings, get_settings

from .jwt_tokens import JWTAuthenticationError, JWTTokenVerifier
from .principal import CurrentPrincipal


_bearer_scheme = HTTPBearer(auto_error=False)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _authentication_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication is not configured for this deployment.",
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required or the session has expired.",
    )


def _csrf_rejected() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CSRF validation failed.",
    )


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentPrincipal:
    """Resolve a trusted browser session or a development-only bearer token."""
    if not settings.AUTH_ENABLED:
        raise _authentication_unavailable()

    mode = settings.AUTH_MODE.strip().lower()
    if mode == "bff_oidc":
        return await authenticate_browser_session(request, settings)
    is_development_environment = settings.APP_ENV.strip().lower() in {
        "development",
        "dev",
        "local",
        "test",
    }
    if (
        mode == "development_bearer"
        and is_development_environment
        and settings.AUTH_DEVELOPMENT_MANUAL_TOKEN_ENABLED
    ):
        return authenticate_bearer_credentials(credentials, settings)
    raise _authentication_unavailable()


async def authenticate_browser_session(request: Request, settings: Settings) -> CurrentPrincipal:
    """Load a server-side session and enforce CSRF before state changes."""
    session_id = request.cookies.get(settings.AUTH_SESSION_COOKIE_NAME)
    store = getattr(request.app, "auth_session_store", None)
    if not session_id or store is None:
        raise _unauthorized()
    session = await store.get_session(session_id)
    if session is None:
        raise _unauthorized()
    if request.method.upper() not in _SAFE_METHODS:
        cookie_token = request.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
        header_token = request.headers.get(settings.AUTH_CSRF_HEADER_NAME)
        if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
            raise _csrf_rejected()
        if not hmac.compare_digest(session.csrf_token, cookie_token):
            raise _csrf_rejected()
    request.state.auth_session_id = session.session_id
    return CurrentPrincipal(subject=session.subject, roles=session.roles)


def authenticate_bearer_credentials(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> CurrentPrincipal:
    """Verify bearer credentials for the explicit local-development mode only."""
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
