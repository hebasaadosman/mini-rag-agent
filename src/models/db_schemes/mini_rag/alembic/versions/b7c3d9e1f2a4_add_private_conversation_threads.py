"""add private conversation threads

Revision ID: b7c3d9e1f2a4
Revises: e9b2a4d5c6f7
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c3d9e1f2a4"
down_revision = "e9b2a4d5c6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("conversation_thread_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("owner_principal_id", sa.String(length=255), nullable=False),
        sa.Column(
            "scope",
            sa.String(length=32),
            server_default="private",
            nullable=False,
        ),
        sa.Column("checkpoint_key", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope IN ('private')", name="ck_conversation_threads_scope"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("conversation_thread_id"),
        sa.UniqueConstraint("checkpoint_key"),
        sa.UniqueConstraint(
            "project_id",
            "thread_id",
            name="uq_conversation_threads_project_thread",
        ),
    )
    op.create_index(
        "ix_conversation_threads_project_owner",
        "conversation_threads",
        ["project_id", "owner_principal_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_ownership_rows = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM conversation_threads)")
    ).scalar()
    if has_ownership_rows:
        raise RuntimeError(
            "Refusing destructive downgrade: conversation_threads contains "
            "private ownership records. Use the documented forward-only "
            "rollback procedure or restore a verified database snapshot."
        )
    op.drop_index(
        "ix_conversation_threads_project_owner",
        table_name="conversation_threads",
    )
    op.drop_table("conversation_threads")
