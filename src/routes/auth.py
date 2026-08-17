"""Authentication inspection endpoints; authorization is added separately."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from authentication import CurrentPrincipal
from authentication.dependencies import get_current_principal


auth_router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class CurrentPrincipalResponse(BaseModel):
    subject: str
    roles: list[str]


@auth_router.get("/me", response_model=CurrentPrincipalResponse)
async def get_authenticated_principal(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> CurrentPrincipalResponse:
    """Return the verified identity carried by the caller's bearer token."""
    return CurrentPrincipalResponse(
        subject=principal.subject,
        roles=list(principal.roles),
    )
