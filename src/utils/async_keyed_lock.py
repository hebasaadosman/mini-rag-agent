import asyncio
import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass
class _LockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class AsyncKeyedLock:
    """Serialize work per key while allowing different keys in parallel."""

    def __init__(self) -> None:
        self._entries: dict[str, _LockEntry] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        async with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                entry = _LockEntry()
                self._entries[key] = entry
            entry.users += 1

        await entry.lock.acquire()
        try:
            yield
        finally:
            entry.lock.release()
            async with self._guard:
                entry.users -= 1
                if entry.users == 0:
                    self._entries.pop(key, None)


class PostgresAdvisoryKeyedLock:
    """Serialize a key across all API workers using PostgreSQL."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._local = AsyncKeyedLock()

    @staticmethod
    def lock_id(key: str) -> int:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        advisory_lock_id = self.lock_id(key)

        async with self._local.acquire(key):
            async with self._engine.connect() as connection:
                await connection.execute(
                    text("SELECT pg_advisory_lock(:lock_id)"),
                    {"lock_id": advisory_lock_id},
                )
                try:
                    yield
                finally:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": advisory_lock_id},
                    )
