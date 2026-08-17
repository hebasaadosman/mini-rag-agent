from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .mini_rag_base import SQLAlchemyBase


class ProjectMembership(SQLAlchemyBase):
    """Authorization relationship between an external identity and a project."""

    __tablename__ = "project_memberships"

    membership_id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    principal_id = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project = relationship("Project", back_populates="memberships")

    __table_args__ = (
        CheckConstraint(
            "role IN ('viewer', 'contributor', 'admin')",
            name="ck_project_memberships_role",
        ),
        UniqueConstraint(
            "project_id",
            "principal_id",
            name="uq_project_memberships_project_principal",
        ),
        Index("ix_project_memberships_principal_id", "principal_id"),
        Index("ix_project_memberships_project_id", "project_id"),
    )
