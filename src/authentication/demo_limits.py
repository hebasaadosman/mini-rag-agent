"""Small server-side fixed-window quota for public demo agent requests."""

from __future__ import annotations

import time


class DemoRateLimitExceeded(PermissionError):
    """The public demo request budget for this window is exhausted."""


class DemoAgentRateLimiter:
    """Use Redis so every API replica enforces the same demo budget."""

    _PREFIX = "mini-rag:demo:agent-rate:"

    def __init__(
        self,
        redis_client,
        *,
        limit: int,
        window_seconds: int = 60,
        key_prefix: str = _PREFIX,
    ) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("demo rate-limit values must be positive.")
        if not key_prefix:
            raise ValueError("demo rate-limit key prefix is required.")
        self._redis = redis_client
        self._limit = limit
        self._window_seconds = window_seconds
        self._key_prefix = key_prefix

    async def require_capacity(self, principal_id: str) -> None:
        now = int(time.time())
        bucket = now // self._window_seconds
        key = f"{self._key_prefix}{bucket}:{principal_id}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, self._window_seconds + 1)
        if count > self._limit:
            raise DemoRateLimitExceeded("Demo agent rate limit exceeded.")
