"""Immutable, append-only outcome evaluation model (Phase 3 Slice 1).

An ``OutcomeEvaluation`` row is a separately recorded evaluation of a
recommendation's actual impact after an accepted decision. It never asserts
that the acceptance caused execution; it records what was measured.

Lifecycle states:

* ``pending`` — evaluation is scheduled but not yet started.
* ``not_yet_measurable`` — measurement window has not closed.
* ``measured`` — evaluation completed with bounded evidence.

Privacy contract:

* ``evidence_source_kind`` is a strict allowlisted enum (no free-form input).
* ``evidence_reference_hash`` is the only evidence pointer, and it is a
  hash-only opaque reference (no raw URLs, filenames, account IDs, or
  transaction identifiers).
* ``result_json`` / ``explanation`` carry the measured outcome data and
  its human explanation (size-bounded, not content-scrubbed); they are
  the outcome itself, never evidence references.
* Raw evidence references are NEVER persisted, logged, or included in
  validation errors.

Append-only: SQLite + PostgreSQL triggers reject ``UPDATE`` and ``DELETE``
on this table.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func

from app.database import Base


class OutcomeEvaluation(Base):
    """Append-only record of one outcome evaluation for an accepted decision."""

    __tablename__ = "outcome_evaluations"
    __table_args__ = (
        # Idempotent replay dedup: same user+recommendation+decision+idempotency
        # collapses to a single row.
        UniqueConstraint(
            "user_id", "recommendation_id", "decision_journal_entry_id", "idempotency_key_hash",
            name="uq_outcome_evaluation_idempotency",
        ),
        # Universal SQL constraints (cross-dialect safe).
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_outcome_evaluation_id_shape"),
        CheckConstraint(
            "length(recommendation_id) = 36 AND recommendation_id = lower(recommendation_id)",
            name="ck_outcome_evaluation_recommendation_id_shape",
        ),
        CheckConstraint(
            "length(decision_journal_entry_id) = 36 AND decision_journal_entry_id = lower(decision_journal_entry_id)",
            name="ck_outcome_evaluation_decision_id_shape",
        ),
        CheckConstraint(
            "length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)",
            name="ck_outcome_evaluation_idempotency_hash",
        ),
        CheckConstraint(
            "lifecycle IN ('pending', 'not_yet_measurable', 'measured')",
            name="ck_outcome_evaluation_lifecycle",
        ),
        CheckConstraint(
            "evidence_source_kind IS NULL OR evidence_source_kind IN ('forecast_projection', 'account_balance_delta', 'transaction_pattern')",
            name="ck_outcome_evaluation_evidence_source_kind",
        ),
        CheckConstraint(
            "evidence_reference_hash IS NULL OR (length(evidence_reference_hash) = 64 AND evidence_reference_hash = lower(evidence_reference_hash))",
            name="ck_outcome_evaluation_evidence_reference_hash",
        ),
        CheckConstraint("currency = 'USD'", name="ck_outcome_evaluation_currency"),
        CheckConstraint(
            "length(schema_version) BETWEEN 1 AND 64",
            name="ck_outcome_evaluation_schema_version_length",
        ),
        CheckConstraint(
            "measurement_window_start IS NULL OR measurement_window_end IS NULL OR measurement_window_start <= measurement_window_end",
            name="ck_outcome_evaluation_window_order",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'medium', 'low')",
            name="ck_outcome_evaluation_confidence_enum",
        ),
        CheckConstraint(
            "explanation IS NULL OR length(explanation) <= 2048",
            name="ck_outcome_evaluation_explanation_length",
        ),
        # Lifecycle-state evidence contract: measured requires all evidence fields,
        # pending/not_yet_measurable forbids them.
        CheckConstraint(
            "(lifecycle = 'measured' AND evidence_source_kind IS NOT NULL AND evidence_reference_hash IS NOT NULL AND measurement_window_start IS NOT NULL AND measurement_window_end IS NOT NULL AND result_json IS NOT NULL AND confidence IS NOT NULL AND explanation IS NOT NULL) OR (lifecycle IN ('pending', 'not_yet_measurable') AND evidence_source_kind IS NULL AND evidence_reference_hash IS NULL AND measurement_window_start IS NULL AND measurement_window_end IS NULL AND result_json IS NULL AND confidence IS NULL AND explanation IS NULL)",
            name="ck_outcome_evaluation_lifecycle_evidence",
        ),
    )

    id = Column(String(36), primary_key=True)
    recommendation_id = Column(
        String(36), ForeignKey("recommendations.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    decision_journal_entry_id = Column(
        String(36), ForeignKey("decision_journal_entries.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    lifecycle = Column(String(32), nullable=False)
    schema_version = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")

    # Bounded evidence metadata (hash-only, allowlisted source kind).
    evidence_source_kind = Column(String(64), nullable=True)
    evidence_reference_hash = Column(String(64), nullable=True)

    measurement_window_start = Column(DateTime(timezone=True), nullable=True)
    measurement_window_end = Column(DateTime(timezone=True), nullable=True)
    result_json = Column(Text, nullable=True)
    confidence = Column(String(16), nullable=True)
    explanation = Column(String(2048), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Symbolic type hints only.
    if False:
        recorded_at: datetime
        created_at: datetime
        measurement_window_start: Optional[datetime]
        measurement_window_end: Optional[datetime]
        explanation: Optional[str]
