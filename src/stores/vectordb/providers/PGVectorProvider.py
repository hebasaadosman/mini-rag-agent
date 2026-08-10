from uuid import uuid4

from ..VectorDBInterface import VectorDBInterface
import logging
from ..VectorDBEnum import DistanceMetricEnum, PgVectorTablesSchemaEnums, PgVectorDistanceMetricEnum, PgVectorIndexTypeEnum
from models.db_schemes import RetrieveDocument
import logging
from typing import List
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
import json
import re

class PGVectorDBProvider(VectorDBInterface):
    def __init__(self,db_client,db_path, default_vector_size: int,  distance_metric_method: str = "cosine",index_threshold: int = 100):
        self.client = db_client
        self.default_vector_size = default_vector_size
        self.distance_metric_method = distance_metric_method
        self.distance_metric = None
        if distance_metric_method == DistanceMetricEnum.COSINE.value:
            self.distance_metric = "cosine"
        elif distance_metric_method == DistanceMetricEnum.DOT.value:
            self.distance_metric = "dot"
        elif distance_metric_method == DistanceMetricEnum.EUCLIDEAN.value:
            self.distance_metric = "euclidean"
        else:
            self.distance_metric = distance_metric_method
        self.pgvector_table_prefix = PgVectorTablesSchemaEnums.PGVECTOR_TABLE_PREFIX.value
        self.logger = logging.getLogger("uvicorn")
        self.default_index_name = lambda collection_name: f"{collection_name}_vector_idx"
        self.index_threshold = index_threshold
        self.db_path = db_path
    @staticmethod
    def _validate_identifier(name: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid SQL identifier: {name}")
        return name
    async def connect(self):
        async with self.client() as session:
            async with session.begin():
                # Create the pgvector extension if it doesn't exist
                await session.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await session.commit()

    async def disconnect(self):
        # No specific disconnect logic needed for SQLAlchemy session
        pass

    async def is_collection_exists(
    self,
    collection_name: str,
    ) -> bool:
        async with self.client() as session:
            async with session.begin():
                result = await session.execute(
                    sql_text("""
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                            AND table_name = :collection_name
                        )
                    """),
                    {"collection_name": collection_name},
                )
        

        return bool(result.scalar())


    async def list_all_collections(self):
        collections = []
        async with self.client() as session:
            async with session.begin():
                result = await session.execute(
                    sql_text("SELECT tablename FROM pg_tables WHERE tablename LIKE :prefix"),
                    {"prefix": f"{self.pgvector_table_prefix}_%"}
                )
                collections =await result.scalars().all()

        return collections
     
    async  def get_collection_info(self, collection_name):
        collection_info = {}
        async with self.client() as session:
            async with session.begin():
                result = await session.execute(
                    sql_text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = :table_name"),
                    {"table_name": collection_name}
                )
                count_result = await session.execute(
                    sql_text(f"SELECT COUNT(*) FROM {collection_name}"),
                    {}
                )
                columns_info =  result.fetchall()
                collection_info["columns"] = [{"name": col[0], "type": col[1]} for col in columns_info]
                table_data =  count_result.fetchone()
            if table_data:
                collection_info["row_count"] = table_data[0]
            collection_info["row_count"] = table_data[0] if table_data else 0
        return {
            "collection_name": collection_name,
            "columns": collection_info.get("columns", []),
            "row_count": collection_info.get("row_count", 0)
        }
    
    async def delete_collection(self, collection_name):
        async with self.client() as session:
            self.logger.info(f"Deleting collection '{collection_name}' from the database.")
            async with session.begin():
                await session.execute(sql_text(f"DROP TABLE IF EXISTS {collection_name}"))
            await session.commit()

        return {"message": f"Collection '{collection_name}' deleted successfully."}
    


    async def create_collection(
        self,
        collection_name: str,
        vector_size: int | None = None,
        distance_metric_method: str = "cosine",
        do_reset: bool = False,  # ممكن تسيبيه مؤقتًا للتوافق مع الـ interface
    ):
        vector_size = vector_size or self.default_vector_size
        distance_metric_method = (
            distance_metric_method or self.distance_metric_method
        )

        if distance_metric_method not in [
            metric.value for metric in DistanceMetricEnum
        ]:
            raise ValueError(
                f"Invalid distance metric method: {distance_metric_method}"
            )

        pgvector_operator_class = (
            PgVectorDistanceMetricEnum[
                distance_metric_method.upper()
            ].value
        )

        async with self.client() as session:
            async with session.begin():

                await session.execute(
                    sql_text(
                        f"DROP TABLE IF EXISTS {collection_name} CASCADE"
                    )
                )

                await session.execute(sql_text(f"""
                    CREATE TABLE {collection_name} (
                        {PgVectorTablesSchemaEnums.ID.value}
                            SERIAL PRIMARY KEY,

                        {PgVectorTablesSchemaEnums.VECTOR.value}
                            VECTOR({vector_size}),

                        {PgVectorTablesSchemaEnums.TEXT.value}
                            TEXT,

                        {PgVectorTablesSchemaEnums.CHUNK_ID.value}
                            INTEGER,

                        {PgVectorTablesSchemaEnums.METADATA.value}
                            JSONB DEFAULT '{{}}'::jsonb,

                        FOREIGN KEY (
                            {PgVectorTablesSchemaEnums.CHUNK_ID.value}
                        )
                        REFERENCES chunks(chunk_id)
                        ON DELETE CASCADE
                    )
                """))

                await session.execute(sql_text(f"""
                    CREATE INDEX {collection_name}_vector_idx
                    ON {collection_name}
                    USING hnsw (
                        {PgVectorTablesSchemaEnums.VECTOR.value}
                        {pgvector_operator_class}
                    )
                """))

        return {
            "message": (
                f"Collection '{collection_name}' recreated successfully."
            )
        }
 
    async def insert_one_vector(
        self,
        collection_name: str,
        text: str,
        vector: List[float],
        metadata: dict | None = None,
        record_id: int | None = None,
    ):
        collection_name = self._validate_identifier(collection_name)

        if record_id is None:
            raise ValueError(
                "record_id is required for inserting a vector."
            )

        if not isinstance(record_id, int):
            raise TypeError("record_id must be an integer chunk_id")

        if not vector:
            raise ValueError("vector cannot be empty")

        vector_literal = "[" + ",".join(map(str, vector)) + "]"

        async with self.client() as session:
            async with session.begin():
                await session.execute(
                    sql_text(f"""
                        INSERT INTO {collection_name} (
                            {PgVectorTablesSchemaEnums.VECTOR.value},
                            {PgVectorTablesSchemaEnums.TEXT.value},
                            {PgVectorTablesSchemaEnums.CHUNK_ID.value},
                            {PgVectorTablesSchemaEnums.METADATA.value}
                        )
                        VALUES (
                            :vector,
                            :text,
                            :chunk_id,
                            CAST(:metadata AS jsonb)
                        )
                    """),
                    {
                        "vector": vector_literal,
                        "text": text,
                        "chunk_id": record_id,
                        "metadata": json.dumps(metadata or {}),
                    },
                )

        return {
            "message": (
                f"Vector inserted into collection "
                f"'{collection_name}' successfully."
            ),
            "record_id": record_id,
        }
         
    async def insert_many_vectors(
        self,
        collection_name: str,
        texts: List[str],
        vectors: List[List[float]],
        metadatas: List[dict] | None = None,
        record_ids: List[int] | None = None,
        batch_size: int = 50,
    ):
        collection_name = self._validate_identifier(collection_name)

        if record_ids is None:
            raise ValueError(
                "record_ids are required and must reference chunks."
            )

        if metadatas is None:
            metadatas = [{} for _ in texts]

        if not (
            len(texts)
            == len(vectors)
            == len(metadatas)
            == len(record_ids)
        ):
            raise ValueError(
                "texts, vectors, metadatas, and record_ids "
                "must have the same length."
            )

        if not all(isinstance(record_id, int) for record_id in record_ids):
            raise TypeError("All record_ids must be integer chunk IDs")

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        async with self.client() as session:
            async with session.begin():

                for start in range(0, len(texts), batch_size):
                    end = start + batch_size

                    parameters = [
                        {
                            "vector": (
                                "[" + ",".join(map(str, vector)) + "]"
                            ),
                            "text": text,
                            "chunk_id": record_id,
                            "metadata": json.dumps(metadata),
                        }
                        for text, vector, metadata, record_id in zip(
                            texts[start:end],
                            vectors[start:end],
                            metadatas[start:end],
                            record_ids[start:end],
                        )
                    ]

                    await session.execute(
                        sql_text(f"""
                            INSERT INTO {collection_name} (
                                {PgVectorTablesSchemaEnums.VECTOR.value},
                                {PgVectorTablesSchemaEnums.TEXT.value},
                                {PgVectorTablesSchemaEnums.CHUNK_ID.value},
                                {PgVectorTablesSchemaEnums.METADATA.value}
                            )
                            VALUES (
                                :vector,
                                :text,
                                :chunk_id,
                                CAST(:metadata AS jsonb)
                            )
                        """),
                        parameters,
                    )

        return {
            "message": (
                f"{len(texts)} vectors inserted into "
                f"collection '{collection_name}' successfully."
            )
        }
           

    async def search_vectors(self, collection_name, query_vector, top_k: int = 5, distance_metric_method: str = None):
        distance_metric_method = distance_metric_method or self.distance_metric_method

        # Validate distance metric method
        if distance_metric_method not in [e.value for e in DistanceMetricEnum]:
            raise ValueError(f"Invalid distance metric method: {distance_metric_method}")

        # Map to pgvector operator class
        pgvector_operator_class = PgVectorDistanceMetricEnum[distance_metric_method.upper()].value

        async with self.client() as session:
            async with session.begin():
                result = await session.execute(
                    sql_text(f"""
                        SELECT *,1- {PgVectorTablesSchemaEnums.VECTOR.value} <-> :query_vector AS score
                        FROM {collection_name}
                        ORDER BY score desc
                        LIMIT :top_k
                    """),
                    {"query_vector": "["+ ",".join([str(v) for v in query_vector])+"]", "top_k": top_k}
                )
                search_results = await result.fetchall()

        return [
    RetrieveDocument(
        chunk_id=row["chunk_id"],
        asset_id=row["asset_id"],
        asset_name=row["asset_name"],
        text=row["text"],
        score=float(row["score"]),
        metadata=row["metadata"] or {},
    )
    for row in search_results
]
    

    async def is_index_exists(self, collection_name):
        index_name = self.default_index_name(collection_name)
        async with self.client() as session:
            async with session.begin():
                result = await session.execute(
                    sql_text(f"""
                        SELECT 1 FROM pg_indexes
                        WHERE tablename = :collection_name AND indexname = :index_name
                    """),
                    {"index_name": index_name, "collection_name": collection_name}
                )
                index_exists = await result.scalar()
        return index_exists is not None

    async def create_vector_index(self, collection_name, index_type: str = PgVectorIndexTypeEnum.HNSW.value):
        is_index_exists = await self.is_index_exists(collection_name)
        if is_index_exists:
            return {"message": f"Index already exists for collection '{collection_name}'."}
        
        async with self.client() as session:
            async with session.begin():
                records_counts = await session.execute(sql_text(f"SELECT COUNT(*) FROM {collection_name}"))
                records_counts = await records_counts.scalar()
                if records_counts < self.index_threshold:
                    self.logger.warning(f"Collection '{collection_name}' has {records_counts} records, which is below the index threshold of {self.index_threshold}. Indexing may not be effective.")
                self.logger.info(f"Creating index for collection '{collection_name}' with index type '{index_type}' and threshold {self.index_threshold}.")
                await session.execute(
                    sql_text(f"""
                        CREATE INDEX {self.default_index_name(collection_name)} ON {collection_name}
                        USING {index_type} ({PgVectorTablesSchemaEnums.VECTOR.value})
                        WITH (lists = :index_threshold)
                    """),
                    {"index_threshold": self.index_threshold}
                )

                return {"message": f"Index created for collection '{collection_name}' successfully.", "records_count": records_counts}
    async def reset_vector_index(self, collection_name, index_type: str = PgVectorIndexTypeEnum.HNSW.value):
        async with self.client() as session:
            async with session.begin():
                await session.execute(sql_text(f"DROP INDEX IF EXISTS {self.default_index_name(collection_name)}"))
                await session.execute(
                    sql_text(f"""
                        CREATE INDEX {self.default_index_name(collection_name)} ON {collection_name}
                        USING {index_type} ({PgVectorTablesSchemaEnums.VECTOR.value})
                        WITH (lists = :index_threshold)
                    """),
                    {"index_threshold": self.index_threshold}
                )
                return {"message": f"Index reset for collection '{collection_name}' successfully."}
    
    async def search_by_vector(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
    ):
        collection_name = self._validate_identifier(
            collection_name
        )

        if not query_vector:
            raise ValueError(
                "Query vector cannot be empty."
            )

        vector_string = (
            "["
            + ",".join(
                str(value)
                for value in query_vector
            )
            + "]"
        )

        async with self.client() as session:
            result = await session.execute(
                sql_text(f"""
                    SELECT
                        collection.chunk_id,
                        chunks.chunk_asset_id AS asset_id,
                        assets.asset_name,
                        collection.text,
                        collection.metadata,
                        1 - (
                            collection.vector
                            <=> CAST(:query_vector AS vector)
                        ) AS score
                    FROM {collection_name} AS collection
                    JOIN chunks
                        ON chunks.chunk_id = collection.chunk_id
                    JOIN assets
                        ON assets.asset_id = chunks.chunk_asset_id
                    ORDER BY
                        collection.vector
                        <=> CAST(:query_vector AS vector)
                    LIMIT :limit
                """),
                {
                    "query_vector": vector_string,
                    "limit": limit,
                },
            )

            rows = result.mappings().all()

        return [
            RetrieveDocument(
                chunk_id=row["chunk_id"],
                asset_id=row["asset_id"],
                asset_name=row["asset_name"],
                text=row["text"],
                score=float(row["score"]),
                metadata=row["metadata"] or {},
                
            )
            for row in rows
        ]