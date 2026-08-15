"""Append-only, owner-scoped account-currency evidence events.

The account currency columns remain a compatibility projection for older
surfaces.  New authority is derived from this immutable event table only.
"""
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class AccountCurrencyEvidence(Base):
    __tablename__ = "account_currency_evidence"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_type = Column(String(16), nullable=False)
    source_kind = Column(String(32), nullable=False)
    currency_code = Column(String(3), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor_category = Column(String(32), nullable=False)
    source_reference_hash = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    supersedes_event_id = Column(String(36), ForeignKey("account_currency_evidence.id", ondelete="RESTRICT"), nullable=True)
    reason_code = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key_hash", name="uq_account_currency_evidence_idempotency"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_account_currency_evidence_id_shape"),
        CheckConstraint("event_type IN ('assertion', 'correction', 'revocation')", name="ck_account_currency_evidence_event_type"),
        CheckConstraint("source_kind IN ('structured_provider', 'structured_statement', 'operator_confirmed', 'correction', 'revocation')", name="ck_account_currency_evidence_source_kind"),
        CheckConstraint("(event_type = 'revocation' AND source_kind = 'revocation' AND currency_code IS NULL) OR (event_type = 'assertion' AND source_kind NOT IN ('correction', 'revocation') AND currency_code IS NOT NULL AND currency_code = upper(currency_code) AND length(currency_code) = 3) OR (event_type = 'correction' AND source_kind = 'correction' AND currency_code IS NOT NULL AND currency_code = upper(currency_code) AND length(currency_code) = 3)", name="ck_account_currency_evidence_currency_shape"),
        CheckConstraint("length(actor_category) BETWEEN 1 AND 32", name="ck_account_currency_evidence_actor_shape"),
        CheckConstraint("length(source_reference_hash) = 64 AND source_reference_hash = lower(source_reference_hash)", name="ck_account_currency_evidence_source_hash"),
        CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_account_currency_evidence_idempotency_hash"),
        CheckConstraint("supersedes_event_id IS NULL OR (length(supersedes_event_id) = 36 AND supersedes_event_id = lower(supersedes_event_id))", name="ck_account_currency_evidence_supersedes_shape"),
        CheckConstraint("reason_code IS NULL OR length(reason_code) BETWEEN 1 AND 64", name="ck_account_currency_evidence_reason_shape"),
    )
