"""Immutable persisted UI-10 Scout research runs."""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class InvestmentScoutRun(Base):
    __tablename__ = "investment_scout_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "run_id", name="uq_investment_scout_runs_owner_run"),
        CheckConstraint("length(run_id) BETWEEN 1 AND 160", name="ck_investment_scout_runs_run_id"),
        CheckConstraint("length(result_hash) = 64 AND result_hash = lower(result_hash)", name="ck_investment_scout_runs_hash"),
        CheckConstraint("length(security_id) BETWEEN 1 AND 128", name="ck_investment_scout_runs_security_id"),
        CheckConstraint("length(symbol) BETWEEN 1 AND 32", name="ck_investment_scout_runs_symbol"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    run_id = Column(String(160), nullable=False)
    security_id = Column(String(128), nullable=False, index=True)
    symbol = Column(String(32), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False)
    as_of = Column(DateTime(timezone=True), nullable=False)
    result_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
