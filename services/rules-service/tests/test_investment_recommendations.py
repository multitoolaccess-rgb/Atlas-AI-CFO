from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.investments.committee_adapters import FixtureCommitteeModel
from app.investments.committee_contracts import CommitteeContext, EvidenceCategory, EvidenceItem
from app.investments.committee_orchestrator import run_committee
from app.investments.contracts import EvidenceKind, EvidenceReference
from app.investments.evidence_validator import EvidenceValidationError
from app.investments.recommendation_contracts import (
    ConvictionBand, InvestmentRecommendation, PositionState, RecommendationFailureCode,
    RecommendationType, TimeHorizon,
)
from app.investments.recommendation_gates import build_recommendation

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)
SECURITY = "sec:recommendation"


def ref(eid, *, as_of=NOW - timedelta(days=1), state="observed"):
    return EvidenceReference(evidence_id=eid, kind=EvidenceKind.SOURCE, source="fixture", content_hash="a" * 64, as_of=as_of, retrieved_at=NOW, state=state)


def context():
    items = (
        EvidenceItem(evidence_id="fundamental:positive", category=EvidenceCategory.FUNDAMENTAL, subject_security_id=SECURITY, owner_id=7, reference=ref("fundamental:positive"), numeric_value="100"),
        EvidenceItem(evidence_id="risk:negative", category=EvidenceCategory.QUANT, subject_security_id=SECURITY, owner_id=7, reference=ref("risk:negative"), numeric_value="20"),
    )
    from app.investments.committee_contracts import EvidencePacket
    packet = EvidencePacket.with_hash(packet_id="packet:recommendation", owner_id=7, subject_security_id=SECURITY, analysis_as_of=NOW, items=items)
    return CommitteeContext.with_hash(run_id="run:recommendation:1", owner_id=7, subject_security_id=SECURITY, analysis_as_of=NOW, evidence_packet=packet, input_hashes=(packet.packet_hash,), portfolio_snapshot_hash="b" * 64)


def responses():
    finding = {"claim": "Validated evidence supports analysis.", "claim_class": "interpretation", "direction": "supports", "evidence_refs": ("fundamental:positive",)}
    return {role: dict(finding) for role in ("fundamental", "technical", "macro", "quant", "portfolio", "risk", "bull", "bear")} | {"chair": {"committee_view": "constructive", "thesis": "The evidence supports a constructive analytical thesis.", "supporting_evidence": ("fundamental:positive",), "contradicting_evidence": ("risk:negative",), "key_risks": ("Risk evidence remains relevant.",), "invalidation_conditions": ("Validated evidence changes.",)}}


def committee():
    return run_committee(context(), FixtureCommitteeModel(responses()), created_at=NOW)


def make(action=RecommendationType.BUY, state=PositionState.NOT_HELD):
    run = committee()
    return build_recommendation(owner_id=7, committee_finding=run.chair_finding, evidence_packet=context().evidence_packet, portfolio_snapshot_hash="b" * 64, position_state=state, requested_type=action, time_horizon=TimeHorizon.MEDIUM_TERM, recommendation_as_of=NOW)


def test_recommendation_is_typed_and_evidence_backed():
    result = make()
    assert result.recommendation is not None
    recommendation = result.recommendation
    assert recommendation.recommendation_type is RecommendationType.BUY
    assert recommendation.committee_finding_id.startswith("committee:")
    assert recommendation.supporting_evidence[0].source_hash == "a" * 64
    assert len(recommendation.recommendation_hash) == 64
    assert recommendation.recommendation_hash == recommendation.model_copy(update={"recommendation_hash": "0" * 64}).model_copy(update={"recommendation_hash": recommendation.recommendation_hash}).recommendation_hash


def test_held_buy_becomes_add_and_not_held_add_becomes_buy():
    assert make(RecommendationType.BUY, PositionState.HELD).recommendation.recommendation_type is RecommendationType.ADD
    assert make(RecommendationType.ADD, PositionState.NOT_HELD).recommendation.recommendation_type is RecommendationType.BUY


def test_sell_or_reduce_when_not_held_degrades_to_watch():
    result = make(RecommendationType.SELL, PositionState.NOT_HELD)
    assert result.recommendation is not None
    assert result.recommendation.recommendation_type is RecommendationType.WATCH
    assert result.recommendation.conviction.band is not ConvictionBand.HIGH


def test_stale_evidence_blocks_actionable_recommendation():
    stale_context = context()
    items = tuple(stale_context.evidence_packet.items)
    from app.investments.committee_contracts import EvidencePacket
    packet = EvidencePacket.with_hash(packet_id=stale_context.evidence_packet.packet_id, owner_id=7, subject_security_id=SECURITY, analysis_as_of=NOW, items=(items[0].model_copy(update={"reference": ref("fundamental:positive", state="stale")}), items[1]))
    stale = CommitteeContext.with_hash(run_id="run:recommendation:stale", owner_id=7, subject_security_id=SECURITY, analysis_as_of=NOW, evidence_packet=packet, input_hashes=(packet.packet_hash,), portfolio_snapshot_hash="b" * 64)
    run = run_committee(stale, FixtureCommitteeModel(responses()), created_at=NOW)
    assert run.chair_finding is None


def test_future_committee_is_rejected():
    run = committee()
    result = build_recommendation(owner_id=7, committee_finding=run.chair_finding, evidence_packet=context().evidence_packet, portfolio_snapshot_hash="b" * 64, position_state=PositionState.NOT_HELD, requested_type=RecommendationType.BUY, time_horizon=TimeHorizon.SHORT_TERM, recommendation_as_of=NOW - timedelta(days=2))
    assert result.failure_code is RecommendationFailureCode.TEMPORAL_VIOLATION


def test_unknown_position_blocks_actionable_semantics():
    result = make(RecommendationType.ADD, PositionState.UNKNOWN)
    assert result.failure_code is RecommendationFailureCode.PORTFOLIO_CONSTRAINT


def test_mixed_view_is_not_high_conviction_actionable():
    run = committee()
    chair = run.chair_finding.model_copy(update={"committee_view": "mixed"})
    result = build_recommendation(owner_id=7, committee_finding=chair, evidence_packet=context().evidence_packet, portfolio_snapshot_hash="b" * 64, position_state=PositionState.NOT_HELD, requested_type=RecommendationType.BUY, time_horizon=TimeHorizon.MEDIUM_TERM, recommendation_as_of=NOW)
    assert result.recommendation is not None
    assert result.recommendation.conviction.band is not ConvictionBand.HIGH


def test_contract_rejects_execution_fields_and_bad_lifecycle():
    recommendation = make().recommendation
    with pytest.raises(ValidationError):
        InvestmentRecommendation.model_validate({**recommendation.model_dump(), "order_quantity": "1"})
    with pytest.raises(ValidationError):
        InvestmentRecommendation.model_validate({**recommendation.model_dump(), "status": "executed"})


def test_no_execution_imports_in_recommendation_modules():
    import ast
    from pathlib import Path
    for path in (Path(__file__).parents[1] / "app" / "investments").glob("recommendation*.py"):
        tree = ast.parse(path.read_text())
        names = {alias.name.lower().replace("-", "_") for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
        assert not names & {"broker", "order", "orders", "execution", "transfer", "trading", "money_movement"}
