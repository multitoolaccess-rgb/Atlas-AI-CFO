"""Budget — spending limit for a (category, period).

Phase 3 lift (``docs/wealthiq-merge-plan.md`` §4 item 11). Enhanced for
Atlas Phase 1: category_id is now nullable (NULL = global budget), period
is 'YYYY-MM' format, and budget_group aggregation is supported.
"""
from sqlalchemy import Column, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    amount = Column(Float, nullable=False)
    period = Column(Text, nullable=False)  # 'YYYY-MM' format
    created_at = Column(Text, nullable=True)
    updated_at = Column(Text, nullable=True)

    category = relationship("Category", foreign_keys=[category_id], lazy="joined")

    # Only one Global budget (category_id is NULL) per user + period.
    # This partial unique index closes the race left by the code-level
    # guard in routes/budgets.py. Dialect-specific ``where`` keys are used
    # because SQLAlchemy accepts ``postgresql_where`` / ``sqlite_where``
    # rather than a generic ``where`` keyword for partial indexes.
    __table_args__ = (
        Index(
            "ix_budgets_user_period_global",
            "user_id",
            "period",
            unique=True,
            postgresql_where=category_id.is_(None),
            sqlite_where=category_id.is_(None),
        ),
    )

    def __repr__(self) -> str:
        return f"<Budget {self.category_id} {self.period}>"
