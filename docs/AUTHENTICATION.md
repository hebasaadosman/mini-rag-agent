# Production authentication

## Browser flow

Production browser authentication uses **OIDC Authorization Code Flow with PKCE** and a Backend-for-Frontend (BFF) session:

1. The Angular application sends the user to `GET /api/v1/auth/login`.
2. The backend generates `state`, `nonce`, and a PKCE verifier, stores the transaction in Redis, and redirects to the configured OIDC provider.
3. The provider redirects to `GET /api/v1/auth/callback` with an authorization code.
4. The backend verifies the state cookie, exchanges the code, validates the signed ID token against the configured issuer, audience, nonce, and JWKS, then creates a server-side Redis session.
5. The browser receives only an opaque `HttpOnly`, `Secure`, `SameSite=Lax` session cookie. Angular never receives an access token or refresh token.
6. API requests resolve the session on the backend. Project membership and RBAC remain the authorization source of truth.

`POST`, `PUT`, `PATCH`, and `DELETE` requests additionally require the CSRF cookie value in the configured CSRF request header. The backend validates both values against the server-side session.

## Development bearer mode

Manual JWT entry is not a production login mechanism. It is allowed only when all of the following are true:

- `AUTH_MODE=development_bearer`
- `AUTH_DEVELOPMENT_MANUAL_TOKEN_ENABLED=true`
- The deployment is a local/development environment

Production must use `AUTH_MODE=bff_oidc` and keep `AUTH_DEVELOPMENT_MANUAL_TOKEN_ENABLED=false`.

## Session policy

- Idle timeout: 30 minutes (`AUTH_SESSION_IDLE_TIMEOUT_SECONDS=1800`).
- Absolute lifetime: 8 hours (`AUTH_SESSION_ABSOLUTE_TIMEOUT_SECONDS=28800`).
- Logout deletes the Redis session and clears both browser cookies.
- Expired or revoked sessions return `401`; the production frontend presents the SSO sign-in action again.
- Refresh tokens, when a provider issues them, remain a backend concern and are never sent to Angular.

## Required production environment variables

| Variable | Purpose |
| --- | --- |
| `AUTH_ENABLED=true` | Enables authentication. |
| `AUTHZ_ENABLED=true` | Enforces project authorization. |
| `AUTH_MODE=bff_oidc` | Selects the production BFF flow. |
| `AUTH_SESSION_REDIS_URL` | Dedicated Redis database/namespace for sessions. |
| `AUTH_SESSION_IDLE_TIMEOUT_SECONDS` | Idle timeout. |
| `AUTH_SESSION_ABSOLUTE_TIMEOUT_SECONDS` | Maximum session lifetime. |
| `AUTH_COOKIE_SECURE=true` | Requires HTTPS cookies in production. |
| `AUTH_FRONTEND_SUCCESS_URL` | Safe post-login frontend URL. |
| `AUTH_OIDC_ISSUER` | Exact OIDC issuer URL. |
| `AUTH_OIDC_CLIENT_ID` | Registered OIDC client ID. |
| `AUTH_OIDC_CLIENT_SECRET` | Optional confidential-client secret; store only in deployment secrets. |
| `AUTH_OIDC_REDIRECT_URI` | Registered backend callback URL. |
| `AUTH_OIDC_AUTHORIZATION_ENDPOINT` | Provider authorization endpoint. |
| `AUTH_OIDC_TOKEN_ENDPOINT` | Provider token endpoint. |
| `AUTH_OIDC_JWKS_URL` | Provider JSON Web Key Set URL. |
| `AUTH_OIDC_SCOPES` | Requested OIDC scopes, normally `openid profile email`. |
| `AUTH_OIDC_ROLES_CLAIM` | Claim used to map provider roles. |
| `AUTH_OIDC_ALLOWED_ALGORITHMS` | Asymmetric ID-token algorithms, e.g. `RS256,ES256`. |

Do not set a provider URL, client secret, redirect URI, or production cookie setting in committed source code. The implementation is provider-neutral OIDC; Keycloak is only suitable as a local development provider.

## Deployment secret

GitHub Actions requires the protected environment secret
`PROD_AUTH_SESSION_REDIS_URL` for every production deployment. It is written
to `AUTH_SESSION_REDIS_URL` in the server-side `docker/env/.env.app` file and
must point to the dedicated session Redis database or namespace (normally
database `1`, separate from Celery's result database `0`). The workflow fails
before connecting to the server when the secret is missing.
