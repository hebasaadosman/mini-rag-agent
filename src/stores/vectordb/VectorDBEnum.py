from enum import Enum

class VectorDBEnum(Enum):
    QDRANT="qdrant"
    PGVECTOR="pgvector"

class DistanceMetricEnum(Enum):
    COSINE="cosine"
    DOT="dot"
    EUCLIDEAN="euclidean"

class PgVectorTablesSchemaEnums(Enum):
   ID="id"
   VECTOR="vector"
   TEXT="text"
   CHUNK_ID="chunk_id"
   METADATA="metadata"
   PGVECTOR_TABLE_PREFIX="pgvector"


class PgVectorDistanceMetricEnum(Enum):
    COSINE="vector_cosine_ops"
    DOT="vector_12_ops"

class PgVectorIndexTypeEnum(Enum):
    IVFFLAT="ivfflat"
    HNSW="hnsw"
