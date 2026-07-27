"""add goals table

Revision ID: c1d2e3f4a5b6
Revises: b0a32894ce61
Create Date: 2026-06-29 21:30:00.000000

Phase 8 — multi-goal financial planning.

Adds the ``goals`` table that owns the local user's progress sheet.
Concurrency model:

- ``user_id`` FK to ``users.id`` — owner-scoped; every goal is a
  row on the active user's sheet.
- ``is_archived`` BOOL — soft-delete flag (the dashboard summary
  keeps showing historical ``GoalResponse`` records by id, so a
  hard delete would break renderers that hold stale snapshots).
- ``priority`` INT — user-sortable column; high = shown first.
- ``target_date`` DATE nullable + ``horizon_years`` INT nullable —
  the user expresses the deadline either way (whichever they set
  is what the FE projection engine uses).

Indexes:
- ``ix_goals_user_id`` — speeds up ``WHERE user_id = :id`` lookups
  on every read path (list + dashboard summary).
- ``ix_goals_id`` — primary-key alignment with the rest of the
  schema (every other table also declares this).

Down-grade drops the table; the soft-delete semantics mean that
no FK from another table can reference ``goals.id`` today, so the
down-grade is reversible without scrub-then-drop.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b0a32894ce61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("horizon_years", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_goals_id"), "goals", ["id"], unique=False)
    op.create_index(op.f("ix_goals_user_id"), "goals", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_goals_user_id"), table_name="goals")
    op.drop_index(op.f("ix_goals_id"), table_name="goals")
    op.drop_table("goals")
