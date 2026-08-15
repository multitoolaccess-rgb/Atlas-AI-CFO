"""Append-only exact-cent authority for account balances."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class AccountBalanceEvidence(Base):
    """Server-read Decimal balance evidence; never a mutable account cache."""

    __tablename__ = "account_balance_evidence"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_type = Column(String(16), nullable=False)
    source_kind = Column(String(32), nullable=False)
    actor_category = Column(String(32), nullable=False)
    currency_code = Column(String(3), nullable=False)
    amount = Column(Numeric(38, 2, asdecimal=True), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    supersedes_event_id = Column(String(36), ForeignKey("account_balance_evidence.id", ondelete="RESTRICT"), nullable=True)
    precondition_hash = Column(String(64), nullable=False)
    state_hash = Column(String(64), nullable=False)
    observation_intent_hash = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key_hash", name="uq_account_balance_evidence_idempotency"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_account_balance_evidence_id_shape"),
        CheckConstraint("event_type IN ('assertion', 'revocation')", name="ck_account_balance_evidence_event_type"),
        CheckConstraint("source_kind = 'operator_confirmed'", name="ck_account_balance_evidence_source_kind"),
        CheckConstraint("actor_category = 'local_operator'", name="ck_account_balance_evidence_actor_category"),
        CheckConstraint("currency_code = 'USD'", name="ck_account_balance_evidence_currency"),
        CheckConstraint("(event_type = 'assertion' AND amount IS NOT NULL) OR (event_type = 'revocation' AND amount IS NULL)", name="ck_account_balance_evidence_amount_event"),
        CheckConstraint("length(precondition_hash) = 64 AND precondition_hash = lower(precondition_hash)", name="ck_account_balance_evidence_precondition_hash"),
        CheckConstraint("length(state_hash) = 64 AND state_hash = lower(state_hash)", name="ck_account_balance_evidence_state_hash"),
        CheckConstraint("length(observation_intent_hash) = 64 AND observation_intent_hash = lower(observation_intent_hash)", name="ck_account_balance_evidence_intent_hash"),
        CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_account_balance_evidence_idempotency_hash"),
    )
