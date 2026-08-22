# Local Keycloak OIDC sandbox

This is a **development and integration sandbox only**. The FastAPI BFF
remains provider-neutral: Keycloak appears only in this Docker Compose file,
realm export, and integration instructions.

## What it validates

The sandbox validates the real OIDC Authorization Code flow with PKCE:

1. FastAPI creates a Redis-backed transaction and redirects to the IdP.
2. Keycloak authenticates the sandbox user and returns an authorization code.
3. FastAPI exchanges the code server-to-server, validates the RS256 ID token
   using Keycloak JWKS, issuer, audience, and nonce, and maps the `roles` claim.
4. FastAPI stores an opaque session in Redis, then protects `/auth/me` and
   state-changing endpoints with the session plus CSRF protection.

## Local setup

Copy the two ignored files:

```bash
cp docker/env/.env.keycloak-sandbox.example docker/env/.env.keycloak-sandbox
cp docker/env/.env.oidc-sandbox.example docker/env/.env.oidc-sandbox
```

The local BFF derives Redis database `1` from the already-configured Celery
Redis URL, so the Redis password is not duplicated. Production remains
explicit: it must provide `AUTH_SESSION_REDIS_URL` itself.

The realm supplies two deliberately non-production users:

| User | Password | Role |
| --- | --- | --- |
| `heba.admin` | `local-keycloak-test-password` | `platform_admin` |
| `analyst.user` | `local-keycloak-test-password` | `analyst` |

Start only the sandbox and application prerequisites:

```bash
docker compose \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.dev.yml \
  -f docker/docker-compose.oidc-sandbox.yml \
  up -d --build redis pgvector rabbitmq keycloak fastapi
```

The browser-facing Keycloak issuer is `https://127.0.0.1:8444/realms/mini-rag`.
FastAPI calls Keycloak's internal Docker name for token exchange and JWKS. That
separation is configuration only and is useful for any later OIDC provider
behind a private network.

## HTTPS boundary

Keycloak itself runs at local HTTPS with a development certificate, so its
authentication cookies are exercised as Secure cookies. The BFF callback is
still loopback HTTP and uses `AUTH_COOKIE_SECURE=false`; this remains a
local-only exception. A production-like BFF test must terminate TLS (for
example through a local reverse proxy and trusted development certificate),
set `AUTH_COOKIE_SECURE=true`, and register the corresponding HTTPS callback
and frontend URLs in the IdP. No production or real-user credentials belong in
this sandbox.

## Entra ID later

Replace only the issuer, authorization endpoint, token endpoint, JWKS URL,
client registration, redirect URI, and configured roles claim. No Keycloak
dependency exists in the FastAPI OIDC implementation.
