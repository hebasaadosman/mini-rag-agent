"""Append-only audit records for security-relevant project operations."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .mini_rag_base import SQLAlchemyBase


class AuditEvent(SQLAlchemyBase):
    __tablename__ = "audit_events"

    audit_event_id = Column(Integer, primary_key=True, autoincrement=True)
    principal_id = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False)
    outcome = Column(String(32), nullable=False)
    project_id = Column(
        Integer,
        ForeignKey("projects.project_id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json = Column(JSONB, nullable=True)
    occurred_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project = relationship("Project", back_populates="audit_events")

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('allowed', 'denied', 'succeeded', 'failed')",
            name="ck_audit_events_outcome",
        ),
        Index("ix_audit_events_principal_id", "principal_id"),
        Index("ix_audit_events_project_id", "project_id"),
        Index("ix_audit_events_occurred_at", "occurred_at"),
    )
