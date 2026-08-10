from .mini_rag_base import SQLAlchemyBase
from sqlalchemy import Column, Integer, String, DateTime,ForeignKey
from datetime import datetime
from sqlalchemy import func
from uuid import uuid4
from sqlalchemy.dialects.postgresql import UUID,JSONB
from sqlalchemy.orm import relationship
from sqlalchemy import Index
# asset.py
from models.enums import AssetStatus

class Asset(SQLAlchemyBase):
    __tablename__ = "assets"

    asset_id = Column(Integer, primary_key=True, autoincrement=True)
    asset_uuid = Column(UUID(as_uuid=True), default=uuid4, unique=True,nullable=False)

    asset_type = Column(String, nullable=False)
    asset_name = Column(String, nullable=False)
    asset_size = Column(Integer, nullable=False)
    asset_config = Column(JSONB, nullable=True)
    asset_project_id = Column(Integer, ForeignKey("projects.project_id"), nullable=False)

    project = relationship("Project", back_populates="assets")
    chunks = relationship("DataChunk", back_populates="asset")

    created_at = Column(DateTime(timezone=True), server_default=func.now(),nullable=False)
    updated_at = Column(DateTime(timezone=True),  onupdate=func.now(), nullable=True)

    asset_status = Column(
        String,
        nullable=False,
        default=AssetStatus.UPLOADED.value,
        server_default=AssetStatus.UPLOADED.value,
    )

    asset_progress = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    asset_checksum = Column(
        String(64),
        nullable=True,
    )
    __table_args__ = (
        # Add a unique constraint on asset_name and asset_project_id    
        Index('ix_asset_project_id', asset_project_id),
        Index('uq_asset_name_project_id', asset_name, asset_project_id, unique=True),
        Index('ix_asset_type', asset_type),
        Index(
            "ix_asset_checksum",
            asset_checksum,
        ),
    )
