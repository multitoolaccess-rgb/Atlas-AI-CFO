"""Phase 4 — add recommendation_logs table for approval workflow.

Revision ID: P4a5b6c7d8e9
Revises: M2a3b4c5d6e7
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "P4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create recommendation_logs table."""
    op.create_table(
        "recommendation_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("impact", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_logs_user_id",
        "recommendation_logs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_logs_status",
        "recommendation_logs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop recommendation_logs table."""
    op.drop_index("ix_recommendation_logs_status", table_name="recommendation_logs")
    op.drop_index("ix_recommendation_logs_user_id", table_name="recommendation_logs")
    op.drop_table("recommendation_logs")
