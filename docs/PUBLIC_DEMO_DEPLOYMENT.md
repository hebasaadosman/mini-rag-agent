# Public portfolio demo deployment

This document prepares a small public demo; it does not authorize a deploy.
The browser reaches only the Nginx TLS listener. FastAPI, PostgreSQL/pgvector,
Redis, RabbitMQ, Qdrant, workers, and Keycloak's database stay on the private
Docker network.

## Intended services

Use **only** `docker/docker-compose.demo.yml`. It is named `mini-rag-demo`
and has its own `mini-rag-demo_*` volumes and `mini-rag-demo_backend` network;
it must never be combined with a legacy Compose file.

- Nginx image containing the production Angular build.
- FastAPI BFF.
- PostgreSQL/pgvector, with a separate Keycloak database and database role.
- Redis (Celery results in database `0`; BFF sessions in database `1`).
- RabbitMQ, file/index/maintenance workers, and Celery beat.
- Qdrant without a public port.
- Keycloak in `start` mode, plus a one-shot realm/user provisioner.

Prometheus, Grafana, Flower, and exporters are assigned an `observability`
profile and are not part of the normal demo invocation.

## Files to create outside Git

Copy these ignored templates and replace all placeholders through the secret
store or a mode-`600` host file:

```bash
cp docker/env/.env.demo.nginx.example docker/env/.env.demo.nginx
cp docker/env/.env.demo.keycloak.example docker/env/.env.demo.keycloak
cp docker/env/.env.demo.provisioner.example docker/env/.env.demo.provisioner
cp docker/env/.env.demo.postgres.example docker/env/.env.demo.postgres
cp docker/env/.env.demo.keycloak-db.example docker/env/.env.demo.keycloak-db
cp docker/env/.env.demo.redis.example docker/env/.env.demo.redis
cp docker/env/.env.demo.rabbitmq.example docker/env/.env.demo.rabbitmq
cp docker/env/.env.demo-app.example docker/env/.env.demo-app
cp docker/env/.env.demo.worker-file.example docker/env/.env.demo.worker-file
cp docker/env/.env.demo.worker-index.example docker/env/.env.demo.worker-index
cp docker/env/.env.demo.worker-maintenance.example docker/env/.env.demo.worker-maintenance
```

Each service reads only its own demo environment file. In particular, Nginx
does not receive database, Keycloak bootstrap, or demo-user credentials; the
realm provisioner alone receives the demo-user credential. File, maintenance,
and beat workers receive no LLM credential; only the index worker receives the
embedding-provider credential.

`docker/env/.env.app` and the database, Redis, and RabbitMQ environment files
are also private deployment inputs. Do not put them in an image, Git history,
or Angular build environment.

## First TLS bootstrap (DNS is already live)

`demo.hebaothman.dev` and `id.demo.hebaothman.dev` already resolve to the
demo host. Do not change DNS as part of this release. Start with
`DEMO_TLS_MODE=bootstrap`, bring up only the HTTP Nginx/dependencies, issue
the certificate with the `tls-bootstrap` profile, then set
`DEMO_TLS_MODE=tls` and restart Nginx. The certificate files are stored under:

```text
docker/nginx/certs/fullchain.pem
docker/nginx/certs/privkey.pem
```

Those paths are intentionally absent from the repository. The demo Nginx
configuration refuses to become a valid TLS deployment without them.

## OIDC requirements

Use one registrable domain with two HTTPS hostnames:

```text
https://demo.example.com
https://id.demo.example.com
```

The Keycloak provisioner creates a public OIDC client with Authorization Code
Flow and PKCE only. Its only callback is:

```text
https://demo.example.com/api/v1/auth/callback
```

It creates `demo.user` with only `demo_user`; it never assigns
`platform_admin`. The demo-user password and all Keycloak bootstrap/database
credentials are deployment secrets. Rotate the demo-user password after the
first successful provisioning if the account is handed to recruiters.

Nginx exposes the Keycloak OIDC realm endpoints on the IdP host but returns
`404` for `/admin` and `/admin/*`. Keycloak has no host-port mapping in the
demo stack, so its admin console and Admin REST API are not publicly reachable.
Perform any administrator actions from the host or private Docker network.

FastAPI must use `AUTH_MODE=bff_oidc`, `AUTH_ENABLED=true`,
`AUTHZ_ENABLED=true`, `AUTH_COOKIE_SECURE=true`, and
`AUTH_FRONTEND_SUCCESS_URL=https://demo.example.com/`. The OIDC issuer must be
the public Keycloak issuer. Session Redis must use a dedicated Redis database
or namespace, separate from Celery results.

Because Angular and `/api` share `demo.example.com`, browser calls are
same-origin and no production CORS origin is needed. If this topology changes,
configure only exact trusted origins in `CORS_ALLOWED_ORIGINS`.

## Demo guardrails

- Nginx rejects bodies larger than `DEMO_UPLOAD_MAX_BODY_SIZE` (default 5 MB).
- FastAPI enforces the configured file type and byte limit while streaming.
- The demo app accepts PDF and plain text only by default.
- `DEMO_MAX_PROJECTS_PER_PRINCIPAL` defaults to three.
- Nginx has per-IP limits for general API calls and a stricter agents limit.
- Keep `INPUT_DEFAULT_MAX_CHARACTERS` and
  `GENERATION_DEFAULT_MAX_TOKENS` conservative. Configure a provider-side
  monthly hard spend cap and alerts; a reverse-proxy rate limit alone cannot
  guarantee a monetary ceiling.

## Fresh database rehearsal

The migration chain was exercised against a new, disposable PostgreSQL 17
database. `alembic upgrade head` completed at revision `b7c3d9e1f2a4` and
created the private-thread tables. Always use a fresh demo database for the
first rollout; do not reuse an old production volume with a different Alembic
history.

## Proposed deployment sequence (not run)

1. DNS is already pointed at the demo host. Create private secret files and
   set `DEMO_TLS_MODE=bootstrap`.
2. Create private secret files/secret-store entries and verify no value is in
   Git.
3. Start private dependencies on an empty, persistent demo data set.
4. The dedicated `migration` container runs `alembic upgrade head` only
   against the fresh `mini-rag-demo_pgvector_data` volume.
5. Start Keycloak and the one-shot provisioner; verify `demo.user` has no
   `platform_admin` role.
6. `demo-provisioner` creates the fixed marker `public-demo-workspace:v1`,
   loads the release asset, processes/indexes it, and fails closed if it is not
   ready. FastAPI resolves that marker at runtime; no project ID is hand-edited.
7. Issue TLS, switch Nginx to TLS mode, then run the browser smoke test:
   Explore Demo, sources, clarification/resume, denied mutation, normal SSO,
   CSRF rejection, and BFF logout. BFF logout is sufficient for this release;
   the upstream Keycloak SSO session may remain until it naturally expires.
