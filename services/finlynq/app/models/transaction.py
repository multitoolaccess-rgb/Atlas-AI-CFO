"""Transaction model — financial movements ledger.

Phase-F5 verbatim lift of ``services/rules-service/app/models/transaction.py``.

Circular-import safety: ``relationship("Account")`` and
``relationship("Category")`` are STRING references — SQLAlchemy
resolves them at mapper-configuration time against the declarative
metadata registry, well after both modules complete their initial
Python import. No top-of-file ``from app.models.account import Account``
needed.

`transactions.id` has no children — leaf in the FK graph.
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
    amount = Column(Float, nullable=False)
    is_pending = Column(Boolean, default=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)
    merchant_name = Column(String, nullable=True)
    merchant_category = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # See module docstring — string-based relationships resolve at
    # mapper-config time so circular-import-free.
    account = relationship("Account")
    category = relationship("Category")

    def __repr__(self) -> str:
        return f"<Transaction {self.description}>"
