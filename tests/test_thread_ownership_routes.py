"""Private-thread authorization at the public Multi-Agent boundary."""

from contextlib import asynccontextmanager
import asyncio
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication.principal import CurrentPrincipal
from authorization import ProjectAuthorizer
from helpers.config import get_settings
from models.ConversationThreadModel import ConversationThreadAccessDenied
from routes.agents import agents_router
import authorization.dependencies as authorization_dependencies


class _Memberships:
    def __init__(self, roles):
        self.roles = roles

    async def get_role(self, *, project_id, principal_id):
        return self.roles.get((project_id, principal_id))


class _Threads:
    def __init__(self, memberships):
        self.memberships = memberships
        self.rows = {}

    async def claim_or_require_owner(self, *, project_id, thread_id, principal_id):
        if await self.memberships.get_role(
            project_id=project_id, principal_id=principal_id
        ) is None:
            raise ConversationThreadAccessDenied()
        key = (project_id, thread_id.strip())
        row = self.rows.setdefault(
            key,
            SimpleNamespace(
                project_id=project_id,
                thread_id=thread_id.strip(),
                owner_principal_id=principal_id,
                checkpoint_key=f"checkpoint-{project_id}-{thread_id.strip()}",
            ),
        )
        if row.owner_principal_id != principal_id:
            raise ConversationThreadAccessDenied()
        return row

    async def require_owner(self, *, project_id, thread_id, principal_id):
        if await self.memberships.get_role(
            project_id=project_id, principal_id=principal_id
        ) is None:
            raise ConversationThreadAccessDenied()
        row = self.rows.get((project_id, thread_id.strip()))
        if row is None or row.owner_principal_id != principal_id:
            raise ConversationThreadAccessDenied()
        return row


class _Locks:
    @asynccontextmanager
    async def acquire(self, _key):
        yield


class _Controller:
    async def chat(self, **kwargs):
        return {
            "success": True,
            "status": "completed",
            "project_id": kwargs["project_id"],
            "thread_id": kwargs["thread_id"],
            "agent": "general",
            "answer": "ok",
            "sources": [],
        }

    async def resume(self, **kwargs):
        return await self.chat(**kwargs)


class ThreadOwnershipRouteTests(unittest.TestCase):
    def setUp(self):
        self.roles = {
            (1, "owner"): "viewer",
            (1, "other-member"): "viewer",
            (2, "owner"): "viewer",
        }
        self.memberships = _Memberships(self.roles)
        self.subject = "owner"
        self.roles_claim = ()
        app = FastAPI()
        app.project_authorizer = ProjectAuthorizer(self.memberships)
        app.conversation_thread_model = _Threads(self.memberships)
        app.agent_thread_locks = _Locks()
        app.multi_agent_controller = _Controller()
        app.audit_logger = SimpleNamespace(record=self._record)
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            AUTH_ENABLED=True, AUTHZ_ENABLED=True
        )
        self.original_principal = authorization_dependencies.get_current_principal

        async def principal(*_args, **_kwargs):
            return CurrentPrincipal(self.subject, self.roles_claim)

        authorization_dependencies.get_current_principal = principal
        app.include_router(agents_router)
        self.client = TestClient(app)

    async def _record(self, _event):
        return None

    def tearDown(self):
        authorization_dependencies.get_current_principal = self.original_principal

    def _chat(self, project_id=1, thread_id="private-1"):
        return self.client.post(
            f"/api/v1/agents/{project_id}/chat",
            json={"message": "hello", "thread_id": thread_id},
        )

    def _resume(self, project_id=1, thread_id="private-1"):
        return self.client.post(
            f"/api/v1/agents/{project_id}/chat/resume",
            json={"response": "continue", "thread_id": thread_id},
        )

    def test_same_project_member_cannot_read_or_resume_another_private_thread(self):
        self.assertEqual(self._chat().status_code, 200)
        self.subject = "other-member"
        self.assertEqual(self._chat().status_code, 403)
        self.assertEqual(self._resume().status_code, 403)

    def test_revocation_immediately_blocks_the_thread_owner(self):
        self.assertEqual(self._chat().status_code, 200)
        self.roles.pop((1, "owner"))
        self.assertEqual(self._chat().status_code, 403)
        self.assertEqual(self._resume().status_code, 403)

    def test_same_public_thread_id_in_another_project_is_not_a_resume_target(self):
        self.assertEqual(self._chat(project_id=1, thread_id="same-id").status_code, 200)
        self.assertEqual(self._resume(project_id=2, thread_id="same-id").status_code, 403)

    def test_platform_admin_has_no_implicit_private_thread_access(self):
        self.assertEqual(self._chat().status_code, 200)
        self.subject = "platform-operator"
        self.roles_claim = ("platform_admin",)
        self.assertEqual(self._resume().status_code, 403)

    def test_legacy_checkpoint_without_an_ownership_row_cannot_resume(self):
        self.assertEqual(self._resume(thread_id="legacy-thread").status_code, 403)


class ThreadOwnershipConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_competing_claims_leave_one_private_owner(self):
        memberships = _Memberships(
            {(1, "first"): "viewer", (1, "second"): "viewer"}
        )
        threads = _Threads(memberships)

        results = await asyncio.gather(
            threads.claim_or_require_owner(
                project_id=1, thread_id="race-thread", principal_id="first"
            ),
            threads.claim_or_require_owner(
                project_id=1, thread_id="race-thread", principal_id="second"
            ),
            return_exceptions=True,
        )

        self.assertEqual(
            sum(not isinstance(result, Exception) for result in results), 1
        )
        self.assertEqual(
            sum(
                isinstance(result, ConversationThreadAccessDenied)
                for result in results
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
