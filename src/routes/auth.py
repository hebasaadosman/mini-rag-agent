"""OIDC BFF endpoints and current authenticated identity inspection."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from authentication import CurrentPrincipal
from authentication.dependencies import get_current_principal
from authentication.oidc import OIDCAuthenticationError
from helpers.config import Settings, get_settings


auth_router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
_STATE_COOKIE_NAME = "mini_rag_oidc_state"


class CurrentPrincipalResponse(BaseModel):
    subject: str
    roles: list[str]


def _require_bff(settings: Settings) -> None:
    if not settings.AUTH_ENABLED or settings.AUTH_MODE.strip().lower() != "bff_oidc":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OIDC browser authentication is not enabled.",
        )


def _cookie_options(settings: Settings) -> dict:
    return {
        "secure": settings.AUTH_COOKIE_SECURE,
        "httponly": True,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": "/",
    }


@auth_router.get("/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def login(request: Request, settings: Annotated[Settings, Depends(get_settings)]):
    """Start a provider-neutral Authorization Code + PKCE login redirect."""
    _require_bff(settings)
    store = getattr(request.app, "auth_session_store", None)
    oidc_client = getattr(request.app, "oidc_client", None)
    if store is None or oidc_client is None:
        raise HTTPException(status_code=503, detail="OIDC authentication is not configured.")
    transaction = await store.create_transaction()
    response = RedirectResponse(oidc_client.authorization_url(transaction), status_code=307)
    response.set_cookie(
        _STATE_COOKIE_NAME,
        transaction.state,
        max_age=settings.AUTH_OIDC_TRANSACTION_TTL_SECONDS,
        **_cookie_options(settings),
    )
    return response


@auth_router.get("/callback")
async def callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Exchange a verified OIDC authorization code for a server-side session."""
    _require_bff(settings)
    if error or not code or not state:
        raise HTTPException(status_code=401, detail="Identity provider login was not completed.")
    state_cookie = request.cookies.get(_STATE_COOKIE_NAME)
    if not state_cookie or not hmac.compare_digest(state_cookie, state):
        raise HTTPException(status_code=401, detail="OIDC login state validation failed.")
    store = request.app.auth_session_store
    oidc_client = request.app.oidc_client
    transaction = await store.get_transaction(state)
    await store.delete_transaction(state)
    if transaction is None:
        raise HTTPException(status_code=401, detail="OIDC login transaction expired.")
    try:
        id_token = await oidc_client.exchange_code(code=code, transaction=transaction)
        principal = await oidc_client.validate_id_token(token=id_token, nonce=transaction.nonce)
    except OIDCAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Identity provider validation failed.") from exc
    session = await store.create_session(subject=principal.subject, roles=principal.roles)
    response = RedirectResponse(settings.AUTH_FRONTEND_SUCCESS_URL, status_code=303)
    response.set_cookie(
        settings.AUTH_SESSION_COOKIE_NAME,
        session.session_id,
        max_age=settings.AUTH_SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        **_cookie_options(settings),
    )
    response.set_cookie(
        settings.AUTH_CSRF_COOKIE_NAME,
        session.csrf_token,
        max_age=settings.AUTH_SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=False,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    response.delete_cookie(_STATE_COOKIE_NAME, path="/")
    return response


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    _: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Invalidate the server-side session and clear browser cookies."""
    session_id = getattr(request.state, "auth_session_id", None)
    if session_id:
        await request.app.auth_session_store.delete_session(session_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.AUTH_SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(settings.AUTH_CSRF_COOKIE_NAME, path="/")
    return response


@auth_router.get("/me", response_model=CurrentPrincipalResponse)
async def get_authenticated_principal(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> CurrentPrincipalResponse:
    return CurrentPrincipalResponse(subject=principal.subject, roles=list(principal.roles))
