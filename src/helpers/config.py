from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
class Settings(BaseSettings):


    APP_NAME: str
    APP_VERSION: str
    APP_ENV: str = "local"
    OPENAI_API_KEY: str
    FILE_ALLOWED_TYPES: list[str]
    FILE_MAX_SIZE: int
    FILE_DEFAULT_CHUNK_SIZE: int
    MONGODB_URI: str
    MONGODB_NAME: str 
    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str
    OPENAI_KEY: str=None
    OPENAI_API_URL: str=None
    COHERE_API_KEY: str=None
    GENEERATION_MODEL_ID: str
    GENEERATION_MODEL_ID_LITERAL: List[str]=None
    EMBEDDING_MODEL_ID: str=None
    EMBEDDING_MODEL_TEMPERATURE: float=None
    INPUT_DEFAULT_MAX_CHARACTERS: int=None
    GENERATION_DEFAULT_MAX_TOKENS: int=None
    EMBEDDING_MODEL_SIZE: int
    VECTOR_DB_BACKEND_LITERAL: List[str]=None
    VECTOR_DB_PGVEC_INDEX_THRESHOLD: int=100
    VECTOR_DB_BACKEND: str
    VECTOR_DB_PATH: str
    VECTOR_DB_DISTANCE_METRIC_METHOD: str

    DEFAULT_LANGUAGE: str
    PRIMARY_LANGUAGE: str

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    INDEX_PAGE_SIZE: int
    INDEX_MAX_RETRIES: int
    INDEX_BATCH_TIMEOUT_SECONDS: int
    INDEX_MAX_BACKOFF_SECONDS: int
    INDEX_DELAY_BETWEEN_BATCHES_SECONDS: int

 # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list[str] = ["json"]

    CELERY_TASK_TIME_LIMIT: int = 600
    CELERY_TASK_SOFT_TIME_LIMIT: int = 540
    CELERY_TASK_ACKS_LATE: bool = True
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1
    CELERY_WORKER_CONCURRENCY: int = 2
    CELERY_FLOWER_PASSWORD: str 

    LANGSMITH_TRACING: bool
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str

    AGENT_MEMORY_MAX_MESSAGES: int = 40

    # Authentication is opt-in while the project is migrated endpoint by
    # endpoint. Production must set AUTH_ENABLED=true and a strong secret.
    AUTH_ENABLED: bool = False
    AUTH_JWT_SECRET: Optional[str] = None
    AUTH_JWT_ALGORITHM: str = "HS256"
    AUTH_JWT_ISSUER: str = "mini-rag-agent"
    AUTH_JWT_AUDIENCE: str = "mini-rag-agent-api"
    AUTH_JWT_LEEWAY_SECONDS: int = 30

    # Outbound email. Credentials are consumed only by the SMTP adapter and
    # are never placed in agent state, prompts, or tool-call arguments.
    SMTP_ENABLED: bool = False
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_ADDRESS: Optional[str] = None
    SMTP_SECURITY: str = "starttls"
    SMTP_TIMEOUT_SECONDS: float = 15.0
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

def get_settings() -> Settings:
    return Settings()
