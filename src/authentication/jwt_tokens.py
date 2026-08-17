"""Strict verification for access tokens issued by a trusted identity provider."""

from __future__ import annotations

from typing import Any

import jwt
from jwt import InvalidTokenError

from .principal import CurrentPrincipal


class JWTAuthenticationError(ValueError):
    """Raised when an access token cannot be trusted."""


class JWTTokenVerifier:
    """Verify signed JWT access tokens and map claims to a principal."""

    _SUPPORTED_ALGORITHMS = frozenset({"HS256"})

    def __init__(
        self,
        *,
        secret: str | None,
        algorithm: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 0,
    ) -> None:
        normalized_secret = str(secret or "").strip()
        normalized_algorithm = str(algorithm or "").strip().upper()
        if len(normalized_secret) < 32:
            raise ValueError("AUTH_JWT_SECRET must contain at least 32 characters.")
        if normalized_algorithm not in self._SUPPORTED_ALGORITHMS:
            raise ValueError("AUTH_JWT_ALGORITHM must be HS256.")
        if not str(issuer or "").strip() or not str(audience or "").strip():
            raise ValueError("JWT issuer and audience must be configured.")
        if leeway_seconds < 0:
            raise ValueError("JWT leeway cannot be negative.")

        self._secret = normalized_secret
        self._algorithm = normalized_algorithm
        self._issuer = issuer.strip()
        self._audience = audience.strip()
        self._leeway_seconds = leeway_seconds

    def verify(self, token: str) -> CurrentPrincipal:
        """Verify a bearer token; never trust unverified claims."""
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_seconds,
                options={"require": ["exp", "iat", "sub"]},
            )
        except InvalidTokenError as exc:
            raise JWTAuthenticationError("The access token is invalid or expired.") from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise JWTAuthenticationError("The access token has no valid subject.")

        raw_roles = claims.get("roles", [])
        if not isinstance(raw_roles, list) or any(
            not isinstance(role, str) or not role.strip() for role in raw_roles
        ):
            raise JWTAuthenticationError("The access token has invalid role claims.")

        return CurrentPrincipal(
            subject=subject.strip(),
            roles=tuple(dict.fromkeys(role.strip() for role in raw_roles)),
        )
