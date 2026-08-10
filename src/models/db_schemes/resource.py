from pydantic import BaseModel, Field,validator
from typing import Optional 
from datetime import datetime
from bson.objectid import ObjectId


class Resource(BaseModel):
    id: Optional[ObjectId] = Field(None, alias="_id")
    resource_project_id: ObjectId
    resource_type: str= Field(..., min_length=1)
    resource_name: str= Field(..., min_length=1)
    resource_size: int= Field(ge=0,default=None)
    resource_config: dict = Field(default=None)

    resource_created_at: datetime = Field(default=datetime.utcnow)
    
    
    # resource_description: Optional[str] = None
    # resource_updated_at: Optional[datetime] = None


    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def get_indexes(cls):
        return [
            {
                "key": [("resource_project_id", 1), ("resource_id", 1)],
                "name": "resource_project_id_resource_id_index",
                "unique": False,
            },
            {
                "key": [("resource_name", 1), ("resource_project_id", 1)],
                "name": "resource_name_resource_project_id_index",
                "unique": True,
            },

        ]