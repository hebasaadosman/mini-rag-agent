from .VectorDBEnum import DistanceMetricEnum
from controllers.BaseController import BaseController
from .VectorDBEnum import VectorDBEnum
from .providers import QdrantDBProvider,PGVectorDBProvider
from sqlalchemy.orm import sessionmaker

class VectorDBProviderFactory:

    def __init__(self,config: dict = None,db_client: sessionmaker = None):
        self.config = config or {}
        self.base_controller = BaseController()
        self.db_client = db_client

    def create_provider(self, provider_name: str=None, db_path: str = None, distance_metric_method: str = "cosine"):
        if provider_name == VectorDBEnum.QDRANT.value:
            db_path = db_path or self.base_controller.get_database_path(self.config.get("VECTOR_DB_PATH", "qdrant_db"))
            distance_metric_method = distance_metric_method or self.config.get("VECTOR_DB_DISTANCE_METRIC_METHOD", DistanceMetricEnum.COSINE.value)
            default_vector_size = self.config.get("VECTOR_DB_DEFAULT_VECTOR_SIZE", 1536)
            index_threshold = self.config.get("VECTOR_DB_INDEX_THRESHOLD", 100)
            return QdrantDBProvider(db_client=self.db_client, db_path=db_path, default_vector_size=default_vector_size, distance_metric_method=distance_metric_method, index_threshold=index_threshold)
                
        if provider_name == VectorDBEnum.PGVECTOR.value:
            db_path = db_path or self.base_controller.get_database_path(self.config.get("VECTOR_DB_PATH", "pgvector_db"))
            distance_metric_method = distance_metric_method or self.config.get("VECTOR_DB_DISTANCE_METRIC_METHOD", DistanceMetricEnum.COSINE.value)
            default_vector_size = self.config.get("VECTOR_DB_DEFAULT_VECTOR_SIZE", 1536)
            index_threshold = self.config.get("VECTOR_DB_INDEX_THRESHOLD", 100)
            return PGVectorDBProvider(db_client=self.db_client, db_path=db_path, default_vector_size=default_vector_size, distance_metric_method=distance_metric_method, index_threshold=index_threshold)
        
        raise ValueError(f"Unsupported provider: {provider_name}")  
