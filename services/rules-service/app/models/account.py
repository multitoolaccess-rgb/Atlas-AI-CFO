"""Account model — checking, savings, investment, crypto, etc.

Phase 3 lift from wealthiq ``backend/app/models/account.py``. Same trivial edit
as the other Phase 3 models (see ``app/models/user.py`` for rationale).

`accounts.id` is FK-referenced by Transaction and ImportBatch.
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    # Phase 16 — every account belongs to a FamilyMember (e.g. Self /
    # Spouse / Kid). NOT NULL because the auto-seed in
    # :func:`app.routes.shared.get_or_create_local_user` guarantees
    # the local user has a Self row before any Account POST lands.
    # The migration upgrade path adds the column nullable, backfills
    # from the per-user Self row, then flips NOT NULL via
    # ``batch_alter_table`` (SQLite-safe).
    family_member_id = Column(
        Integer, ForeignKey("family_members.id"), nullable=False, index=True
    )
    plaid_id = Column(String, unique=True, nullable=True, index=True)
    account_name = Column(String, nullable=False)
    account_number = Column(String, nullable=True)  # masked
    account_type = Column(String, nullable=False)
    account_subtype = Column(String, nullable=True)
    current_balance = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    # Phase 40 — provenance. The ``server_default='manual'`` in the
    # alembic migration covers ALTER-time back-fill; the
    # model-level ``default='manual'`` covers ad-hoc ORM-row
    # construction (scripted seeding, tests). Route layer always
    # stamps ``source`` explicitly so the defaults are belt-and-
    # braces for non-route write paths only.
    source = Column(String(20), nullable=False, default="manual")
    # Phase 40 — free-text note. Auto-filled at every create-path
    # with a parser-aware diagnostic (see the route layer) and
    # editable via ``PUT /api/accounts/{id}`` from the Edit modal.
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_sync = Column(DateTime(timezone=True), nullable=True)
    # Debt fields — populated for liability accounts (credit_card, loan, mortgage).
    interest_rate = Column(Float, nullable=True)
    credit_limit = Column(Float, nullable=True)
    minimum_payment = Column(Float, nullable=True)
    term_months = Column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Account {self.account_name}>"
