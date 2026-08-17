"""add project memberships

Revision ID: a9e70e3af010
Revises: 678e109b0185
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9e70e3af010"
down_revision: Union[str, Sequence[str], None] = "678e109b0185"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_memberships",
        sa.Column("membership_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("principal_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('viewer', 'contributor', 'admin')",
            name="ck_project_memberships_role",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("membership_id"),
        sa.UniqueConstraint(
            "project_id",
            "principal_id",
            name="uq_project_memberships_project_principal",
        ),
    )
    op.create_index(
        "ix_project_memberships_principal_id",
        "project_memberships",
        ["principal_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_memberships_project_id",
        "project_memberships",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_memberships_project_id", table_name="project_memberships")
    op.drop_index("ix_project_memberships_principal_id", table_name="project_memberships")
    op.drop_table("project_memberships")
