"""Category model — transactional taxonomy.

Phase 3 lift (``docs/wealthiq-merge-plan.md`` §4 item 9). Same trivial edit.

`categories.id` is FK-referenced by Transaction and Budget.

Phase A — Hierarchical Categories: adds a ``group`` column for the
4-group taxonomy (Income, Expenses, Debt, Investments) + Transfer.
The ``group`` column is additive; existing ``category_name`` reads
keep working. Budget_group is preserved for backward compat with
the Atlas budgeting system.

Phase 30h — Sub-categories: adds a nullable self-referential
``parent_id`` so a category can be a CHILD of another (e.g. ``Coffee
Shops`` under ``Food & Dining``). Existing flat rows are all parents;
children are created on demand by the LLM Pass-4 accept-proposal
flow. ``parent_id`` is additive and never breaks the group taxonomy
(a child inherits its parent's ``group``).
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
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
    # Phase 30h — sub-category hierarchy. NULL = top-level category;
    # otherwise the id of the parent this category nests under. A child
    # inherits its parent's ``group``. Added via Alembic migration
    # U3e4f5a6b7c8. Self-referential FK; cycle prevention lives in the
    # route layer (a parent can never be its own descendant).
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    parent = relationship("Category", remote_side=[id], backref="children")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Category {self.name} group={self.group} parent_id={self.parent_id}>"
