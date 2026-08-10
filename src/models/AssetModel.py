from sqlalchemy import select
from sqlalchemy import update as sqlalchemy_update

from .BaseDataModel import BaseDataModel
from .db_schemes import Asset


class AssetModel(BaseDataModel):
    def __init__(self, db_client):
        super().__init__(db_client)
        self.collection = self.db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def create_asset(
        self,
        asset: Asset,
    ) -> Asset:
        async with self.db_client() as session:
            session.add(asset)

            await session.commit()
            await session.refresh(asset)

            return asset
    async def get_all_projects_assets(
        self,
        asset_project_id: int,
        asset_type: str | None = None,
    ) -> list[Asset]:
        async with self.db_client() as session:
            query = (
                select(Asset)
                .where(
                    Asset.asset_project_id
                    == asset_project_id
                )
                .order_by(Asset.asset_id.asc())
            )

            if asset_type is not None:
                query = query.where(
                    Asset.asset_type == asset_type
                )

            result = await session.execute(query)

            return list(result.scalars().all())
    async def get_asset_by_id(
        self,
        asset_project_id: int,
        asset_id: int,
    ) -> Asset | None:
        async with self.db_client() as session:
            query = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_id == asset_id,
            )

            result = await session.execute(query)

            return result.scalar_one_or_none()

    async def update_checksum(
        self,
        asset_id: int,
        checksum: str,
    ) -> Asset | None:
        statement = (
            sqlalchemy_update(Asset)
            .where(
                Asset.asset_id == asset_id
            )
            .values(
                asset_checksum=checksum
            )
            .returning(Asset)
        )

        async with self.db_client() as session:
            result = await session.execute(statement)
            asset = result.scalar_one_or_none()

            await session.commit()

            return asset