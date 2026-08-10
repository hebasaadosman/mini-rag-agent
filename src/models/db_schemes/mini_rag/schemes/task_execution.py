
from .mini_rag_base import SQLAlchemyBase
from uuid import uuid4
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID



class TaskExecution(SQLAlchemyBase):
    __tablename__ = "task_executions"

    execution_id = Column(Integer, primary_key=True)

    idempotency_key = Column(
        String(64),
        nullable=False,
        unique=True,
    )

    celery_task_id = Column(
        UUID(as_uuid=True),
        nullable=False,
    )

    operation = Column(
        String(50),
        nullable=False,
    )

    status = Column(
        String(20),
        nullable=False,
    )

    result = Column(
        JSONB,
        nullable=True,
    )

    error_message = Column(
        String,
        nullable=True,
    )

    started_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    finished_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    project_id = Column(
    Integer,
    nullable=False,
    )

    asset_id = Column(
    Integer,
    nullable=True,
    )

    updated_at = Column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
    )

    heartbeat_at = Column(
    DateTime(timezone=True),
    nullable=True,
)

    lease_expires_at = Column(
    DateTime(timezone=True),
    nullable=True,
)

    attempt_count = Column(
    Integer,
    nullable=False,
    default=1,
    server_default="1",
   )
    __table_args__ = (
    Index(
        "ix_task_executions_project_id",
        "project_id",
    ),
    Index(
        "ix_task_executions_asset_id",
        "asset_id",
    ),
    Index(
        "ix_task_executions_status",
        "status",
    ),
    Index(
            "ix_task_executions_lease_expires_at",
            "lease_expires_at",
        ),
)


    
