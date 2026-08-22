from uuid import uuid4

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


class ConversationThread(SQLAlchemyBase):
    """Private conversation metadata; checkpoint content remains in LangGraph."""

    __tablename__ = "conversation_threads"

    conversation_thread_id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id = Column(String(255), nullable=False)
    owner_principal_id = Column(String(255), nullable=False)
    # Deliberately constrained to private for this phase. Shared conversations
    # will need an explicit participant model and a separately approved policy.
    scope = Column(String(32), nullable=False, server_default="private")
    # Never expose this value in an API response. It prevents client-provided
    # public thread IDs from becoming direct LangGraph checkpoint identifiers.
    checkpoint_key = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: str(uuid4()),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    project = relationship("Project", back_populates="conversation_threads")

    __table_args__ = (
        CheckConstraint(
            "scope IN ('private')",
            name="ck_conversation_threads_scope",
        ),
        UniqueConstraint(
            "project_id",
            "thread_id",
            name="uq_conversation_threads_project_thread",
        ),
        Index(
            "ix_conversation_threads_project_owner",
            "project_id",
            "owner_principal_id",
        ),
    )
