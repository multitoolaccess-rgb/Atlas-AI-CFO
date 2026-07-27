"""Account model — checking, savings, investment, crypto, etc.

Phase-F5 verbatim lift of ``services/rules-service/app/models/account.py``
(itself a Phase-3 wealthiq lift). Both services bind to the SAME
``accounts`` table per Phase-F2 shared-DB wiring decision —
Finlynq's read-side aggregator at ``/state/summary`` queries
``Account.current_balance`` and ``Account.last_sync`` against rows the
rules-service dashboard forwarder re-emits to the FE.

Schema divergence risk: any PR that touches the column declaration
on EITHER service's copy without the matching change on the other
will silently desync — the cross-DB invariant test
``services/tests/test_state_aggregator_cross_db.py`` catches this
via ``Account.user_id`` FK binding. The simplest maintenance rule
is "edit rules-service first; copy verbatim into Finlynq in the
same commit".

`accounts.id` is FK-referenced by Transaction and ImportBatch.
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    plaid_id = Column(String, unique=True, nullable=True, index=True)
    account_name = Column(String, nullable=False)
    account_number = Column(String, nullable=True)  # masked
    account_type = Column(String, nullable=False)
    account_subtype = Column(String, nullable=True)
    current_balance = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_sync = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Account {self.account_name}>"
