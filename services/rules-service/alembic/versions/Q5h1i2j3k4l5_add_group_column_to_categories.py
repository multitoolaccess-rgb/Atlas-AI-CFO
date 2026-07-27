"""Phase A — add group column to categories for hierarchical taxonomy.

Revision ID: Q5h1i2j3k4l5
Revises: P4a5b6c7d8e9
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "Q5h1i2j3k4l5"
down_revision: Union[str, Sequence[str], None] = "P4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Data migration mapping ──────────────────────────────────────────
# Each entry: (old_name, new_name, group)
# - old_name = current DB name (exact match)
# - new_name = new name (same as old_name when unchanged)
# - group = canonical group assignment
#
# Categories that are RENAMED keep their id (FKs stay valid).
# New subcategories (old_name == new_name == None pattern) are NOT
# handled here — they're created by the seed_default_categories()
# function on the next cold start.
CATEGORY_MIGRATIONS: list[tuple[str, str, str]] = [
    # ── Income group ──
    ("Income", "Base Salary", "Income"),
    # ── Expenses group ──
    ("Food & Dining", "Food & Dining", "Expenses"),
    ("Groceries", "Groceries", "Expenses"),
    ("Transportation", "Transportation", "Expenses"),
    ("Shopping", "Shopping", "Expenses"),
    ("Entertainment", "Entertainment", "Expenses"),
    ("Bills & Utilities", "Bills & Utilities", "Expenses"),
    ("Health", "Health", "Expenses"),
    ("Travel", "Travel", "Expenses"),
    ("Education", "Education", "Expenses"),
    ("Other", "Other", "Expenses"),
    ("Vehicle Maintainace", "Vehicle Maintenance", "Expenses"),
    ("ATM Withdrawals", "ATM Withdrawals", "Expenses"),
    ("Home Improvement", "Home Improvement", "Expenses"),
    # ── Debt group ──
    ("Mortgage", "Mortgage", "Debt"),
    ("Car Loan", "Loan Payments", "Debt"),
    ("Credit Cards - Interest Paid", "Interest Paid", "Debt"),
    ("Life Insurance", "Life Insurance", "Debt"),
    # ── Investments group ──
    ("Investments", "Brokerage Buys", "Investments"),
    # ── Transfer group ──
    ("Transfer", "Transfer", "Transfer"),
    ("Money Transfer - India", "Money Transfer - India", "Transfer"),
]


def upgrade() -> None:
    """Add group column + data migration to remap categories."""
    # Step 1: Add the group column with default 'Expenses'.
    op.add_column(
        "categories",
        sa.Column("group", sa.String(), nullable=False, server_default="Expenses"),
    )
    op.create_index("ix_categories_group", "categories", ["group"], unique=False)

    # Step 2: Data migration — rename + re-group existing categories.
    conn = op.get_bind()
    for old_name, new_name, group in CATEGORY_MIGRATIONS:
        # Update group for all matching rows (including those where
        # old_name == new_name — we still need to set the group).
        conn.execute(
            sa.text(
                "UPDATE categories SET \"group\" = :group WHERE name = :old_name"
            ),
            {"group": group, "old_name": old_name},
        )
        # Rename if the name changed.
        if old_name != new_name:
            conn.execute(
                sa.text(
                    "UPDATE categories SET name = :new_name WHERE name = :old_name"
                ),
                {"new_name": new_name, "old_name": old_name},
            )

    # Step 3: Set any remaining NULL groups to 'Expenses' (safety net
    # for user-created categories that weren't in the mapping).
    conn.execute(
        sa.text("UPDATE categories SET \"group\" = 'Expenses' WHERE \"group\" IS NULL")
    )


def downgrade() -> None:
    """Remove group column and reverse renames."""
    conn = op.get_bind()

    # Reverse renames (new_name → old_name).
    reverse_migrations = [
        (new_name, old_name)
        for old_name, new_name, _ in CATEGORY_MIGRATIONS
        if old_name != new_name
    ]
    for new_name, old_name in reverse_migrations:
        conn.execute(
            sa.text(
                "UPDATE categories SET name = :old_name WHERE name = :new_name"
            ),
            {"old_name": old_name, "new_name": new_name},
        )

    op.drop_index("ix_categories_group", table_name="categories")
    op.drop_column("categories", "group")
