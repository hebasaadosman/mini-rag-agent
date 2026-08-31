import unittest

from authentication.principal import CurrentPrincipal
from authorization.project_access import (
    ProjectAccessDenied,
    ProjectAuthorizer,
    ProjectPermission,
    ProjectRole,
)


class _MembershipReader:
    def __init__(self, roles):
        self.roles = roles

    async def get_role(self, *, project_id, principal_id):
        return self.roles.get((project_id, principal_id))


class ProjectAuthorizerTests(unittest.IsolatedAsyncioTestCase):
    async def test_viewer_can_read_but_cannot_write(self):
        authorizer = ProjectAuthorizer(_MembershipReader({(7, "heba"): "viewer"}))
        principal = CurrentPrincipal(subject="heba")

        access = await authorizer.require_permission(
            principal=principal,
            project_id=7,
            permission=ProjectPermission.READ,
        )
        self.assertEqual(access.role, ProjectRole.VIEWER)

        with self.assertRaises(ProjectAccessDenied):
            await authorizer.require_permission(
                principal=principal,
                project_id=7,
                permission=ProjectPermission.WRITE,
            )

    async def test_contributor_can_write(self):
        authorizer = ProjectAuthorizer(
            _MembershipReader({(7, "heba"): "contributor"})
        )

        access = await authorizer.require_permission(
            principal=CurrentPrincipal(subject="heba"),
            project_id=7,
            permission=ProjectPermission.WRITE,
        )
        self.assertEqual(access.role, ProjectRole.CONTRIBUTOR)

    async def test_missing_membership_is_denied(self):
        authorizer = ProjectAuthorizer(_MembershipReader({}))

        with self.assertRaises(ProjectAccessDenied):
            await authorizer.require_permission(
                principal=CurrentPrincipal(subject="heba"),
                project_id=7,
                permission=ProjectPermission.READ,
            )

    async def test_platform_admin_is_allowed_without_membership(self):
        authorizer = ProjectAuthorizer(_MembershipReader({}))

        access = await authorizer.require_permission(
            principal=CurrentPrincipal(subject="operator", roles=("platform_admin",)),
            project_id=7,
            permission=ProjectPermission.MANAGE,
        )
        self.assertEqual(access.role, ProjectRole.ADMIN)

    async def test_demo_principal_is_read_only_and_scoped_to_its_workspace(self):
        authorizer = ProjectAuthorizer(_MembershipReader({(7, "demo-1"): "viewer"}))
        principal = CurrentPrincipal(
            subject="demo-1", kind="demo", demo_project_id=7
        )
        access = await authorizer.require_permission(
            principal=principal, project_id=7, permission=ProjectPermission.READ
        )
        self.assertEqual(access.role, ProjectRole.VIEWER)
        with self.assertRaises(ProjectAccessDenied):
            await authorizer.require_permission(
                principal=principal, project_id=7, permission=ProjectPermission.WRITE
            )
        with self.assertRaises(ProjectAccessDenied):
            await authorizer.require_permission(
                principal=principal, project_id=8, permission=ProjectPermission.READ
            )


if __name__ == "__main__":
    unittest.main()
