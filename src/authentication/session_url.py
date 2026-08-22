"""Resolve the Redis location used for BFF sessions without duplicating secrets."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from helpers.config import Settings


def resolve_auth_session_redis_url(settings: Settings) -> str:
    """Return the explicit session URL or a local-only Celery Redis sibling.

    Production configuration must remain explicit.  Local Docker development
    already provides the Redis credential via ``CELERY_RESULT_BACKEND``; using
    database 1 avoids copying that credential into a second ignored file.
    """
    explicit_url = str(settings.AUTH_SESSION_REDIS_URL or "").strip()
    if explicit_url:
        return explicit_url

    if settings.APP_ENV.strip().lower() not in {"development", "dev", "local", "test"}:
        raise RuntimeError("AUTH_SESSION_REDIS_URL is required for bff_oidc authentication.")

    result_backend = str(settings.CELERY_RESULT_BACKEND or "").strip()
    parsed = urlsplit(result_backend)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise RuntimeError(
            "AUTH_SESSION_REDIS_URL is required unless CELERY_RESULT_BACKEND is a Redis URL in local development."
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "/1", parsed.query, parsed.fragment))
