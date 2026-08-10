from pydantic import BaseModel, Field
from typing import Optional
from fastapi import Body

class PushRequest(BaseModel):
   
    do_reset: Optional[int] = 0

class SearchRequest(BaseModel):
    query: str 
    limit: Optional[int] = Field(5, description="The maximum number of search results to return.")