from uuid import uuid4

from ..VectorDBInterface import VectorDBInterface
import logging
from ..VectorDBEnum import DistanceMetricEnum
from qdrant_client import QdrantClient,models
from models.db_schemes import RetrieveDocument

class QdrantDBProvider(VectorDBInterface):
    def __init__(self,db_client,db_path, default_vector_size: int,  distance_metric_method: str = "cosine",index_threshold: int = 100):

        if distance_metric_method == DistanceMetricEnum.COSINE.value:
            self.distance_metric = models.Distance.COSINE
        elif distance_metric_method == DistanceMetricEnum.DOT.value:
            self.distance_metric = models.Distance.DOT
        elif distance_metric_method == DistanceMetricEnum.EUCLIDEAN.value:
            self.distance_metric = models.Distance.EUCLIDEAN
        else:
            self.distance_metric = distance_metric_method
        self.db_path = db_path
        self.client = db_client
        self.default_vector_size = default_vector_size
        self.index_threshold = index_threshold
        self.logging = logging.getLogger("uvicorn")

    async def connect(self):
        try:
            self.client = QdrantClient(path=self.db_path)
            self.logging.info(f"Connected to Qdrant at {self.db_path}")
        except Exception as e:
            self.logging.error(f"Failed to connect to Qdrant: {e}")
            raise

    async def disconnect(self):
        # QdrantClient does not have a disconnect method, but we can set the client to None
        self.client = None
        self.logging.info("Disconnected from Qdrant")

    async def is_collection_exists(self, collection_name: str) -> bool:
        try:
            return await self.client.collection_exists(collection_name)
        except Exception as e:
            self.logging.error(f"Error checking if collection exists: {e}")
            raise

    async def get_collection_info(self, collection_name: str) -> dict:
        try:
            return await self.client.get_collection(collection_name).dict()
        except Exception as e:
            self.logging.error(f"Error getting collection info: {e}")
            raise

    async def list_all_collections(self):
        return await self.client.list_all_collections()
    
    async def create_collection(self, collection_name: str, vector_size: int, do_reset: bool = False):
        try:
            if do_reset and await self.is_collection_exists(collection_name):
               _= await self.delete_collection(collection_name)
            if not await self.is_collection_exists(collection_name):
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(size=vector_size, distance=self.distance_metric)
                )
                self.logging.info(f"Collection '{collection_name}' created with vector size {vector_size} and distance metric {self.distance_metric}.")
                return True
            else:
                self.logging.info(f"Collection '{collection_name}' already exists.")
                return False
        except Exception as e:
            self.logging.error(f"Error creating collection: {e}")
            return False

    async def insert_one_vector(
        self,
        collection_name: str,
        text: str,
        vector: list[float],
        metadata: dict | None = None,
        record_id: str | None = None
    ) -> bool:
        try:
            if not await self.is_collection_exists(collection_name):
                self.logging.warning(
                    f"Collection '{collection_name}' does not exist."
                )
                return False

            point_id = record_id or str(uuid4())

            point = models.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text": text,
                    **(metadata or {})
                }
            )
            
            result = await self.client.upsert(
                collection_name=collection_name,
                points=[point],
                wait=True
            )

            self.logging.info(
                f"Inserted vector into collection '{collection_name}' "
                f"with record ID '{point_id}'. Result: {result}"
            )

            return True

        except Exception:
            self.logging.exception(
                f"Error inserting vector into '{collection_name}'."
            )
            raise

    async def search_by_vector(self, collection_name: str, query_vector: list, limit: int):
        try:
            if not await self.is_collection_exists(collection_name):
                self.logging.warning(f"Collection '{collection_name}' does not exist.")
                return []
            search_result = await self.client.search_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit
            )
            self.logging.info(f"Search completed in collection '{collection_name}' with limit {limit}.")
            # return search_result.points
            return [RetrieveDocument
            (score=point.score, 
            text=point.payload.get("text", "")) 
            for point in search_result.points]
        except Exception as e:
            self.logging.error(f"Error searching by vector: {e}")
            raise

    async def insert_many_vectors(
        self,
        collection_name: str,
        vectors: list,
        metadata: dict | None = None,
        record_ids: list | None = None,
        batch_size: int = 50
         ) -> int:
        try:
            if not await self.is_collection_exists(collection_name):
                self.logging.warning(
                    f"Collection '{collection_name}' does not exist."
                )
                return 0

            inserted_count = 0
            points = []

            print("=" * 60)
            print("Collection:", collection_name)
            print("Collection exists:", await self.is_collection_exists(collection_name))
            print("Total vectors:", len(vectors))
            print("=" * 60)

            for i, item in enumerate(vectors):
                record_id = (
                    record_ids[i]
                    if record_ids and i < len(record_ids)
                    else str(uuid4())
                )

                point = models.PointStruct(
                    id=record_id,
                    vector=item["vector"],
                    payload={
                        "text": item.get("text", ""),
                        **(metadata or {})
                    }
                )

                print(f"Point {i + 1}")
                print("ID:", record_id)
                print("Vector length:", len(item["vector"]))
                print("Text:", item.get("text", "")[:50])
                print("-" * 40)

                points.append(point)

                if len(points) >= batch_size:
                    batch_count = len(points)

                    print(f"Uploading batch with {batch_count} points...")

                    result = await self.client.upsert(
                        collection_name=collection_name,
                        points=points,
                        wait=True
                    )

                    print("Upsert result:", result)

                    info = await self.client.get_collection(collection_name)
                    print("Points after upload:", info.points_count)
                    print("=" * 60)

                    inserted_count += batch_count
                    points = []

            if points:
                batch_count = len(points)

                print(f"Uploading final batch with {batch_count} points...")

                result = await self.client.upsert(
                    collection_name=collection_name,
                    points=points,
                    wait=True
                )

                print("Upsert result:", result)

                info = await self.client.get_collection(collection_name)
                print("Points after upload:", info.points_count)
                print("=" * 60)

                inserted_count += batch_count

            self.logging.info(
                f"Inserted {inserted_count} vectors "
                f"into collection '{collection_name}'."
            )

            return inserted_count

        except Exception:
            self.logging.exception(
                f"Error inserting vectors into '{collection_name}'."
            )
            raise
   
    async def delete_collection(self, collection_name: str):
        try:
            if not await self.is_collection_exists(collection_name):
                self.logging.warning(f"Collection '{collection_name}' does not exist.")
                return
            await self.client.delete_collection(collection_name)
            self.logging.info(f"Collection '{collection_name}' deleted.")
        except Exception as e:
            self.logging.error(f"Error deleting collection: {e}")
            raise