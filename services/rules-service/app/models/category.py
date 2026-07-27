"""Category model — transactional taxonomy.

Phase 3 lift (``docs/wealthiq-merge-plan.md`` §4 item 9). Same trivial edit.

`categories.id` is FK-referenced by Transaction and Budget.

Phase A — Hierarchical Categories: adds a ``group`` column for the
4-group taxonomy (Income, Expenses, Debt, Investments) + Transfer.
The ``group`` column is additive; existing ``category_name`` reads
keep working. Budget_group is preserved for backward compat with
the Atlas budgeting system.
"""
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base

# Canonical top-level groups for the hierarchical taxonomy.
CATEGORY_GROUPS: list[str] = [
    "Income",
    "Expenses",
    "Debt",
    "Investments",
    "Transfer",
]


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    color = Column(String, nullable=True)
    # Budget grouping: 'fixed', 'flexible', 'debt', 'savings', 'other'
    budget_group = Column(Text, nullable=False, server_default="flexible")
    # Phase A — Hierarchical taxonomy group.
    # One of: 'Income', 'Expenses', 'Debt', 'Investments', 'Transfer'.
    # Default 'Expenses' for backward compat (most existing categories
    # are expense categories). Added via Alembic migration Q5h1i2j3k4l5.
    group = Column(String, nullable=False, server_default="Expenses", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Category {self.name} group={self.group}>"
