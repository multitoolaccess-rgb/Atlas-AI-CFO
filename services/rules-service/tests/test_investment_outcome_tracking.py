from datetime import UTC, datetime, timedelta

import pytest

from app.investments.outcome_tracking import (
    HumanDecision, MarketObservation, OutcomeState, ThesisStatus, TrackingStatus,
    evaluate_outcome, record_decision, supersede, track_recommendation, update_status,
)
from app.investments.recommendation_contracts import PositionState, RecommendationType, TimeHorizon
from app.investments.recommendation_gates import build_recommendation
from app.investments.committee_contracts import CommitteeContext, EvidenceCategory, EvidenceItem, EvidencePacket
from app.investments.committee_adapters import FixtureCommitteeModel
from app.investments.committee_orchestrator import run_committee
from app.investments.contracts import EvidenceKind, EvidenceReference

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)
SECURITY = "sec:tracked"
BENCHMARK = "sec:benchmark"

def ref(eid):
    return EvidenceReference(evidence_id=eid, kind=EvidenceKind.SOURCE, source="fixture", content_hash="a" * 64, as_of=NOW - timedelta(days=1), retrieved_at=NOW)

def recommendation():
    analysis_as_of = NOW - timedelta(days=7)
    item = EvidenceItem(evidence_id="market:evidence", category=EvidenceCategory.MARKET, subject_security_id=SECURITY, owner_id=7, reference=ref("market:evidence").model_copy(update={"as_of": analysis_as_of - timedelta(days=1), "retrieved_at": analysis_as_of}), numeric_value="100")
    packet = EvidencePacket.with_hash(packet_id="packet:tracked", owner_id=7, subject_security_id=SECURITY, analysis_as_of=analysis_as_of, items=(item,))
    context = CommitteeContext.with_hash(run_id="run:tracked", owner_id=7, subject_security_id=SECURITY, analysis_as_of=analysis_as_of, evidence_packet=packet, input_hashes=(packet.packet_hash,), portfolio_snapshot_hash="b" * 64)
    finding = {"claim": "Evidence supports the view.", "claim_class": "interpretation", "direction": "supports", "evidence_refs": ("market:evidence",)}
    responses = {role: dict(finding) for role in ("fundamental", "technical", "macro", "quant", "portfolio", "risk", "bull", "bear")} | {"chair": {"committee_view": "constructive", "thesis": "The evidence supports the thesis.", "supporting_evidence": ("market:evidence",), "contradicting_evidence": (), "key_risks": (), "invalidation_conditions": ("Evidence changes.",)}}
    run = run_committee(context, FixtureCommitteeModel(responses), created_at=NOW)
    return build_recommendation(owner_id=7, committee_finding=run.chair_finding, evidence_packet=packet, portfolio_snapshot_hash="b" * 64, position_state=PositionState.NOT_HELD, requested_type=RecommendationType.BUY, time_horizon=TimeHorizon.MEDIUM_TERM, recommendation_as_of=NOW - timedelta(days=7)).recommendation, packet.packet_hash

def obs(h, security, price, when, known=None):
    return MarketObservation(observation_hash=h * 64, security_id=security, price=str(price), observed_at=when, as_known_at=known or when, state="observed")

def test_tracking_and_decision_preserve_original_hash():
    rec, packet_hash = recommendation()
    tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    decision = record_decision(tracked, owner_id=7, decision=HumanDecision.ACCEPT, decided_at=NOW)
    assert tracked.recommendation_hash == rec.recommendation_hash
    assert decision.recommendation_hash == rec.recommendation_hash
    assert decision.decision is HumanDecision.ACCEPT
    with pytest.raises(ValueError):
        record_decision(tracked, owner_id=8, decision=HumanDecision.ACCEPT, decided_at=NOW)

def test_outcome_uses_point_in_time_baseline_and_is_reproducible():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    t0 = NOW - timedelta(days=10); t1 = NOW
    observations = (obs("a", SECURITY, 100, t0), obs("b", SECURITY, 110, NOW - timedelta(days=8)), obs("c", SECURITY, 120, t1), obs("d", SECURITY, 999, t1 + timedelta(days=1)))
    first = evaluate_outcome(tracked, evaluation_as_of=t1, observations=observations, horizon="1W")
    second = evaluate_outcome(tracked, evaluation_as_of=t1, observations=tuple(reversed(observations)), horizon="1W")
    assert first.outcome.simple_return == "0.090909090909090909090909091"
    assert first.outcome.baseline_observation_hash == "b" * 64
    assert first.outcome.evaluation_observation_hash == second.outcome.evaluation_observation_hash
    assert first.outcome.outcome_hash == second.outcome.outcome_hash
    assert first.outcome.thesis_status is ThesisStatus.SUPPORTED

def test_exact_timestamp_match_is_eligible_for_baseline():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    exact_time = tracked.as_of
    exact = evaluate_outcome(tracked, evaluation_as_of=NOW, observations=(obs("a", SECURITY, 100, exact_time), obs("b", SECURITY, 110, NOW)), horizon="1D")
    assert exact.outcome.baseline_observation_hash == "a" * 64
    assert exact.outcome.evaluation_observation_hash == "b" * 64


def test_no_historical_observation_returns_insufficient_baseline():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    future = obs("a", SECURITY, 100, NOW + timedelta(days=1))
    result = evaluate_outcome(tracked, evaluation_as_of=NOW + timedelta(days=2), observations=(future,), horizon="1D")
    assert result.outcome.state is OutcomeState.INSUFFICIENT_HISTORY
    assert result.outcome.baseline_observation_hash is None


def test_duplicate_timestamps_use_canonical_hash_tiebreaker():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    when = tracked.as_of
    observations = (obs("b", SECURITY, 110, when), obs("a", SECURITY, 100, when), obs("c", SECURITY, 120, NOW))
    first = evaluate_outcome(tracked, evaluation_as_of=NOW, observations=observations, horizon="1D")
    second = evaluate_outcome(tracked, evaluation_as_of=NOW, observations=tuple(reversed(observations)), horizon="1D")
    assert first.outcome.baseline_observation_hash == "b" * 64
    assert first.outcome.outcome_hash == second.outcome.outcome_hash


def test_benchmark_and_excess_return_are_separate_from_identity():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    t0 = tracked.as_of
    result = evaluate_outcome(tracked, evaluation_as_of=NOW, observations=(obs("a", SECURITY, 100, t0), obs("b", SECURITY, 110, NOW)), horizon="1M", benchmark_security_id=BENCHMARK, benchmark_observations=(obs("c", BENCHMARK, 200, t0), obs("d", BENCHMARK, 205, NOW)))
    assert result.outcome.benchmark_security_id == BENCHMARK
    assert result.outcome.benchmark_return == "0.025"
    assert result.outcome.excess_return == "0.075"
    assert result.outcome.benchmark_baseline_observation_hash == "c" * 64

def test_missing_and_zero_baseline_fail_closed():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    assert evaluate_outcome(tracked, evaluation_as_of=NOW, observations=(), horizon="1D").outcome.state is OutcomeState.INSUFFICIENT_HISTORY
    t0 = tracked.as_of
    zero = evaluate_outcome(tracked, evaluation_as_of=NOW, observations=(obs("a", SECURITY, 0, t0), obs("b", SECURITY, 1, NOW)), horizon="1D")
    assert zero.outcome.state is OutcomeState.UNAVAILABLE

def test_future_evaluation_and_future_observations_are_rejected_or_excluded():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    with pytest.raises(ValueError):
        evaluate_outcome(tracked, evaluation_as_of=tracked.as_of - timedelta(seconds=1), observations=(), horizon="1D")
    t0 = tracked.as_of
    result = evaluate_outcome(tracked, evaluation_as_of=NOW, observations=(obs("a", SECURITY, 100, t0), obs("b", SECURITY, 110, NOW + timedelta(days=1))), horizon="1D")
    assert result.outcome.state is OutcomeState.AVAILABLE
    assert result.outcome.evaluation_observation_hash == "a" * 64
    assert "b" * 64 not in result.outcome.source_observation_hashes

def test_supersession_and_status_are_immutable_projections():
    rec, packet_hash = recommendation(); old = track_recommendation(rec, evidence_packet_hash=packet_hash)
    newer_rec = rec.model_copy(update={"recommendation_id": "investment-recommendation:newer", "created_at": NOW + timedelta(days=1)})
    new = track_recommendation(newer_rec, evidence_packet_hash=packet_hash)
    superseded, successor = supersede(old, new, owner_id=7)
    assert superseded.status is TrackingStatus.SUPERSEDED
    assert old.status is TrackingStatus.OPEN
    assert successor.tracking_id == new.tracking_id
    with pytest.raises(ValueError):
        supersede(old, old, owner_id=7)
    assert update_status(old, at=old.review_at).status is TrackingStatus.REVIEWED

def test_action_semantics_are_not_sign_only_for_watch():
    rec, packet_hash = recommendation(); tracked = track_recommendation(rec, evidence_packet_hash=packet_hash)
    outcome = evaluate_outcome(tracked, evaluation_as_of=NOW, observations=(obs("a", SECURITY, 100, tracked.as_of), obs("b", SECURITY, 101, NOW)), horizon="1D")
    assert outcome.outcome.state is OutcomeState.AVAILABLE
    assert outcome.outcome.thesis_status in {ThesisStatus.SUPPORTED, ThesisStatus.PARTIALLY_SUPPORTED}
