"""Immutable, user-scoped decision-journal model (Phase 2 Slice 1).

A ``DecisionJournalEntry`` row is the user's append-only response to a
``Recommendation``. The PK (``decision_id``) is deterministic from
canonical-JSON inputs that include the underlying recommendation, the
chosen ``decision_action`` (``accept`` / ``reject`` / ``defer``),
and the SHA-256 hash of the client-supplied ``Idempotency-Key``
header (the raw key is never persisted).

Idempotent-replay semantics:

* The ``UNIQUE (user_id, goal_id, recommendation_id, idempotency_key_hash)``
  constraint rejects a duplicate INSERT for the same client retry.
* The application layer reads the existing row when the PK collision
  occurs and emits the same response envelope, so the client sees an
  idempotent retry as a no-op walk to the prior decision.

Append-only: SQLite + PostgreSQL triggers reject ``UPDATE`` and
``DELETE`` on this table. Ownership triggers enforce
``entry.user_id == goal.user_id`` AND
``entry.user_id == recommendation.user_id`` -- a cross-user journal
write cannot be expressed even via direct SQL because the BEFORE
INSERT trigger rejects it.

Currency is fail-closed to ``"USD"``; the optional ``note`` is bounded
to 2048 chars; ``metadata_json`` is bounded-optional and never carries
raw snapshot, contribution, balance, or sourced financial values.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class DecisionJournalEntry(Base):
    """Append-only record of one user decision event on a recommendation."""

    __tablename__ = "decision_journal_entries"
    __table_args__ = (
        # Idempotent replay dedup: same client retry collapses onto a
        # single row via the UNIQUE constraint.
        UniqueConstraint(
            "user_id", "goal_id", "recommendation_id", "idempotency_key_hash",
            name="uq_decision_journal_idempotency",
        ),
        # Universal SQL constraints (cross-dialect safe).
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_decision_journal_id_shape"),
        CheckConstraint(
            "length(recommendation_id) = 36 AND recommendation_id = lower(recommendation_id)",
            name="ck_decision_journal_recommendation_id_shape",
        ),
        CheckConstraint(
            "length(idempotency_key_hash) = 64",
            name="ck_decision_journal_idempotency_hash_length",
        ),
        CheckConstraint(
            "idempotency_key_hash = lower(idempotency_key_hash)",
            name="ck_decision_journal_idempotency_hash_lower",
        ),
        CheckConstraint(
            "decision_action IN ('accept', 'reject', 'defer')",
            name="ck_decision_journal_action_enum",
        ),
        CheckConstraint(
            "length(schema_version) BETWEEN 1 AND 64",
            name="ck_decision_journal_schema_version_length",
        ),
        CheckConstraint("currency = 'USD'", name="ck_decision_journal_currency"),
        CheckConstraint(
            "note IS NULL OR length(note) <= 2048",
            name="ck_decision_journal_note_length",
        ),
    )

    # The PK column doubles as the canonical ``decision_id`` exposed on
    # the journal-entry response envelope.
    id = Column(String(36), primary_key=True)
    recommendation_id = Column(
        String(36), ForeignKey("recommendations.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision_action = Column(String(16), nullable=False)
    schema_version = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")
    note = Column(String(2048), nullable=True)
    metadata_json = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Symbolic type hints only -- not visible to SQLAlchemy at runtime.
    if False:
        decided_at: datetime
        created_at: datetime
        note: Optional[str]
