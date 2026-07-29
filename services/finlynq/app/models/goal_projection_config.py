"""Finlynq-owned, explicit Phase 1 projection-goal configuration."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class GoalProjectionConfig(Base):
    """Server-owned inputs for the sole supported Phase 1 goal kind.

    This is intentionally not an end-user request model.  It contains only
    bounded planning inputs and provenance references, never raw financial
    records or client-supplied generation payloads.
    """

    __tablename__ = "goal_projection_configs"
    __table_args__ = (UniqueConstraint("goal_id", name="uq_goal_projection_configs_goal"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    projection_kind = Column(String(32), nullable=False)
    currency_code = Column(String(3), nullable=False)
    monthly_contribution = Column(Numeric(38, 2, asdecimal=True), nullable=False)
    contribution_source_reference = Column(String(128), nullable=False)
    contribution_observed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
