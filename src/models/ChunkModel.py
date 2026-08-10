from sqlalchemy.future import select

from .BaseDataModel import BaseDataModel
from .db_schemes import DataChunk
from .enums.DatabaseEnum import DatabaseEnum
from sqlalchemy import func

from sqlalchemy import delete

class ChunkModel(BaseDataModel):

    def __init__(self, db_client):
        super().__init__(db_client)
        self.collection = self.db_client

    @classmethod
    async def create_instance(cls, db_client:object):
        instance = cls(db_client)
        return instance
    
   
    async def create_chunk(self, chunk: DataChunk):
       async with self.db_client() as session:
            async with session.begin():
              session.add(chunk)
            await session.commit()
            await session.refresh(chunk)
            return chunk
       
    async def insert_many_chunks(self, chunks: list,batch_size: int = 100):

       async with self.db_client() as session:
            async with session.begin():
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i + batch_size]
                    session.add_all(batch)
                await session.commit()
                return len(chunks)
    
    async def get_chunk_by_id(self, chunk_id: str):
      async with self.db_client() as session:
          async with session.begin():
              chunk = await session.get(DataChunk, chunk_id)
              return chunk
          

    async def update_chunk(self, chunk_id: str, updated_data: dict):
        async with self.db_client() as session:
            async with session.begin():
                chunk = await session.get(DataChunk, chunk_id)
                if chunk:
                    for key, value in updated_data.items():
                        setattr(chunk, key, value)
                    await session.commit()
                    return True
                return False
            
    async def delete_chunk(self, chunk_id: str):
        async with self.db_client() as session:
            async with session.begin():
                chunk = await session.get(DataChunk, chunk_id)
                if chunk:
                    await session.delete(chunk)
                    await session.commit()
                    return True
                return False
    
    async def delete_chunks_by_project_id(self, project_id: str):
        async with self.db_client() as session:
            async with session.begin():
                query = select(DataChunk).where(DataChunk.chunk_project_id == project_id)
                result = await session.execute(query)
                chunks = result.scalars().all()
                for chunk in chunks:
                    await session.delete(chunk)
                await session.commit()
                return len(chunks)
    
    async def get_chunks_by_project_id(self, project_id: int,page_number: int = 1, page_size: int = 50):
        async with self.db_client() as session:
            async with session.begin():
                total_pages= (await session.execute(select(func.count(DataChunk.chunk_id)).where(DataChunk.chunk_project_id == project_id))).scalar_one()
                total_pages = (total_pages + page_size - 1) // page_size    
                query = select(DataChunk).where(DataChunk.chunk_project_id == project_id).offset((page_number - 1) * page_size).limit(page_size)
                result = await session.execute(query)
                chunks = result.scalars().all()

                return chunks,page_number,page_size
    async def get_total_chunks_count_by_project_id(self, project_id: int):
        total_count=0
        async with self.db_client() as session:
            async with session.begin():
                total_count = await session.execute(select(func.count(DataChunk.chunk_id)).where(DataChunk.chunk_project_id == project_id))
                total_count = total_count.scalar_one()
        return total_count
    

    async def replace_asset_chunks(
        self,
        *,
        project_id: int,
        asset_id: int,
        chunk_records: list[DataChunk],
    ) -> int:
        """
        Atomically replaces all chunks belonging to one asset.

        If anything fails, both the deletion and insertion
        are rolled back.
        """

        async with self.db_client() as session:
            async with session.begin():
                delete_statement = delete(
                    DataChunk
                ).where(
                    DataChunk.chunk_project_id == project_id,
                    DataChunk.chunk_asset_id == asset_id,
                )

                await session.execute(
                    delete_statement
                )

                session.add_all(
                    chunk_records
                )

            return len(chunk_records)

  


    async def get_asset_content(
        self,
        *,
        project_id: int,
        asset_id: int,
    ) -> list[DataChunk]:
        """
        Retrieve all chunks for one asset inside one project,
        ordered exactly as they were created.
        """

        async with self.db_client() as session:
            query = (
                select(DataChunk)
                .where(
                    DataChunk.chunk_project_id
                    == project_id,
                    DataChunk.chunk_asset_id
                    == asset_id,
                )
                .order_by(
                    DataChunk.chunk_order.asc()
                )
            )

            result = await session.execute(query)

            return list(
                result.scalars().all()
            )