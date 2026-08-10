"""Immutable Phase 4 decision-history and audit records.

These records add context to the Phase 2 decision ledger; they never amend a
decision, recommendation, or outcome.  A correction is a new history row that
references the row it supersedes.  Only idempotency digests are stored.
"""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class DecisionHistoryEntry(Base):
    __tablename__ = "decision_history_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "recommendation_id", "decision_journal_entry_id", "idempotency_key_hash", name="uq_decision_history_idempotency"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_decision_history_id_shape"),
        CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_decision_history_idempotency_hash"),
        CheckConstraint("decision_action IN ('accept', 'reject', 'defer')", name="ck_decision_history_action"),
        CheckConstraint("length(schema_version) BETWEEN 1 AND 64", name="ck_decision_history_schema"),
        CheckConstraint("currency = 'USD'", name="ck_decision_history_currency"),
        CheckConstraint("length(rationale) BETWEEN 1 AND 2048", name="ck_decision_history_rationale"),
        CheckConstraint("length(alternatives_json) BETWEEN 2 AND 4096", name="ck_decision_history_alternatives"),
    )
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_id = Column(String(36), ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision_journal_entry_id = Column(String(36), ForeignKey("decision_journal_entries.id", ondelete="RESTRICT"), nullable=False, index=True)
    supersedes_history_entry_id = Column(String(36), ForeignKey("decision_history_entries.id", ondelete="RESTRICT"), nullable=True, index=True)
    decision_action = Column(String(16), nullable=False)
    alternatives_json = Column(Text, nullable=False)
    rationale = Column(String(2048), nullable=False)
    schema_version = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False, server_default="USD")
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DecisionAuditEvent(Base):
    __tablename__ = "decision_audit_events"
    __table_args__ = (
        UniqueConstraint("history_entry_id", "event_action", name="uq_decision_audit_history_action"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_decision_audit_id_shape"),
        CheckConstraint("event_action IN ('recorded', 'corrected', 'evaluated')", name="ck_decision_audit_action"),
        CheckConstraint("(event_action = 'evaluated' AND outcome_evaluation_id IS NOT NULL) OR (event_action IN ('recorded', 'corrected') AND outcome_evaluation_id IS NULL)", name="ck_decision_audit_outcome_semantics"),
        CheckConstraint("policy_result = 'recorded'", name="ck_decision_audit_policy"),
        CheckConstraint("actor_scope = 'owner'", name="ck_decision_audit_actor_scope"),
        CheckConstraint("length(correlation_hash) = 64 AND correlation_hash = lower(correlation_hash)", name="ck_decision_audit_correlation_hash"),
    )
    id = Column(String(36), primary_key=True)
    history_entry_id = Column(String(36), ForeignKey("decision_history_entries.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_id = Column(String(36), ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision_journal_entry_id = Column(String(36), ForeignKey("decision_journal_entries.id", ondelete="RESTRICT"), nullable=False, index=True)
    outcome_evaluation_id = Column(String(36), ForeignKey("outcome_evaluations.id", ondelete="RESTRICT"), nullable=True, index=True)
    event_action = Column(String(16), nullable=False)
    actor_scope = Column(String(16), nullable=False, server_default="owner")
    correlation_hash = Column(String(64), nullable=False)
    policy_result = Column(String(16), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
