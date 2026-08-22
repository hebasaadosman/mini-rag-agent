from .mini_rag_base import SQLAlchemyBase
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from sqlalchemy import func
from uuid import uuid4
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship


class Project(SQLAlchemyBase):
    __tablename__ = "projects"

    project_id = Column(Integer, primary_key=True, autoincrement=True)
    project_uuid = Column(UUID(as_uuid=True), default=uuid4, unique=True,nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(),nullable=False)
    updated_at = Column(DateTime(timezone=True),  onupdate=func.now(), nullable=True)
    project_description = Column(String, nullable=True)
    

    chunks = relationship("DataChunk", back_populates="project")
    assets = relationship("Asset", back_populates="project")
    memberships = relationship(
        "ProjectMembership",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    audit_events = relationship("AuditEvent", back_populates="project")
    conversation_threads = relationship(
        "ConversationThread",
        back_populates="project",
        cascade="all, delete-orphan",
    )
