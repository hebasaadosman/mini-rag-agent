"""add request context to task executions

Revision ID: e9b2a4d5c6f7
Revises: c4d6e8f0a1b2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e9b2a4d5c6f7"
down_revision: Union[str, Sequence[str], None] = "c4d6e8f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_executions", sa.Column("principal_id", sa.String(length=255), nullable=True))
    op.add_column("task_executions", sa.Column("correlation_id", sa.String(length=128), nullable=True))
    op.add_column("task_executions", sa.Column("request_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("ix_task_executions_principal_id", "task_executions", ["principal_id"])
    op.create_index("ix_task_executions_correlation_id", "task_executions", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_task_executions_correlation_id", table_name="task_executions")
    op.drop_index("ix_task_executions_principal_id", table_name="task_executions")
    op.drop_column("task_executions", "request_metadata")
    op.drop_column("task_executions", "correlation_id")
    op.drop_column("task_executions", "principal_id")
