"""Immutable, user-scoped recommendation derivation model (Phase 2 Slice 1).

A ``Recommendation`` row is appended once per
``(user_id, goal_id, forecast_version_id, recommendation_kind)`` tuple.
The PK is deterministic from canonical-JSON inputs (see
:mod:`app.models.decision_journal_identities`); replays against the same
canonical inputs collapse onto the same row via the UNIQUE constraint.

Currency is fail-closed to ``"USD"``; immutable linkage to the source
``forecast_versions`` row is preserved via ``forecast_version_id`` and the
redundant ``forecast_input_state_hash`` column (a hash-only linkage
that does not need a JOIN to verify hash-equality).

Append-only: SQLite + PostgreSQL triggers reject ``UPDATE`` and
``DELETE`` on this table (see the additive Alembic migration
``T8a1b2c3d4e5_add_decision_journal_substrate.py``).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func

from app.database import Base


class Recommendation(Base):
    """Append-only record of one deterministic recommendation derivation."""

    __tablename__ = "recommendations"
    __table_args__ = (
        # Identity: same user+goal+forecast_version+kind+rule_version must
        # collapse to a single row. ``rule_version`` is part of the
        # identity because the deterministic PK includes it -- a future
        # rule-version bump produces a NEW recommendation rather than
        # overwriting the prior derivation. Cross-user is impossible
        # because the FK into ``goals`` (RESTRICT) plus the
        # ``recommendations_goal_owner`` ownership trigger enforce
        # user_id == goals.user_id.
        UniqueConstraint(
            "user_id", "goal_id", "forecast_version_id", "recommendation_kind", "rule_version",
            name="uq_recommendations_identity",
        ),
        # Universal SQL constraints (cross-dialect safe).
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_recommendations_id_shape"),
        CheckConstraint(
            "length(forecast_version_id) = 36 AND forecast_version_id = lower(forecast_version_id)",
            name="ck_recommendations_forecast_version_id_shape",
        ),
        CheckConstraint(
            "length(forecast_input_state_hash) = 64",
            name="ck_recommendations_input_state_hash_length",
        ),
        CheckConstraint(
            "forecast_input_state_hash = lower(forecast_input_state_hash)",
            name="ck_recommendations_input_state_hash_lower",
        ),
        CheckConstraint(
            "length(recommendation_kind) BETWEEN 2 AND 64",
            name="ck_recommendations_recommendation_kind_length",
        ),
        CheckConstraint(
            "length(rule_version) BETWEEN 1 AND 64",
            name="ck_recommendations_rule_version_length",
        ),
        CheckConstraint(
            "length(derivation_schema_version) BETWEEN 1 AND 64",
            name="ck_recommendations_schema_version_length",
        ),
        CheckConstraint("currency = 'USD'", name="ck_recommendations_currency"),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_recommendations_confidence_range",
        ),
        CheckConstraint(
            "expected_impact_min_decimal <= expected_impact_max_decimal",
            name="ck_recommendations_impact_ordering",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 1 AND 1024",
            name="ck_recommendations_reason_length",
        ),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    forecast_version_id = Column(
        String(36), ForeignKey("forecast_versions.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    forecast_input_state_hash = Column(String(64), nullable=False)
    recommendation_kind = Column(String(64), nullable=False)
    rule_version = Column(String(64), nullable=False)
    derivation_schema_version = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")
    reason = Column(String(1024), nullable=False)
    expected_impact_min_decimal = Column(Numeric(38, 12, asdecimal=True), nullable=False)
    expected_impact_max_decimal = Column(Numeric(38, 12, asdecimal=True), nullable=False)
    confidence_score = Column(Numeric(5, 4, asdecimal=True), nullable=False)
    assumptions_json = Column(Text, nullable=False, default="{}", server_default="{}")
    risks_json = Column(Text, nullable=False, default="{}", server_default="{}")
    freshness_json = Column(Text, nullable=False, default="{}", server_default="{}")
    provenance_json = Column(Text, nullable=False, default="{}", server_default="{}")
    metadata_json = Column(Text, nullable=True)
    derived_at = Column(DateTime(timezone=True), nullable=False)
    data_as_of = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Decimal defaults wired as plain ``Decimal`` in the application
    # layer; the CHECK constraint enforces range on every row, including
    # server-default default values via the comparison.

    # ``expected_impact_min_decimal`` and ``expected_impact_max_decimal``
    # are typed as ``Decimal`` so the application can pass canonical
    # string words like ``Decimal("123.45")`` without losing precision;
    # see :mod:`app.forecasts.canonical_state` for canonical-decimal
    # conversion rules.
    if False:  # type-only directive: keep ``__all__`` discoverable via inspect
        expected_impact_min_decimal: Decimal
        expected_impact_max_decimal: Decimal
        confidence_score: Decimal
