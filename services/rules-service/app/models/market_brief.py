"""Immutable owner-scoped generated Market Intelligence briefings."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class MarketBrief(Base):
    __tablename__ = "market_briefs"
    __table_args__ = (
        UniqueConstraint("user_id", "portfolio_state_hash", "universe_hash", "report_window", "schema_version", "calculation_version", name="uq_market_briefs_idempotency"),
        CheckConstraint("length(portfolio_state_hash) = 64", name="ck_market_brief_state_hash"),
        CheckConstraint("length(universe_hash) = 64", name="ck_market_brief_universe_hash"),
    )
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    portfolio_state_hash = Column(String(64), nullable=False)
    universe_hash = Column(String(64), nullable=False)
    report_window = Column(String(64), nullable=False)
    schema_version = Column(String(64), nullable=False)
    calculation_version = Column(String(64), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
