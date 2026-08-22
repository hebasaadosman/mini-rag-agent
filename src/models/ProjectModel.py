from .BaseDataModel import BaseDataModel
from .db_schemes import Project, ProjectMembership
from .enums.DatabaseEnum import DatabaseEnum
from sqlalchemy.future import select
from sqlalchemy import func


class ProjectModel(BaseDataModel):
    def __init__(self, db_client):
        super().__init__(db_client)
        self.collection = self.db_client
        
    @classmethod
    async def create_instance(cls, db_client:object):
        instance = cls(db_client)
        return instance
    
  
    async def create_project(self, project: Project):
        async with self.db_client() as session:
            async with session.begin():
               session.add(project)

            await session.commit()
            await session.refresh(project)

       
        return project

    async def create_project_with_creator_admin(
        self,
        *,
        description: str | None,
        creator_principal_id: str,
    ) -> Project:
        """Provision the project and its first admin as one transaction."""
        project = Project(project_description=description)
        async with self.db_client() as session:
            async with session.begin():
                session.add(project)
                await session.flush()
                session.add(
                    ProjectMembership(
                        project_id=project.project_id,
                        principal_id=creator_principal_id,
                        role="admin",
                    )
                )
            await session.refresh(project)
        return project

    async def get_project_or_create_one(self, project_id: int):
      async with self.db_client() as session:
          async with session.begin():
              query = select(Project).where(Project.project_id == project_id)
              result = await session.execute(query)
              project = result.scalar_one_or_none()
              if not project:
                  project = Project(project_id=project_id)
                  await self.create_project(project)
                  return project
              return project
          
    async def update_project(self, project_id: int, updated_data: dict):
        async with self.db_client() as session:
            async with session.begin():
                query = select(Project).where(Project.project_id == project_id)
                result = await session.execute(query)
                project = result.scalar_one_or_none()
                if project:
                    for key, value in updated_data.items():
                        setattr(project, key, value)
                    await session.commit()
                    return True
                return False

    async def delete_project(self, project_id: int):
        async with self.db_client() as session:
            async with session.begin():
                query = select(Project).where(Project.project_id == project_id)
                result = await session.execute(query)
                project = result.scalar_one_or_none()
                if project:
                    await session.delete(project)
                    await session.commit()
                    return True
                return False

    async def get_all_projects(self,page: int = 1, page_size: int = 10):
        async with self.db_client() as session:
            async with session.begin():
                count_query = select(func.count()).select_from(Project)
                count_result = await session.execute(count_query)
                total_projects = count_result.scalar_one()
                total_pages = (total_projects + page_size - 1) // page_size
                if total_pages == 0:
                    total_pages = 1
                query = select(Project).offset((page - 1) * page_size).limit(page_size)
                result = await session.execute(query)
                projects = result.scalars().all()
                return projects, total_pages
            
    async def get_project_by_id(self, project_id: int)-> Project | None:
        async with self.db_client() as session:
            query = select(Project).where(
                Project.project_id == project_id
            )

            result = await session.execute(query)
            return result.scalar_one_or_none()
