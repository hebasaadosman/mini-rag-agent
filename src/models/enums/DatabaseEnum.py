from enum import Enum

class DatabaseEnum(str, Enum):
    PROJECTS_COLLECTION = "projects"
    DATA_CHUNKS_COLLECTION = "chunks"
    ASSETS_COLLECTION = "assets"