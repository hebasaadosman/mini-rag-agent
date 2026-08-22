"""Endpoint-level checks for project authorization and membership revocation."""

from types import SimpleNamespace
import unittest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from authentication.principal import CurrentPrincipal
from authorization import ProjectAccess, ProjectAuthorizer, ProjectPermission
from authorization.dependencies import require_project_permission
import authorization.dependencies as authorization_dependencies
from helpers.config import get_settings
from routes.projects import projects_router


class _MembershipReader:
    def __init__(self, roles: dict[tuple[int, str], str]) -> None:
        self.roles = roles

    async def get_role(self, *, project_id: int, principal_id: str) -> str | None:
        return self.roles.get((project_id, principal_id))

    async def revoke_role(self, *, project_id: int, principal_id: str):
        role = self.roles.pop((project_id, principal_id), None)
        if role is None:
            return None
        return SimpleNamespace(principal_id=principal_id, role=role)

    async def list_members(self, *, project_id: int):
        return [
            SimpleNamespace(principal_id=principal_id, role=role)
            for (member_project_id, principal_id), role in self.roles.items()
            if member_project_id == project_id
        ]


class _AuditLogger:
    async def record(self, event) -> None:
        return None


class ProjectAuthorizationEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roles = {
            (1, "project-one-user"): "viewer",
            (2, "project-two-user"): "contributor",
            (3, "viewer"): "viewer",
            (3, "contributor"): "contributor",
            (4, "revoked-user"): "viewer",
            (4, "project-admin"): "admin",
        }
        self.current_subject = "project-one-user"
        self.app = FastAPI()
        self.memberships = _MembershipReader(self.roles)
        self.app.project_authorizer = ProjectAuthorizer(self.memberships)
        self.app.project_membership_model = self.memberships
        self.app.audit_logger = _AuditLogger()
        self.app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            AUTH_ENABLED=True,
            AUTHZ_ENABLED=True,
        )
        self._original_principal_dependency = authorization_dependencies.get_current_principal

        async def current_principal(*_args, **_kwargs) -> CurrentPrincipal:
            return CurrentPrincipal(subject=self.current_subject)

        authorization_dependencies.get_current_principal = current_principal
        self.app.include_router(projects_router)

        @self.app.get("/projects/{project_id}/read")
        async def read(
            _: ProjectAccess = Depends(
                require_project_permission(ProjectPermission.READ)
            ),
        ) -> dict[str, bool]:
            return {"ok": True}

        @self.app.post("/projects/{project_id}/write")
        async def write(
            _: ProjectAccess = Depends(
                require_project_permission(ProjectPermission.WRITE)
            ),
        ) -> dict[str, bool]:
            return {"ok": True}

        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        authorization_dependencies.get_current_principal = self._original_principal_dependency

    def test_cross_project_access_is_denied(self) -> None:
        response = self.client.get("/projects/2/read")
        self.assertEqual(response.status_code, 403)

    def test_viewer_is_read_only_and_contributor_can_write(self) -> None:
        self.current_subject = "viewer"
        self.assertEqual(self.client.get("/projects/3/read").status_code, 200)
        self.assertEqual(self.client.post("/projects/3/write").status_code, 403)

        self.current_subject = "contributor"
        self.assertEqual(self.client.post("/projects/3/write").status_code, 200)

    def test_membership_revocation_denies_the_next_request(self) -> None:
        self.current_subject = "project-admin"
        self.assertEqual(
            self.client.delete(
                "/api/v1/projects/4/members/revoked-user"
            ).status_code,
            204,
        )
        self.current_subject = "revoked-user"
        self.assertEqual(self.client.get("/projects/4/read").status_code, 403)


if __name__ == "__main__":
    unittest.main()
