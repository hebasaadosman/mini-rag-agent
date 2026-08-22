"""Safe request correlation metadata shared with asynchronous work."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request


_MAX_CORRELATION_ID_LENGTH = 128


def request_correlation_id(request: Request | None) -> str:
    """Use a bounded client correlation identifier or create a server one."""
    if request is None:
        return str(uuid4())
    value = request.headers.get("X-Request-ID", "").strip()
    if value and len(value) <= _MAX_CORRELATION_ID_LENGTH:
        return value
    return str(uuid4())


def background_request_metadata(*, route: str) -> dict[str, str]:
    """Allowlist only stable operational context, never request content."""
    return {"source": "api", "route": route}
