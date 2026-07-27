"""Holding model — one row per position in a portfolio import.

Phase 39 — portfolio positions import. Each row represents a single
holding (stock, ETF, mutual fund, cash position) within an account at
the time of import. A re-import of the same account's positions CSV
replaces all previous holdings for that account (upsert-by-account).

``holdings.id`` is standalone — no FK links from Transaction. The
account's ``current_balance`` is recalculated from
``SUM(holdings.current_value)`` after every import.
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(
        Integer, ForeignKey("accounts.id"), nullable=False, index=True
    )
    import_batch_id = Column(
        Integer, ForeignKey("import_batches.id"), nullable=True, index=True
    )
    # Ticker symbol (e.g. "AAPL", "VTI", "SPAXX"). May be empty for
    # cash positions or pending-activity rows that have no symbol.
    symbol = Column(String, nullable=True)
    # Human-readable description (e.g. "Apple Inc.", "Vanguard Total
    # Stock Market ETF", "FIDELITY GOVERNMENT MONEY MARKET").
    description = Column(String, nullable=True)
    # Number of shares held. ``None`` for cash positions (which have
    # a Current Value but no quantity).
    quantity = Column(Float, nullable=True)
    # Price per share at time of import.
    last_price = Column(Float, nullable=True)
    # Dollar value of the position (= quantity × last_price for
    # equities; direct value for cash positions).
    current_value = Column(Float, nullable=False, default=0.0)
    # Total cost basis (what was paid for the shares). ``None`` when
    # not available (e.g. cash positions, pending activity).
    cost_basis_total = Column(Float, nullable=True)
    # Asset type: "Cash", "Stock", "ETF", "Mutual Fund", etc.
    type = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<Holding {self.symbol or '(no symbol)'} "
            f"acct={self.account_id} val={self.current_value}>"
        )
