"""Transaction model — financial movements ledger.

Phase 3 lift from wealthiq ``backend/app/models/transaction.py`` (``docs/wealthiq-merge-plan.md`` §4
item 8). One trivial edit (see ``app/models/user.py``).

`transactions.id` has no children — leaf in the FK graph.

Phase 11 — added ``account`` and ``category`` ORM relationships so the
``GET /api/transactions/`` endpoint can ``joinedload(Transaction.account)``
without raising ``AttributeError: type object 'Transaction' has no
attribute 'account'``. The previous live-server traceback was caused
by the route passing the FK column's class-level attribute as a
joinedload target — only resolved by declaring the relationship here.
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    plaid_id = Column(String, unique=True, nullable=True, index=True)
    description = Column(String, nullable=False)
    # Phase 52+ — universal accounting column. Stored as
    # ``credit - debit`` (positive = money in, negative = money
    # out — universal across all account types). The historical
    # per-type sign-flip at import time was ALSO ``-(raw)`` for
    # credit types, which preserved ``SUM(amount) = SUM(credit) -
    # SUM(debit)`` semantics for depositories and ``SUM(debit) -
    # SUM(credit)`` for credit accounts — the new ``amount``
    # computation lands at the SAME value so existing read paths
    # (which read ``amount``) continue to produce identical
    # sums. The cross-account ``total_balance`` (which used a
    # type-aware SUM with sign flips per type) is the only
    # aggregate that materially drifts — Phase 52+ recomputes
    # ``Account.current_balance`` and the dashboard formula is
    # updated to match the new convention simultaneously.
    amount = Column(Float, nullable=False)
    # Phase 52+ — split bookkeeping columns. Both NULLABLE so the
    # zero-amount edge case (transferred-in-then-out row, or a
    # FX-neutral entry) doesn't need to carry a bogus 0.0 in
    # every column. Convention:
    #   debit:  unsigned POSITIVE = money that LEFT the account.
    #   credit: unsigned POSITIVE = money that ENTERED the account.
    # Exactly one of (``debit``, ``credit``) is non-zero per
    # transaction for non-zero rows; both NULL for an FX-neutral
    # zero-amount row. The route layer enforces this at INSERT
    # time so a parser bug that emits both non-zero surfaces as a
    # 500 with a clear log line, NOT as a silently doubled amount
    # on the next balance recompute.
    #
    # NOTE: ``amount``'s semantics are NOW type-aware. For
    # depository accounts, ``amount = credit - debit`` matches
    # the universal accounting convention (positive = money in,
    # negative = money out). For credit-type accounts, the
    # parser emits ``amount = -(raw)`` so ``amount`` is signed
    # OPPOSITE to the bank's display (a purchase shows as
    # negative even though the bank's Debit column shows it
    # positive). ``SUM(amount)`` therefore has DIFFERENT
    # meanings for different account types. The cross-account
    # ``Account.current_balance`` is computed type-aware via
    # ``recalculate_account_balance``; the ``amount`` column is
    # preserved for backward compat with read paths that key
    # off single-account sums.
    debit = Column(Float, nullable=True)
    credit = Column(Float, nullable=True)
    is_pending = Column(Boolean, default=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)
    merchant_name = Column(String, nullable=True)
    merchant_category = Column(String, nullable=True)
    # Phase 54+ — duplicate tracking. When a transaction is detected
    # as a duplicate during import, it IS still inserted (not skipped)
    # but flagged with ``is_duplicate=True`` and ``duplicate_of_id``
    # pointing to the earlier transaction it matches. The Activity
    # page renders these with a duplicate badge and the user can
    # resolve them (keep this, keep original, keep all).
    is_duplicate = Column(Boolean, default=False, nullable=False, index=True)
    duplicate_of_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Phase 11 — ORM relationships that mirror the FK columns. Without
    # these, ``joinedload(Transaction.account)`` raises AttributeError
    # at list-time (the original "Activity tab errored" report) because
    # SQLAlchemy's joinedload needs a Mapper-property target, not a
    # raw ForeignKey column. Defining the relationship is zero-cost —
    # it's just metadata that the query planner uses to emit a JOIN.
    # One-way is sufficient (Joinedload works either way); we declare
    # the Account side too for completeness (Account.transactions)
    # but do NOT use back_populates so the relationship stays
    # context-light even if one side is modified independently.
    account = relationship("Account")
    category = relationship("Category")

    def __repr__(self) -> str:
        return f"<Transaction {self.description}>"
