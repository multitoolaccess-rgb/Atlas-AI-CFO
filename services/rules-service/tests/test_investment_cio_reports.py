from datetime import UTC, date, datetime, timedelta

import pytest

from app.investments.cio_reports import (
    CIOReport, ReportQuality, ReportType, generate_cio_report, period_for,
)
from app.investments.committee_adapters import FixtureCommitteeModel
from app.investments.committee_contracts import CommitteeContext, EvidenceCategory, EvidenceItem
from app.investments.committee_orchestrator import run_committee
from app.investments.contracts import EvidenceKind, EvidenceReference
from app.investments.recommendation_contracts import PositionState, RecommendationType, TimeHorizon
from app.investments.recommendation_gates import build_recommendation

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)
SECURITY = "sec:report"


def _reference(eid, *, as_of=NOW - timedelta(days=1)):
    return EvidenceReference(evidence_id=eid, kind=EvidenceKind.SOURCE, source="fixture", content_hash="a" * 64, as_of=as_of, retrieved_at=NOW)


def _committee():
    item = EvidenceItem(evidence_id="fundamental:one", category=EvidenceCategory.FUNDAMENTAL, subject_security_id=SECURITY, owner_id=7, reference=_reference("fundamental:one"), numeric_value="100")
    from app.investments.committee_contracts import EvidencePacket
    packet = EvidencePacket.with_hash(packet_id="packet:report", owner_id=7, subject_security_id=SECURITY, analysis_as_of=NOW, items=(item,))
    context = CommitteeContext.with_hash(run_id="run:report:1", owner_id=7, subject_security_id=SECURITY, analysis_as_of=NOW, evidence_packet=packet, input_hashes=(packet.packet_hash,), portfolio_snapshot_hash="b" * 64)
    finding = {"claim": "Evidence supports the view.", "claim_class": "interpretation", "direction": "supports", "evidence_refs": ("fundamental:one",)}
    responses = {role: dict(finding) for role in ("fundamental", "technical", "macro", "quant", "portfolio", "risk", "bull", "bear")} | {"chair": {"committee_view": "constructive", "thesis": "The evidence supports a constructive view.", "supporting_evidence": ("fundamental:one",), "contradicting_evidence": (), "key_risks": ("Evidence remains bounded.",), "invalidation_conditions": ("New evidence changes the thesis.",)}}
    run = run_committee(context, FixtureCommitteeModel(responses), created_at=NOW)
    recommendation = build_recommendation(owner_id=7, committee_finding=run.chair_finding, evidence_packet=packet, portfolio_snapshot_hash="b" * 64, position_state=PositionState.NOT_HELD, requested_type=RecommendationType.BUY, time_horizon=TimeHorizon.MEDIUM_TERM, recommendation_as_of=NOW).recommendation
    return run.chair_finding, recommendation


def test_daily_and_weekly_periods_are_explicit():
    daily_start, daily_end = period_for(ReportType.DAILY_BRIEF, date(2026, 8, 31))
    weekly_start, weekly_end = period_for(ReportType.WEEKLY_REVIEW, date(2026, 8, 31))
    assert daily_start.date() == daily_end.date()
    assert (weekly_end - weekly_start).days == 6
    assert daily_start.tzinfo is not None


def test_report_assembles_canonical_recommendation_and_committee_without_rewriting_action():
    finding, recommendation = _committee()
    report = generate_cio_report(owner_id=7, report_type=ReportType.DAILY_BRIEF, anchor_date=date(2026, 8, 31), as_of=NOW, portfolio_snapshot_hash="b" * 64, committee_findings=(finding,), recommendations=(recommendation,), portfolio_items=("Portfolio review required.",), review_items=("Review recommendation before deciding.",))
    assert report.report_type is ReportType.DAILY_BRIEF
    assert report.recommendations[0].recommendation_type == RecommendationType.BUY.value
    assert report.committee_runs[0].view.value == "constructive"
    assert "fundamental:one" in {item.evidence_id for item in report.evidence}
    assert report.quality is ReportQuality.PARTIAL


def test_report_is_reproducible_for_identical_inputs():
    finding, recommendation = _committee()
    kwargs = dict(owner_id=7, report_type=ReportType.WEEKLY_REVIEW, anchor_date=date(2026, 8, 31), as_of=NOW, generated_at=NOW, portfolio_snapshot_hash="b" * 64, committee_findings=(finding,), recommendations=(recommendation,))
    first = generate_cio_report(**kwargs)
    second = generate_cio_report(**kwargs)
    assert first.report_hash == second.report_hash
    assert first.input_hash == second.input_hash
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_future_recommendation_or_committee_is_rejected():
    finding, recommendation = _committee()
    with pytest.raises(ValueError, match="future"):
        generate_cio_report(owner_id=7, report_type=ReportType.DAILY_BRIEF, anchor_date=date(2026, 8, 31), as_of=NOW - timedelta(days=2), portfolio_snapshot_hash="b" * 64, committee_findings=(finding,), recommendations=(recommendation,))


def test_owner_mismatch_is_rejected():
    finding, recommendation = _committee()
    with pytest.raises(ValueError, match="owner"):
        generate_cio_report(owner_id=8, report_type=ReportType.DAILY_BRIEF, anchor_date=date(2026, 8, 31), as_of=NOW, portfolio_snapshot_hash="b" * 64, committee_findings=(finding,), recommendations=(recommendation,))


def test_invalid_period_and_naive_timestamp_are_rejected():
    with pytest.raises(ValueError):
        generate_cio_report(owner_id=7, report_type=ReportType.DAILY_BRIEF, anchor_date=date(2026, 8, 31), as_of=datetime(2026, 8, 31, 12), portfolio_snapshot_hash="b" * 64)
    with pytest.raises(ValueError):
        CIOReport.model_validate({"owner_id": 7, "report_type": "daily_brief", "period_start": NOW, "period_end": NOW - timedelta(days=1), "as_of": NOW, "generated_at": NOW, "portfolio_snapshot_hash": "b" * 64, "quality": "complete", "input_hash": "a" * 64, "report_hash": "a" * 64})


def test_no_execution_imports_in_report_module():
    import ast
    from pathlib import Path
    path = Path(__file__).parents[1] / "app" / "investments" / "cio_reports.py"
    tree = ast.parse(path.read_text())
    names = {alias.name.lower().replace("-", "_") for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert not names & {"broker", "order", "orders", "execution", "transfer", "trading", "money_movement"}
