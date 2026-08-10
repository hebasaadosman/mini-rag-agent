"""add asset processing status

Revision ID: 8194edd05d08
Revises: f1458315c1da
Create Date: 2026-07-27 22:59:26.702738
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8194edd05d08"
down_revision: Union[str, Sequence[str], None] = "f1458315c1da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "assets",
        sa.Column(
            "asset_status",
            sa.String(),
            server_default="uploaded",
            nullable=False,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "asset_progress",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    op.create_check_constraint(
        "ck_assets_progress_range",
        "assets",
        "asset_progress >= 0 AND asset_progress <= 100",
    )

    op.add_column(
        "projects",
        sa.Column(
            "project_description",
            sa.String(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "projects",
        "project_description",
    )

    op.drop_constraint(
        "ck_assets_progress_range",
        "assets",
        type_="check",
    )

    op.drop_column(
        "assets",
        "asset_progress",
    )

    op.drop_column(
        "assets",
        "asset_status",
    )