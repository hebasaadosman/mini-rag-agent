from sqlalchemy import select

from .BaseDataModel import BaseDataModel
from .db_schemes import ProjectMembership


class ProjectMembershipModel(BaseDataModel):
    """Persistence adapter for project authorization memberships."""

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def get_role(self, *, project_id: int, principal_id: str) -> str | None:
        async with self.db_client() as session:
            result = await session.execute(
                select(ProjectMembership.role).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.principal_id == principal_id,
                )
            )
            return result.scalar_one_or_none()

    async def grant_role(
        self,
        *,
        project_id: int,
        principal_id: str,
        role: str,
    ) -> ProjectMembership:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    select(ProjectMembership).where(
                        ProjectMembership.project_id == project_id,
                        ProjectMembership.principal_id == principal_id,
                    )
                )
                membership = result.scalar_one_or_none()
                if membership is None:
                    membership = ProjectMembership(
                        project_id=project_id,
                        principal_id=principal_id,
                        role=role,
                    )
                    session.add(membership)
                else:
                    membership.role = role

            await session.refresh(membership)
            return membership
