"""INV-12 immutable durable stores (design gate §6b/§7b/§5b).

Three append-only tables designed by ``ATLAS-INVESTMENT-INV-12-DESIGN.md``:

- ``investment_market_observations`` — durable vintaged market observations.
  Owner-independent public security data (the single deliberate exception to
  owner scoping, justified in the design §15): provider-derived close/value
  facts are identical for every owner and both pre-existing observation
  contracts carry no ``owner_id``. Writes are server-internal only.
  ``observation_id`` is deterministic over the canonical payload, so an
  identical delivery collapses onto one row; a restated value or a later
  ``as_known_at`` vintage is a NEW row, never an UPDATE.
- ``investment_portfolio_snapshots`` — immutable payloads of the existing
  INV-03 ``PortfolioSnapshot/v1`` (single builder reused; this is not a second
  portfolio ledger). Owner-scoped because snapshots embed private holdings.
- ``investment_evaluation_records`` — the INV-12 evaluation artifact registry.
  Owner-scoped, references recommendation/decision/outcome rows by RESTRICT
  FK, and stores replay metadata + hashes; measured values stay in the
  existing ``investment_outcome_records`` payloads.

Immutability is enforced by ``BEFORE UPDATE``/``BEFORE DELETE`` triggers on
both SQLite and PostgreSQL (precedent ``T8a1b2c3d4e5``); downgrade of a
non-empty table is refused so history can never be silently destroyed.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class InvestmentMarketObservation(Base):
    __tablename__ = "investment_market_observations"
    __table_args__ = (
        UniqueConstraint("observation_id", name="uq_investment_market_observations_id"),
        CheckConstraint("length(observation_id) BETWEEN 1 AND 160", name="ck_investment_market_observations_id"),
        CheckConstraint("length(observation_hash) = 64 AND observation_hash = lower(observation_hash)", name="ck_investment_market_observations_hash"),
        CheckConstraint("length(security_id) BETWEEN 1 AND 128", name="ck_investment_market_observations_security"),
        CheckConstraint("currency = upper(currency) AND length(currency) = 3", name="ck_investment_market_observations_currency"),
        CheckConstraint("state IN ('unknown', 'missing', 'stale', 'estimated', 'observed')", name="ck_investment_market_observations_state"),
        CheckConstraint("freshness IN ('unknown', 'missing', 'stale', 'estimated', 'observed')", name="ck_investment_market_observations_freshness"),
        CheckConstraint("quality IN ('validated', 'partial', 'invalid')", name="ck_investment_market_observations_quality"),
        CheckConstraint("adjustment_basis IN ('unadjusted', 'split_adjusted', 'total_return_adjusted', 'unknown')", name="ck_investment_market_observations_basis"),
    )

    id = Column(Integer, primary_key=True)
    observation_id = Column(String(160), nullable=False)
    security_id = Column(String(128), nullable=False, index=True)
    observed_value = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False)
    adjustment_basis = Column(String(32), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    as_known_at = Column(DateTime(timezone=True), nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(String(160), nullable=False)
    source_identifier = Column(String(160), nullable=True)
    state = Column(String(16), nullable=False)
    quality = Column(String(16), nullable=False)
    freshness = Column(String(16), nullable=False)
    observation_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InvestmentPortfolioSnapshot(Base):
    __tablename__ = "investment_portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("owner_id", "snapshot_hash", name="uq_investment_portfolio_snapshots_owner_hash"),
        CheckConstraint("length(snapshot_id) BETWEEN 1 AND 160", name="ck_investment_portfolio_snapshots_id"),
        CheckConstraint("length(snapshot_hash) = 64 AND snapshot_hash = lower(snapshot_hash)", name="ck_investment_portfolio_snapshots_hash"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    snapshot_id = Column(String(160), nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InvestmentEvaluationRecord(Base):
    __tablename__ = "investment_evaluation_records"
    __table_args__ = (
        UniqueConstraint("owner_id", "evaluation_id", name="uq_investment_evaluations_owner_id"),
        CheckConstraint("evaluation_id LIKE 'investment-evaluation:%'", name="ck_investment_evaluations_id"),
        CheckConstraint("length(input_hash) = 64 AND input_hash = lower(input_hash)", name="ck_investment_evaluations_input_hash"),
        CheckConstraint("length(evaluation_hash) = 64 AND evaluation_hash = lower(evaluation_hash)", name="ck_investment_evaluations_hash"),
        CheckConstraint(
            "recommendation_hash IS NOT NULL AND length(recommendation_hash) = 64 AND recommendation_hash = lower(recommendation_hash)",
            name="ck_investment_evaluations_recommendation_hash",
        ),
        CheckConstraint(
            "outcome_hash IS NULL OR (length(outcome_hash) = 64 AND outcome_hash = lower(outcome_hash))",
            name="ck_investment_evaluations_outcome_hash",
        ),
        CheckConstraint("horizon IN ('1D', '1W', '1M', '3M', '6M', '1Y')", name="ck_investment_evaluations_horizon"),
        CheckConstraint("evaluation_state IN ('pending', 'evaluable', 'evaluated', 'blocked')", name="ck_investment_evaluations_state"),
        CheckConstraint(
            "result_state IS NULL OR result_state IN ('available', 'insufficient_history', 'unavailable', 'temporal_violation', 'not_comparable')",
            name="ck_investment_evaluations_result_state",
        ),
        CheckConstraint("replay_state IN ('match', 'methodology_changed', 'inputs_unavailable', 'hash_mismatch')", name="ck_investment_evaluations_replay"),
        CheckConstraint("evaluation_as_of >= evaluation_window_start", name="ck_investment_evaluations_window"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    evaluation_id = Column(String(160), nullable=False)
    recommendation_record_id = Column(Integer, ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_id = Column(String(160), nullable=False)
    recommendation_hash = Column(String(64), nullable=False)
    decision_record_id = Column(Integer, ForeignKey("investment_decision_records.id", ondelete="RESTRICT"), nullable=True)
    decision_id = Column(String(160), nullable=True)
    outcome_record_id = Column(Integer, ForeignKey("investment_outcome_records.id", ondelete="RESTRICT"), nullable=True)
    outcome_id = Column(String(160), nullable=True)
    outcome_hash = Column(String(64), nullable=True)
    security_id = Column(String(128), nullable=False, index=True)
    evaluation_window_start = Column(DateTime(timezone=True), nullable=False)
    evaluation_as_of = Column(DateTime(timezone=True), nullable=False)
    horizon = Column(String(8), nullable=False)
    benchmark_security_id = Column(String(128), nullable=True)
    evaluation_state = Column(String(16), nullable=False)
    result_state = Column(String(32), nullable=True)
    methodology_version = Column(String(64), nullable=False)
    vintage_bound = Column(DateTime(timezone=True), nullable=False)
    replay_state = Column(String(32), nullable=False)
    input_hash = Column(String(64), nullable=False)
    evaluation_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
