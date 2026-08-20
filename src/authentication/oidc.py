"""Provider-neutral OIDC Authorization Code + PKCE integration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from helpers.config import Settings

from .principal import CurrentPrincipal
from .sessions import OIDCLoginTransaction


class OIDCAuthenticationError(ValueError):
    """Raised when an OIDC response or token cannot be trusted."""


@dataclass(frozen=True, slots=True)
class OIDCConfiguration:
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_url: str
    scopes: tuple[str, ...]
    roles_claim: str
    allowed_algorithms: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: Settings) -> "OIDCConfiguration":
        fields = {
            "AUTH_OIDC_ISSUER": settings.AUTH_OIDC_ISSUER,
            "AUTH_OIDC_CLIENT_ID": settings.AUTH_OIDC_CLIENT_ID,
            "AUTH_OIDC_REDIRECT_URI": settings.AUTH_OIDC_REDIRECT_URI,
            "AUTH_OIDC_AUTHORIZATION_ENDPOINT": settings.AUTH_OIDC_AUTHORIZATION_ENDPOINT,
            "AUTH_OIDC_TOKEN_ENDPOINT": settings.AUTH_OIDC_TOKEN_ENDPOINT,
            "AUTH_OIDC_JWKS_URL": settings.AUTH_OIDC_JWKS_URL,
        }
        missing = [name for name, value in fields.items() if not str(value or "").strip()]
        if missing:
            raise ValueError(f"OIDC configuration is missing: {', '.join(missing)}.")
        algorithms = tuple(
            algorithm.strip().upper()
            for algorithm in settings.AUTH_OIDC_ALLOWED_ALGORITHMS.split(",")
            if algorithm.strip()
        )
        if not algorithms or any(algorithm.startswith("HS") for algorithm in algorithms):
            raise ValueError("OIDC algorithms must use asymmetric signing algorithms.")
        return cls(
            issuer=str(settings.AUTH_OIDC_ISSUER).rstrip("/"),
            client_id=str(settings.AUTH_OIDC_CLIENT_ID),
            client_secret=(str(settings.AUTH_OIDC_CLIENT_SECRET).strip() or None),
            redirect_uri=str(settings.AUTH_OIDC_REDIRECT_URI),
            authorization_endpoint=str(settings.AUTH_OIDC_AUTHORIZATION_ENDPOINT),
            token_endpoint=str(settings.AUTH_OIDC_TOKEN_ENDPOINT),
            jwks_url=str(settings.AUTH_OIDC_JWKS_URL),
            scopes=tuple(scope for scope in settings.AUTH_OIDC_SCOPES.split() if scope),
            roles_claim=settings.AUTH_OIDC_ROLES_CLAIM,
            allowed_algorithms=algorithms,
        )


class OIDCClient:
    def __init__(self, configuration: OIDCConfiguration, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._configuration = configuration
        self._http_client = http_client

    @staticmethod
    def pkce_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def authorization_url(self, transaction: OIDCLoginTransaction) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._configuration.client_id,
                "redirect_uri": self._configuration.redirect_uri,
                "scope": " ".join(self._configuration.scopes),
                "state": transaction.state,
                "nonce": transaction.nonce,
                "code_challenge": self.pkce_challenge(transaction.code_verifier),
                "code_challenge_method": "S256",
            }
        )
        return f"{self._configuration.authorization_endpoint}?{query}"

    async def exchange_code(self, *, code: str, transaction: OIDCLoginTransaction) -> str:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._configuration.redirect_uri,
            "client_id": self._configuration.client_id,
            "code_verifier": transaction.code_verifier,
        }
        if self._configuration.client_secret:
            payload["client_secret"] = self._configuration.client_secret
        response = await self._request("POST", self._configuration.token_endpoint, data=payload)
        try:
            body = response.json()
            token = body["id_token"]
        except (KeyError, ValueError, TypeError) as exc:
            raise OIDCAuthenticationError("The OIDC token response has no id_token.") from exc
        if not isinstance(token, str) or not token:
            raise OIDCAuthenticationError("The OIDC id_token is invalid.")
        return token

    async def validate_id_token(self, *, token: str, nonce: str) -> CurrentPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            algorithm = str(header.get("alg", "")).upper()
        except jwt.InvalidTokenError as exc:
            raise OIDCAuthenticationError("The OIDC id_token header is invalid.") from exc
        if not isinstance(kid, str) or algorithm not in self._configuration.allowed_algorithms:
            raise OIDCAuthenticationError("The OIDC id_token uses an untrusted signing key.")

        jwks = (await self._request("GET", self._configuration.jwks_url)).json()
        key_data = next(
            (key for key in jwks.get("keys", []) if key.get("kid") == kid), None
        )
        if key_data is None:
            raise OIDCAuthenticationError("The OIDC signing key is unavailable.")
        key = self._key_from_jwk(key_data, algorithm)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=list(self._configuration.allowed_algorithms),
                audience=self._configuration.client_id,
                issuer=self._configuration.issuer,
                options={"require": ["exp", "iat", "sub", "nonce"]},
            )
        except jwt.InvalidTokenError as exc:
            raise OIDCAuthenticationError("The OIDC id_token is invalid or expired.") from exc
        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OIDCAuthenticationError("The OIDC nonce does not match the login transaction.")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise OIDCAuthenticationError("The OIDC id_token has no valid subject.")
        return CurrentPrincipal(subject=subject.strip(), roles=self._roles_from_claims(claims))

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if self._http_client is not None:
            response = await self._http_client.request(method, url, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(method, url, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OIDCAuthenticationError("The identity provider request failed.") from exc
        return response

    @staticmethod
    def _key_from_jwk(jwk: dict[str, Any], algorithm: str):
        """Build a verification key through PyJWT's algorithm registry.

        This intentionally avoids provider- or key-type-specific imports.  The
        algorithm is already allow-listed from configuration before this call.
        """
        try:
            return jwt.get_algorithm_by_name(algorithm).from_jwk(json.dumps(jwk))
        except (AttributeError, ValueError, TypeError) as exc:
            raise OIDCAuthenticationError("The OIDC signing key is unsupported.") from exc

    def _roles_from_claims(self, claims: dict[str, Any]) -> tuple[str, ...]:
        raw_roles = claims.get(self._configuration.roles_claim, [])
        if raw_roles is None:
            return ()
        if isinstance(raw_roles, str):
            raw_roles = [raw_roles]
        if not isinstance(raw_roles, list) or any(not isinstance(role, str) for role in raw_roles):
            raise OIDCAuthenticationError("The OIDC role claims are invalid.")
        return tuple(dict.fromkeys(role.strip() for role in raw_roles if role.strip()))
