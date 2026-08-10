from abc import ABC, abstractmethod
from typing import List, Dict, Any
from models.db_schemes import RetrieveDocument

class VectorDBInterface(ABC):


    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def is_collection_exists(self, collection_name: str) -> bool:
        pass

    @abstractmethod
    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        pass    

    @abstractmethod
    def list_all_collections(self) -> List[str]:
        pass

    @abstractmethod
    def create_collection(self, collection_name: str, vector_size: int,do_reset: bool = False):
        pass

    async def insert_one_vector(self, collection_name: str,text:str, vector: list,metadata: dict = None,record_id: str = None):
        pass

    async def insert_many_vectors(self, collection_name: str, vectors: List[dict],metadata: dict = None,record_ids: List[str] = None,batch_size: int = 50):
        pass

    @abstractmethod
    def search_by_vector(self, collection_name: str, query_vector: list, limit: int)-> List[RetrieveDocument]:
        pass

    @abstractmethod
    def delete_collection(self, collection_name: str):
        pass