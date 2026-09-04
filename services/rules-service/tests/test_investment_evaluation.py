"""INV-12 engine + durable-store writers: vertical slice and failure modes.

Covers the design gate §21b minimal vertical slice and the §22 test strategy:
- store writers are idempotent (identical observation delivery collapses; the
  snapshot store accepts exactly one builder payload per hash);
- evaluation reuses ``evaluate_outcome()`` (no parallel engine) and persists
  measured values only through ``record_outcome()``;
- artifacts are deterministic and idempotent; conflicting windows produce
  distinct artifacts, never overwrites;
- replay returns ``match`` and detects vintage/methodology/hash drift;
- failure modes fail closed with typed blocked reasons (missing snapshot is
  never re-derived, currency/basis mismatch is never converted);
- owner isolation holds at the service boundary.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.investments.committee_adapters import FixtureCommitteeModel
from app.investments.committee_contracts import CommitteeContext, EvidenceCategory, EvidenceItem, EvidencePacket
from app.investments.committee_orchestrator import run_committee
from app.investments.contracts import EvidenceKind, EvidenceReference
from app.investments.evaluation_contracts import (
    EvaluationReplayState,
    EvaluationResultState,
    EvaluationState,
    StoredMarketObservation,
)
from app.investments.evaluation_service import BLOCKED_BASIS_MISMATCH, BLOCKED_CURRENCY_MISMATCH, BLOCKED_MISSING_OBSERVATION, BLOCKED_MISSING_SNAPSHOT, BLOCKED_TEMPORAL_VIOLATION, BLOCKED_WINDOW_NOT_CLOSED, EvaluationService, EvaluationServiceError
from app.investments.market_observations import AdjustmentBasis, ObservationQuality
from app.investments.outcome_tracking import HumanDecision, HumanDecisionRecord, OutcomeState
from app.investments.persistence_repository import InvestmentRepositoryError
from app.investments.persistence_service import InvestmentPersistenceService
from app.investments.portfolio_intelligence import build_portfolio_snapshot
from app.investments.recommendation_contracts import PositionState, RecommendationType, TimeHorizon
from app.investments.recommendation_gates import build_recommendation
from app.investments.contracts import DataState
from app.models import InvestmentEvaluationRecord, InvestmentMarketObservation, InvestmentOutcomeRecord, InvestmentPortfolioSnapshot
from app.routes.shared import get_or_create_local_user


@pytest.fixture
def domain_db():
    """Isolated per-test schema on the suite engine (drop/create)."""
    from app.database import Base, SessionLocal, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_recommendation(db, owner_id: int, *, security: str, portfolio_snapshot_hash: str, recommendation_as_of: datetime, status: str = "active"):
    now = recommendation_as_of
    evidence_as_of = now - timedelta(days=1)
    reference = EvidenceReference(evidence_id=f"market:inv12:{owner_id}", kind=EvidenceKind.SOURCE, source="fixture", content_hash="a" * 64, as_of=evidence_as_of, retrieved_at=now)
    item = EvidenceItem(evidence_id=f"market:inv12:{owner_id}", category=EvidenceCategory.MARKET, subject_security_id=security, owner_id=owner_id, reference=reference, numeric_value="100")
    packet = EvidencePacket.with_hash(packet_id=f"packet:inv12:{owner_id}", owner_id=owner_id, subject_security_id=security, analysis_as_of=evidence_as_of, items=(item,))
    committee_context = CommitteeContext.with_hash(run_id=f"run:inv12:{owner_id}", owner_id=owner_id, subject_security_id=security, analysis_as_of=packet.analysis_as_of, evidence_packet=packet, input_hashes=(packet.packet_hash,), portfolio_snapshot_hash=portfolio_snapshot_hash)
    finding_payload = {"claim": "Evidence supports the view.", "claim_class": "interpretation", "direction": "supports", "evidence_refs": (item.evidence_id,)}
    responses = {role: dict(finding_payload) for role in ("fundamental", "technical", "macro", "quant", "portfolio", "risk", "bull", "bear")} | {"chair": {"committee_view": "constructive", "thesis": "The evidence supports the thesis.", "supporting_evidence": (item.evidence_id,), "contradicting_evidence": (), "key_risks": (), "invalidation_conditions": ("Evidence changes.",)}}
    committee_run = run_committee(committee_context, FixtureCommitteeModel(responses), created_at=now)
    assert committee_run.chair_finding is not None
    recommendation_result = build_recommendation(
        owner_id=owner_id,
        committee_finding=committee_run.chair_finding,
        evidence_packet=packet,
        portfolio_snapshot_hash=portfolio_snapshot_hash,
        position_state=PositionState.NOT_HELD,
        requested_type=RecommendationType.BUY,
        time_horizon=TimeHorizon.MEDIUM_TERM,
        recommendation_as_of=now,
    )
    recommendation = recommendation_result.recommendation
    assert recommendation is not None, recommendation_result.failure_reason
    if status != "active":
        recommendation = recommendation.model_copy(update={"status": type(recommendation.status)(status)})
    service = InvestmentPersistenceService(db)
    service.persist_evidence_packet(packet)
    committee_run = committee_run.model_copy(update={"context_hash": packet.packet_hash, "run_hash": committee_run.run_hash})
    service.persist_committee_run(committee_run, evidence_packet=packet)
    service.persist_committee_finding(committee_run.chair_finding, run=committee_run, evidence_packet=packet)
    service.persist_recommendation(recommendation, committee_finding=committee_run.chair_finding, run=committee_run, evidence_packet=packet)
    return recommendation


def _observation(*, security: str, price: str, observed_at: datetime, as_known_at: datetime, currency: str = "USD", basis: AdjustmentBasis = AdjustmentBasis.SPLIT_ADJUSTED, source: str = "fixture-provider") -> StoredMarketObservation:
    return StoredMarketObservation.with_hash(
        security_id=security,
        observed_value=price,
        currency=currency,
        adjustment_basis=basis,
        observed_at=observed_at,
        as_known_at=as_known_at,
        retrieved_at=as_known_at,
        source=source,
        source_identifier=None,
        state=DataState.OBSERVED,
        quality=ObservationQuality.VALIDATED,
        freshness=DataState.OBSERVED,
    )


def _store_snapshot(db, owner_id: int, as_of: datetime):
    snapshot = build_portfolio_snapshot(owner_id=owner_id, accounts=[], holdings=[], as_of=as_of)
    EvaluationService(db).store_portfolio_snapshot(snapshot)
    return snapshot


def _seed_decision(db, owner_id: int, recommendation) -> str:
    decision = HumanDecisionRecord(
        decision_id="investment-decision:" + hashlib.sha256(f"{owner_id}|{recommendation.recommendation_id}|decision".encode()).hexdigest(),
        tracking_id="persisted:" + recommendation.recommendation_id,
        recommendation_id=recommendation.recommendation_id,
        recommendation_hash=recommendation.recommendation_hash,
        owner_id=owner_id,
        decision=HumanDecision.ACCEPT,
        decided_at=recommendation.created_at + timedelta(days=1),
        rationale=None,
    )
    key_hash = hashlib.sha256("inv12-decision-key".encode()).hexdigest()
    InvestmentPersistenceService(db).record_decision(decision, recommendation=recommendation, idempotency_key_hash=key_hash)
    return decision.decision_id


def _count(db, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)))


# ---------------------------------------------------------------------- #
# Minimal vertical slice (§21b)
# ---------------------------------------------------------------------- #

def test_vertical_slice_store_to_replay(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)

    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)

    # Durable observation store: vintaged rows, idempotent identical delivery.
    baseline_v1 = _observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2))
    baseline_v2 = _observation(security=security, price="101", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(minutes=1))
    evaluation_obs = _observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1))
    service = EvaluationService(db)
    for observation in (baseline_v1, baseline_v2, evaluation_obs):
        service.store_observation(observation)
        service.store_observation(observation)  # identical delivery collapses
    db.commit()
    assert _count(db, InvestmentMarketObservation) == 3
    assert _count(db, InvestmentPortfolioSnapshot) == 1

    # One frozen outcome + one evaluated artifact + deterministic replay.
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()
    assert run.created is True
    artifact = run.artifact
    assert artifact.evaluation_state is EvaluationState.EVALUATED
    assert artifact.result_state is EvaluationResultState.AVAILABLE
    assert artifact.blocked_reason is None
    assert run.outcome is not None and run.outcome.outcome_hash == artifact.outcome_hash
    assert run.outcome.state is OutcomeState.AVAILABLE
    assert _count(db, InvestmentOutcomeRecord) == 1
    assert _count(db, InvestmentEvaluationRecord) == 1
    assert artifact.input_hash in artifact.evaluation_id
    assert len(artifact.input_hash) == 64 and len(artifact.evaluation_hash) == 64

    # Replay (meaning D): reproduce the stored result -> match.
    replay = service.replay(owner_id=owner_id, evaluation_id=artifact.evaluation_id)
    assert replay.replay_state is EvaluationReplayState.MATCH
    assert replay.verified is True
    assert replay.evaluation_hash == artifact.evaluation_hash

    # Read projections (owner-scoped).
    loaded = service.get_evaluation(owner_id=owner_id, evaluation_id=artifact.evaluation_id)
    assert loaded is not None and loaded.evaluation_id == artifact.evaluation_id and loaded.evaluation_hash == artifact.evaluation_hash
    listed = service.list_evaluations(owner_id=owner_id)
    assert [item.evaluation_id for item in listed] == [artifact.evaluation_id]

    # Idempotency: identical inputs -> the same artifact, never a second row.
    again = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()
    assert again.created is False
    assert again.artifact.evaluation_id == artifact.evaluation_id
    assert _count(db, InvestmentEvaluationRecord) == 1

    # Conflicting window -> a distinct deterministic artifact, no overwrite.
    later = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of + timedelta(days=60), horizon="1M")
    db.commit()
    assert later.created is True
    assert later.artifact.evaluation_id != artifact.evaluation_id
    assert _count(db, InvestmentEvaluationRecord) == 2


def test_decision_linkage_is_recorded_and_validated(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    decision_id = _seed_decision(db, owner_id, recommendation)
    db.commit()

    service = EvaluationService(db)
    service.store_observation(_observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2)))
    service.store_observation(_observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1)))
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M", decision_id=decision_id)
    db.commit()
    assert run.created is True and run.artifact.decision_id == decision_id
    # Foreign / unmatched decision -> typed input error, nothing persisted.
    with pytest.raises(EvaluationServiceError):
        service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M", decision_id="investment-decision:" + "f" * 64)


# ---------------------------------------------------------------------- #
# Fail-closed failure modes (§18)
# ---------------------------------------------------------------------- #

def test_missing_snapshot_is_blocked_never_re_derived(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    # Recommendation persisted with a portfolio_snapshot_hash that has NO
    # stored payload (legacy-style linkage).
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash="b" * 64, recommendation_as_of=as_of)
    db.commit()
    service = EvaluationService(db)
    service.store_observation(_observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2)))
    service.store_observation(_observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1)))
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()
    assert run.created is True and run.artifact.evaluation_state is EvaluationState.BLOCKED
    assert run.artifact.blocked_reason == BLOCKED_MISSING_SNAPSHOT
    assert run.outcome is None and _count(db, InvestmentOutcomeRecord) == 0
    # Idempotent retry returns the same blocked artifact.
    again = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    assert again.created is False and again.artifact.evaluation_id == run.artifact.evaluation_id


def test_missing_observations_fail_closed(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=f"atlas-security:{owner_id}:acme", portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    db.commit()
    run = EvaluationService(db).evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()
    assert run.artifact.evaluation_state is EvaluationState.BLOCKED
    assert run.artifact.blocked_reason == BLOCKED_MISSING_OBSERVATION
    assert run.artifact.result_state is EvaluationResultState.INSUFFICIENT_HISTORY
    assert _count(db, InvestmentOutcomeRecord) == 0


def test_window_not_closed_and_temporal_violation_are_blocked(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    db.commit()
    service = EvaluationService(db)
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=as_of + timedelta(days=10), horizon="1M")
    db.commit()
    assert run.artifact.evaluation_state is EvaluationState.BLOCKED and run.artifact.blocked_reason == BLOCKED_WINDOW_NOT_CLOSED
    # An evaluation point before the baseline is an invalid request, not a
    # measurement: fail closed with a typed error, nothing persisted.
    with pytest.raises(EvaluationServiceError) as excinfo:
        service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=as_of - timedelta(days=1), horizon="1M")
    assert BLOCKED_TEMPORAL_VIOLATION in str(excinfo.value)
    assert _count(db, InvestmentEvaluationRecord) == 1


def test_currency_and_basis_mismatch_are_not_comparable(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    db.commit()
    service = EvaluationService(db)

    # Currency mismatch (USD baseline vs EUR evaluation) -> not_comparable.
    service.store_observation(_observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2), currency="USD"))
    service.store_observation(_observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1), currency="EUR"))
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()
    assert run.artifact.evaluation_state is EvaluationState.BLOCKED
    assert run.artifact.blocked_reason == BLOCKED_CURRENCY_MISMATCH
    assert run.artifact.result_state is EvaluationResultState.NOT_COMPARABLE
    assert _count(db, InvestmentOutcomeRecord) == 0

    # Adjustment-basis mismatch at a NEW evaluation point (distinct inputs ->
    # a distinct artifact; the earlier currency artifact is never rewritten).
    db.query(InvestmentMarketObservation).delete()
    db.commit()
    basis_as_of = evaluation_as_of + timedelta(days=1)
    service.store_observation(_observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2), basis=AdjustmentBasis.SPLIT_ADJUSTED))
    service.store_observation(_observation(security=security, price="110", observed_at=basis_as_of - timedelta(hours=1), as_known_at=basis_as_of - timedelta(hours=1), basis=AdjustmentBasis.UNADJUSTED))
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=basis_as_of, horizon="1M")
    db.commit()
    assert run.artifact.evaluation_state is EvaluationState.BLOCKED
    assert run.artifact.blocked_reason == BLOCKED_BASIS_MISMATCH
    assert run.artifact.result_state is EvaluationResultState.NOT_COMPARABLE


def test_zero_baseline_price_is_unavailable_not_fabricated(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    db.commit()
    service = EvaluationService(db)
    service.store_observation(_observation(security=security, price="0", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2)))
    service.store_observation(_observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1)))
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()
    assert run.created is True
    assert run.artifact.evaluation_state is EvaluationState.EVALUATED
    assert run.artifact.result_state is EvaluationResultState.UNAVAILABLE
    assert run.outcome is not None and run.outcome.state is OutcomeState.UNAVAILABLE
    assert run.outcome.reference_price is None and run.outcome.simple_return is None


# ---------------------------------------------------------------------- #
# Replay semantics: vintage, methodology, tamper
# ---------------------------------------------------------------------- #

def test_later_restatement_never_rewrites_an_earlier_artifact(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    db.commit()
    service = EvaluationService(db)
    service.store_observation(_observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2)))
    service.store_observation(_observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1)))
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()
    original_id = run.artifact.evaluation_id

    # Provider restates the evaluation-day value AFTER the original vintage
    # bound. The new vintage (as_known_at after the bound) is a NEW row and is
    # invisible to the original artifact: replay still matches.
    service.store_observation(_observation(security=security, price="115", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of + timedelta(minutes=1)))
    db.commit()
    assert _count(db, InvestmentMarketObservation) == 3
    replay = service.replay(owner_id=owner_id, evaluation_id=original_id)
    assert replay.replay_state is EvaluationReplayState.MATCH and replay.verified is True

    # A NEW evaluation with a later vintage bound uses the restated vintage
    # (distinct deterministic artifact, never an overwrite).
    later_as_of = evaluation_as_of + timedelta(days=2)
    later = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=later_as_of, horizon="1M")
    db.commit()
    assert later.created is True and later.artifact.evaluation_id != original_id
    assert later.artifact.evaluation_state is EvaluationState.EVALUATED
    assert later.outcome is not None and later.outcome.evaluation_price == "115"


def test_replay_detects_tampering_and_reports_hash_mismatch(domain_db):
    db = domain_db
    owner = get_or_create_local_user(db, "alex")
    db.commit()
    owner_id = owner.id
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = _store_snapshot(db, owner_id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    db.commit()
    service = EvaluationService(db)
    service.store_observation(_observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2)))
    service.store_observation(_observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1)))
    run = service.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()

    row = db.scalar(select(InvestmentEvaluationRecord).where(InvestmentEvaluationRecord.evaluation_id == run.artifact.evaluation_id))
    payload = json.loads(row.payload_json)
    payload["horizon"] = "1W"
    row.payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    db.commit()

    # Strict read fails closed; replay reports the drift without side effects.
    with pytest.raises(InvestmentRepositoryError):
        service.get_evaluation(owner_id=owner_id, evaluation_id=run.artifact.evaluation_id)
    replay = service.replay(owner_id=owner_id, evaluation_id=run.artifact.evaluation_id)
    assert replay.replay_state is EvaluationReplayState.HASH_MISMATCH
    assert replay.verified is False
    assert _count(db, InvestmentEvaluationRecord) == 1


# ---------------------------------------------------------------------- #
# Owner isolation
# ---------------------------------------------------------------------- #

def test_service_reads_are_owner_scoped(domain_db):
    db = domain_db
    owner_a = get_or_create_local_user(db, "alex")
    owner_b = get_or_create_local_user(db, "owner-b")
    db.commit()
    security = f"atlas-security:{owner_a.id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = _store_snapshot(db, owner_a.id, as_of=as_of)
    recommendation = _seed_recommendation(db, owner_a.id, security=security, portfolio_snapshot_hash=snapshot.snapshot_hash, recommendation_as_of=as_of)
    db.commit()
    service = EvaluationService(db)
    service.store_observation(_observation(security=security, price="100", observed_at=as_of - timedelta(hours=2), as_known_at=as_of - timedelta(hours=2)))
    service.store_observation(_observation(security=security, price="110", observed_at=evaluation_as_of - timedelta(hours=1), as_known_at=evaluation_as_of - timedelta(hours=1)))
    run = service.evaluate(owner_id=owner_a.id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    db.commit()

    assert service.get_evaluation(owner_id=owner_b.id, evaluation_id=run.artifact.evaluation_id) is None
    assert service.list_evaluations(owner_id=owner_b.id) == []
    with pytest.raises(EvaluationServiceError):
        service.replay(owner_id=owner_b.id, evaluation_id=run.artifact.evaluation_id)
    # Owner B cannot read A's snapshot payload either.
    assert db.scalar(select(func.count()).select_from(InvestmentPortfolioSnapshot).where(InvestmentPortfolioSnapshot.owner_id == owner_b.id)) == 0
