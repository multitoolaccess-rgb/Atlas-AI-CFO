"""Goal model — multi-goal financial planning.

Phase-F5 verbatim lift of ``services/rules-service/app/models/goal.py``.

The Finlynq canonical store now owns this table; the dashboard
aggregator at ``/state/summary`` queries ``Goal`` rows ordered by
priority DESC + created_at ASC, filtered ``is_archived.is_(False)``.

Schema divergence risk: same as ``Account`` — the cross-DB
invariant test asserts ``goals.user_id`` (NOT NULL no default) binds
cleanly to ``users.id``. Test factories MUST seed the User row BEFORE
the Goal row to satisfy the FK.

`goals.id` has no children — leaf in the Finlynq read-side FK graph.
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
