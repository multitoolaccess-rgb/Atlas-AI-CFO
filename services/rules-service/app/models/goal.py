"""Goal model — multi-goal financial planning (Phase 8).

The schema is intentionally minimal: every column mirrors a field on
``app.schemas.GoalCreate`` / ``GoalUpdate`` so the BE whitelist
contract is enforced at the ORM boundary (the Pydantic model
controls what is mutable; this ORM class controls WHY/WHERE).

Design choices:

- **owner-scoped** via ``user_id`` FK to ``users.id``. Every
  goal is a row on the local user's progress sheet; the route
  layer never returns rows from another user.
- **soft-archive** via ``is_archived`` instead of a hard delete.
  Mirrors the Account-soft-delete pattern (Phase 7): the row stays
  in the DB so historical ``DashboardSummary`` snapshots can keep
  referencing it; ``list_goals`` filters it out by default.
- **priority** is an integer the user can sort by — high = done
  first on the UI. Phase 8 ships the column + sort order in the
  route but the FE renderer is left to enforce user-controlled
  ordering. Future phase can expose drag-reorder.
- **target_date** (Date) and **horizon_years** (Integer) are
  both nullable — the user may express a goal as "by 2045" OR as
  "in 20 years", not both. The projection engine uses whichever
  is set; ``FinancialPlans.tsx`` falls back to ``horizon_years``
  when ``target_date`` is missing.
"""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, default=0.0, nullable=False)
    target_date = Column(Date, nullable=True)
    horizon_years = Column(Integer, nullable=True)
    priority = Column(Integer, default=0, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Goal {self.name!r} target=${self.target_amount:,.0f}>"
