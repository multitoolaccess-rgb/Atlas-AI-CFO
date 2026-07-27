"""align budgets schema and add unique constraint

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Align budgets schema with app.models.budget and add unique constraint.

    The initial migration (b0a32894ce60) already created a budgets table
    with a slightly different schema (category_id NOT NULL, period String,
    created_at/updated_at DateTime). On a fresh database that table is
    present by the time this migration runs, so we alter it in place
    rather than trying to recreate it.
    """
    with op.batch_alter_table("budgets") as batch_op:
        batch_op.alter_column("category_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column(
            "period", existing_type=sa.String(), type_=sa.Text(), nullable=False
        )
        batch_op.alter_column(
            "created_at", existing_type=sa.DateTime(), type_=sa.Text()
        )
        batch_op.alter_column(
            "updated_at", existing_type=sa.DateTime(), type_=sa.Text()
        )
        batch_op.create_unique_constraint(
            "uq_budget_user_cat_period", ["user_id", "category_id", "period"]
        )


def downgrade() -> None:
    with op.batch_alter_table("budgets") as batch_op:
        batch_op.drop_constraint("uq_budget_user_cat_period", type_="unique")
        batch_op.alter_column(
            "updated_at", existing_type=sa.Text(), type_=sa.DateTime(timezone=True)
        )
        batch_op.alter_column(
            "created_at", existing_type=sa.Text(), type_=sa.DateTime(timezone=True)
        )
        batch_op.alter_column(
            "period", existing_type=sa.Text(), type_=sa.String(), nullable=True
        )
        batch_op.alter_column("category_id", existing_type=sa.Integer(), nullable=False)
