from pydantic import BaseModel, Field
from typing import Optional

class ProcessRequest(BaseModel):
    asset_id: int | None = None
    chunk_size: int
    overlap_size: int
    do_reset: int = 0
