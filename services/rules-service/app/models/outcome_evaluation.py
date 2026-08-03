"""Append-only evidence-based outcome evaluations for accepted recommendations."""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class OutcomeEvaluation(Base):
    """A separately recorded evaluation; it never asserts that acceptance executed."""

    __tablename__ = "outcome_evaluations"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key_hash", name="uq_outcome_evaluation_idempotency"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_outcome_evaluation_id_shape"),
        CheckConstraint("length(recommendation_id) = 36 AND recommendation_id = lower(recommendation_id)", name="ck_outcome_evaluation_recommendation_id_shape"),
        CheckConstraint("length(decision_journal_entry_id) = 36 AND decision_journal_entry_id = lower(decision_journal_entry_id)", name="ck_outcome_evaluation_decision_id_shape"),
        CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_outcome_evaluation_idempotency_hash"),
        CheckConstraint("lifecycle IN ('pending', 'not_yet_measurable', 'measured')", name="ck_outcome_evaluation_lifecycle"),
        CheckConstraint("currency = 'USD'", name="ck_outcome_evaluation_currency"),
        CheckConstraint("length(schema_version) BETWEEN 1 AND 64", name="ck_outcome_evaluation_schema_version"),
        CheckConstraint("measurement_window_start IS NULL OR measurement_window_end IS NULL OR measurement_window_start <= measurement_window_end", name="ck_outcome_evaluation_window_order"),
        CheckConstraint("(lifecycle = 'measured' AND authoritative_evidence_reference IS NOT NULL AND measurement_window_start IS NOT NULL AND measurement_window_end IS NOT NULL AND inputs_json IS NOT NULL AND result_json IS NOT NULL AND confidence IS NOT NULL AND explanation IS NOT NULL) OR (lifecycle IN ('pending', 'not_yet_measurable') AND authoritative_evidence_reference IS NULL AND measurement_window_start IS NULL AND measurement_window_end IS NULL AND inputs_json IS NULL AND result_json IS NULL AND confidence IS NULL AND explanation IS NULL)", name="ck_outcome_evaluation_lifecycle_evidence"),
    )

    id = Column(String(36), primary_key=True)
    recommendation_id = Column(String(36), ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision_journal_entry_id = Column(String(36), ForeignKey("decision_journal_entries.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    lifecycle = Column(String(32), nullable=False)
    schema_version = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")
    authoritative_evidence_reference = Column(String(512), nullable=True)
    measurement_window_start = Column(DateTime(timezone=True), nullable=True)
    measurement_window_end = Column(DateTime(timezone=True), nullable=True)
    inputs_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    confidence = Column(String(16), nullable=True)
    explanation = Column(String(2048), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
