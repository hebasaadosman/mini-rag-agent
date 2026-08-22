"""Real PostgreSQL concurrency coverage for private thread claiming.

Set THREAD_OWNERSHIP_TEST_DATABASE_URL to an isolated, migrated PostgreSQL
database to run this test module. It intentionally skips in unit-test-only CI.
"""

import asyncio
import os
import unittest
from unittest.mock import patch

from sqlalchemy import delete
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from models.ConversationThreadModel import (
    ConversationThreadAccessDenied,
    ConversationThreadModel,
)
from models.db_schemes import ConversationThread, Project, ProjectMembership


DATABASE_URL = os.getenv("THREAD_OWNERSHIP_TEST_DATABASE_URL", "").strip()
if not DATABASE_URL and os.getenv("RUN_POSTGRES_THREAD_OWNERSHIP_TESTS") == "1":
    # This opt-in is for the project's local Docker stack.  CI must provide an
    # explicit isolated URL rather than inheriting application configuration.
    from helpers.config import get_settings

    settings = get_settings()
    DATABASE_URL = URL.create(
        "postgresql+asyncpg",
        username=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
    )


@unittest.skipUnless(
    DATABASE_URL,
    "requires THREAD_OWNERSHIP_TEST_DATABASE_URL and migrated PostgreSQL",
)
class ConversationThreadPostgresConcurrencyTests(
    unittest.IsolatedAsyncioTestCase
):
    async def asyncSetUp(self):
        self.engine = create_async_engine(DATABASE_URL)
        self.sessions = async_sessionmaker(
            self.engine, expire_on_commit=False
        )
        async with self.sessions() as session:
            async with session.begin():
                project = Project(project_description="thread ownership test")
                session.add(project)
                await session.flush()
                self.project_id = project.project_id
                session.add_all(
                    [
                        ProjectMembership(
                            project_id=self.project_id,
                            principal_id="concurrency-owner-a",
                            role="viewer",
                        ),
                        ProjectMembership(
                            project_id=self.project_id,
                            principal_id="concurrency-owner-b",
                            role="viewer",
                        ),
                    ]
                )

    async def asyncTearDown(self):
        async with self.sessions() as session:
            async with session.begin():
                await session.execute(
                    delete(ConversationThread).where(
                        ConversationThread.project_id == self.project_id
                    )
                )
                await session.execute(
                    delete(ProjectMembership).where(
                        ProjectMembership.project_id == self.project_id
                    )
                )
                await session.execute(
                    delete(Project).where(Project.project_id == self.project_id)
                )
        await self.engine.dispose()

    async def _competing_claims(self, first_principal, second_principal):
        barrier = asyncio.Barrier(2)
        entry_lock = asyncio.Lock()
        entry_count = 0
        original = ConversationThreadModel._require_current_membership

        async def synchronize_before_claim(*, session, project_id, principal_id):
            nonlocal entry_count
            await original(
                session=session,
                project_id=project_id,
                principal_id=principal_id,
            )
            async with entry_lock:
                entry_count += 1
                synchronize = entry_count <= 2
            if synchronize:
                await barrier.wait()

        first = ConversationThreadModel(self.sessions)
        second = ConversationThreadModel(self.sessions)
        with patch.object(
            ConversationThreadModel,
            "_require_current_membership",
            staticmethod(synchronize_before_claim),
        ):
            return await asyncio.gather(
                first.claim_or_require_owner(
                    project_id=self.project_id,
                    thread_id="postgres-race-thread",
                    principal_id=first_principal,
                ),
                second.claim_or_require_owner(
                    project_id=self.project_id,
                    thread_id="postgres-race-thread",
                    principal_id=second_principal,
                ),
                return_exceptions=True,
            )

    async def test_same_owner_race_is_idempotent(self):
        results = await self._competing_claims(
            "concurrency-owner-a", "concurrency-owner-a"
        )

        self.assertTrue(
            all(not isinstance(result, Exception) for result in results),
            repr(results),
        )
        self.assertEqual(results[0].owner_principal_id, "concurrency-owner-a")
        self.assertEqual(results[0].checkpoint_key, results[1].checkpoint_key)

    async def test_competing_owner_race_leaves_one_private_owner(self):
        results = await self._competing_claims(
            "concurrency-owner-a", "concurrency-owner-b"
        )

        self.assertEqual(
            sum(not isinstance(item, Exception) for item in results),
            1,
            repr(results),
        )
        self.assertEqual(
            sum(
                isinstance(item, ConversationThreadAccessDenied)
                for item in results
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
