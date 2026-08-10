from enum import Enum


class AssetTypeEnum(str, Enum):
    FILE = "file"



class AssetStatus(str, Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"