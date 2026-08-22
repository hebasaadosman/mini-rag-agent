"""Server-side browser sessions and short-lived OIDC login transactions."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class BrowserSession:
    session_id: str
    subject: str
    roles: tuple[str, ...]
    csrf_token: str
    created_at: int
    expires_at: int
    absolute_expires_at: int


@dataclass(frozen=True, slots=True)
class OIDCLoginTransaction:
    state: str
    nonce: str
    code_verifier: str
    expires_at: int


class SessionStore(Protocol):
    async def create_session(self, *, subject: str, roles: tuple[str, ...]) -> BrowserSession: ...
    async def get_session(self, session_id: str) -> BrowserSession | None: ...
    async def delete_session(self, session_id: str) -> None: ...
    async def create_transaction(self) -> OIDCLoginTransaction: ...
    async def get_transaction(self, state: str) -> OIDCLoginTransaction | None: ...
    async def delete_transaction(self, state: str) -> None: ...


class InMemorySessionStore:
    """Deterministic store for tests; production uses :class:`RedisSessionStore`."""

    def __init__(
        self,
        *,
        idle_timeout_seconds: int = 1800,
        absolute_timeout_seconds: int = 28800,
        transaction_ttl_seconds: int = 600,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._idle_timeout = idle_timeout_seconds
        self._absolute_timeout = absolute_timeout_seconds
        self._transaction_ttl = transaction_ttl_seconds
        self._clock = clock or (lambda: int(time.time()))
        self._sessions: dict[str, BrowserSession] = {}
        self._transactions: dict[str, OIDCLoginTransaction] = {}

    async def create_session(self, *, subject: str, roles: tuple[str, ...]) -> BrowserSession:
        now = self._clock()
        session = BrowserSession(
            session_id=secrets.token_urlsafe(32),
            subject=subject,
            roles=roles,
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + self._idle_timeout,
            absolute_expires_at=now + self._absolute_timeout,
        )
        self._sessions[session.session_id] = session
        return session

    async def get_session(self, session_id: str) -> BrowserSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        now = self._clock()
        if now >= session.expires_at or now >= session.absolute_expires_at:
            self._sessions.pop(session_id, None)
            return None
        refreshed = BrowserSession(
            **{
                **asdict(session),
                "expires_at": min(now + self._idle_timeout, session.absolute_expires_at),
            }
        )
        self._sessions[session_id] = refreshed
        return refreshed

    async def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def create_transaction(self) -> OIDCLoginTransaction:
        now = self._clock()
        transaction = OIDCLoginTransaction(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
            expires_at=now + self._transaction_ttl,
        )
        self._transactions[transaction.state] = transaction
        return transaction

    async def get_transaction(self, state: str) -> OIDCLoginTransaction | None:
        transaction = self._transactions.get(state)
        if transaction is None or self._clock() >= transaction.expires_at:
            self._transactions.pop(state, None)
            return None
        return transaction

    async def delete_transaction(self, state: str) -> None:
        self._transactions.pop(state, None)


class RedisSessionStore(InMemorySessionStore):
    """Redis-backed session store with TTL enforced by Redis and application code."""

    _SESSION_PREFIX = "mini-rag:auth:session:"
    _TRANSACTION_PREFIX = "mini-rag:auth:oidc-transaction:"

    def __init__(self, redis_client, **kwargs) -> None:
        super().__init__(**kwargs)
        self._redis = redis_client

    async def create_session(self, *, subject: str, roles: tuple[str, ...]) -> BrowserSession:
        session = await super().create_session(subject=subject, roles=roles)
        await self._save_session(session)
        return session

    async def get_session(self, session_id: str) -> BrowserSession | None:
        raw = await self._redis.get(f"{self._SESSION_PREFIX}{session_id}")
        if raw is None:
            return None
        payload = json.loads(raw)
        payload["roles"] = tuple(payload["roles"])
        session = BrowserSession(**payload)
        now = self._clock()
        if now >= session.expires_at or now >= session.absolute_expires_at:
            await self.delete_session(session_id)
            return None
        refreshed = BrowserSession(
            **{
                **asdict(session),
                "roles": tuple(session.roles),
                "expires_at": min(now + self._idle_timeout, session.absolute_expires_at),
            }
        )
        await self._save_session(refreshed)
        return refreshed

    async def delete_session(self, session_id: str) -> None:
        await self._redis.delete(f"{self._SESSION_PREFIX}{session_id}")

    async def create_transaction(self) -> OIDCLoginTransaction:
        transaction = await super().create_transaction()
        await self._redis.setex(
            f"{self._TRANSACTION_PREFIX}{transaction.state}",
            self._transaction_ttl,
            json.dumps(asdict(transaction)),
        )
        return transaction

    async def get_transaction(self, state: str) -> OIDCLoginTransaction | None:
        raw = await self._redis.get(f"{self._TRANSACTION_PREFIX}{state}")
        if raw is None:
            return None
        transaction = OIDCLoginTransaction(**json.loads(raw))
        if self._clock() >= transaction.expires_at:
            await self.delete_transaction(state)
            return None
        return transaction

    async def delete_transaction(self, state: str) -> None:
        await self._redis.delete(f"{self._TRANSACTION_PREFIX}{state}")

    async def _save_session(self, session: BrowserSession) -> None:
        ttl = max(1, session.absolute_expires_at - self._clock())
        payload = asdict(session)
        payload["roles"] = list(session.roles)
        await self._redis.setex(
            f"{self._SESSION_PREFIX}{session.session_id}", ttl, json.dumps(payload)
        )
