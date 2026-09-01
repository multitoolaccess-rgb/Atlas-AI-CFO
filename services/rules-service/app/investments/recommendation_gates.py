"""Deterministic INV-09 recommendation gates.

The service consumes a validated INV-08 CommitteeFinding and a frozen evidence
packet. It never calls a model, persists records, mutates holdings, or creates
an executable order representation.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Iterable

from .committee_contracts import CommitteeDataQuality, CommitteeFinding, CommitteeView, EvidencePacket
from .recommendation_contracts import (
    ConvictionAssessment, ConvictionBand, EvidenceRole, InvestmentRecommendation,
    PortfolioImpact, PortfolioPositionContext, PositionState, RecommendationEvidence,
    RecommendationFailureCode, RecommendationFreshness, RecommendationQuality,
    RecommendationResult, RecommendationStatus, RecommendationType, TimeHorizon,
)
from .evidence_validator import EvidenceValidationError, validate_packet

RECOMMENDATION_METHODOLOGY_VERSION = "investment-recommendation/v1"


def _failure(code: RecommendationFailureCode, reason: str) -> RecommendationResult:
    return RecommendationResult(failure_code=code, failure_reason=" ".join(reason.split())[:240])


def _action_for(*, requested: RecommendationType, position_state: PositionState) -> RecommendationType:
    if requested is RecommendationType.BUY and position_state is PositionState.HELD:
        return RecommendationType.ADD
    if requested is RecommendationType.ADD and position_state is PositionState.NOT_HELD:
        return RecommendationType.BUY
    if requested in {RecommendationType.REDUCE, RecommendationType.SELL} and position_state is PositionState.NOT_HELD:
        return RecommendationType.WATCH
    return requested


def _conviction(*, finding: CommitteeFinding, valid_evidence: int, total_evidence: int, stale: bool, blocker: str | None) -> ConvictionAssessment:
    coverage = Decimal(valid_evidence) / Decimal(total_evidence) if total_evidence else Decimal("0")
    support = Decimal("1") if finding.committee_view in {CommitteeView.CONSTRUCTIVE, CommitteeView.CAUTIOUS, CommitteeView.NEUTRAL} else Decimal("0.5") if finding.committee_view is CommitteeView.MIXED else Decimal("0")
    quality = Decimal("0.5") if stale else Decimal("1")
    score = int((coverage * Decimal("40") + support * Decimal("35") + quality * Decimal("25")).to_integral_value())
    blockers = (blocker,) if blocker else ()
    if blocker:
        score = min(score, 25)
    band = ConvictionBand.UNAVAILABLE if blocker and score == 0 else ConvictionBand.LOW if score < 50 else ConvictionBand.MEDIUM if score < 75 else ConvictionBand.HIGH
    if blocker and score >= 75:
        band = ConvictionBand.MEDIUM
    if blocker is None and score >= 75:
        band = ConvictionBand.MEDIUM
    return ConvictionAssessment(
        score=score, band=band,
        evidence_coverage=format(coverage.normalize(), "f"),
        committee_support=format(support.normalize(), "f"),
        data_quality=format(quality.normalize(), "f"),
        blockers=blockers,
        drivers=("committee_view", "validated_evidence"),
        methodology_version=RECOMMENDATION_METHODOLOGY_VERSION,
    )


def _recommendation_id(*, finding: CommitteeFinding, action: RecommendationType, snapshot_hash: str) -> str:
    digest = hashlib.sha256(f"{finding.finding_hash}|{action.value}|{snapshot_hash}|{RECOMMENDATION_METHODOLOGY_VERSION}".encode()).hexdigest()[:40]
    return f"investment-recommendation:{digest}"


def build_recommendation(
    *,
    owner_id: int,
    committee_finding: CommitteeFinding,
    evidence_packet: EvidencePacket,
    portfolio_snapshot_hash: str,
    position_state: PositionState,
    requested_type: RecommendationType,
    time_horizon: TimeHorizon,
    recommendation_as_of: datetime,
    review_after: datetime | None = None,
    expires_at: datetime | None = None,
    concentration_note: str | None = None,
    analytical_allocation_range: str | None = None,
) -> RecommendationResult:
    """Create a typed recommendation only after deterministic quality gates."""
    try:
        validate_packet(evidence_packet)
    except EvidenceValidationError as exc:
        return _failure(RecommendationFailureCode.INVALID_EVIDENCE, str(exc))
    if committee_finding.run_id.startswith("run:") is False or committee_finding.subject_security_id != evidence_packet.subject_security_id:
        return _failure(RecommendationFailureCode.INVALID_COMMITTEE, "committee subject or run is invalid")
    if committee_finding.analysis_as_of > recommendation_as_of:
        return _failure(RecommendationFailureCode.TEMPORAL_VIOLATION, "committee analysis is later than recommendation as_of")
    if portfolio_snapshot_hash == "0" * 64:
        return _failure(RecommendationFailureCode.INSUFFICIENT_EVIDENCE, "portfolio snapshot is unavailable")
    if recommendation_as_of.tzinfo is None or recommendation_as_of.utcoffset() is None:
        return _failure(RecommendationFailureCode.TEMPORAL_VIOLATION, "recommendation timestamp must be UTC")
    recommendation_as_of = recommendation_as_of.astimezone(UTC)
    action = _action_for(requested=requested_type, position_state=position_state)
    if action in {RecommendationType.BUY, RecommendationType.ADD, RecommendationType.REDUCE, RecommendationType.SELL} and position_state is PositionState.UNKNOWN:
        return _failure(RecommendationFailureCode.PORTFOLIO_CONSTRAINT, "position state is unknown for an actionable type")
    evidence_by_id = {item.evidence_id: item for item in evidence_packet.items}
    refs = tuple(dict.fromkeys((*committee_finding.supporting_evidence, *committee_finding.contradicting_evidence)))
    missing = [ref for ref in refs if ref not in evidence_by_id]
    if missing:
        return _failure(RecommendationFailureCode.INVALID_EVIDENCE, "committee evidence is outside the packet")
    stale = any(evidence_by_id[ref].reference.state.value == "stale" for ref in refs)
    if stale and action in {RecommendationType.BUY, RecommendationType.ADD, RecommendationType.REDUCE, RecommendationType.SELL}:
        return _failure(RecommendationFailureCode.STALE_CONTEXT, "stale evidence cannot support an actionable recommendation")
    if not refs:
        return _failure(RecommendationFailureCode.INSUFFICIENT_EVIDENCE, "recommendation requires evidence")
    blocker = "mixed_committee_view" if committee_finding.committee_view is CommitteeView.MIXED else None
    conviction = _conviction(finding=committee_finding, valid_evidence=len(refs), total_evidence=len(evidence_packet.items), stale=stale, blocker=blocker)
    if action in {RecommendationType.BUY, RecommendationType.ADD, RecommendationType.REDUCE, RecommendationType.SELL} and conviction.band is ConvictionBand.LOW:
        return _failure(RecommendationFailureCode.INSUFFICIENT_EVIDENCE, "conviction is below the actionable threshold")
    quality = RecommendationQuality(
        freshness=RecommendationFreshness.STALE if stale else RecommendationFreshness.FRESH,
        data_quality=tuple(sorted({evidence_by_id[ref].reference.state.value for ref in refs})),
        omissions=() if len(refs) == len(evidence_packet.items) else ("some packet evidence was not material to this recommendation",),
    )
    support = tuple(RecommendationEvidence(
        evidence_id=ref, role=EvidenceRole.SUPPORTING, category=evidence_by_id[ref].category,
        subject_security_id=evidence_by_id[ref].subject_security_id, owner_id=evidence_by_id[ref].owner_id,
        source_hash=evidence_by_id[ref].reference.content_hash, as_of=evidence_by_id[ref].reference.as_of,
        state=CommitteeDataQuality(evidence_by_id[ref].reference.state.value), numeric_value=evidence_by_id[ref].numeric_value,
    ) for ref in committee_finding.supporting_evidence)
    contradicting = tuple(RecommendationEvidence(
        evidence_id=ref, role=EvidenceRole.CONTRADICTING, category=evidence_by_id[ref].category,
        subject_security_id=evidence_by_id[ref].subject_security_id, owner_id=evidence_by_id[ref].owner_id,
        source_hash=evidence_by_id[ref].reference.content_hash, as_of=evidence_by_id[ref].reference.as_of,
        state=CommitteeDataQuality(evidence_by_id[ref].reference.state.value), numeric_value=evidence_by_id[ref].numeric_value,
    ) for ref in committee_finding.contradicting_evidence)
    review = review_after or recommendation_as_of + timedelta(days=30 if time_horizon is TimeHorizon.LONG_TERM else 14 if time_horizon is TimeHorizon.MEDIUM_TERM else 7)
    impact = PortfolioImpact(
        portfolio_snapshot_hash=portfolio_snapshot_hash,
        concentration_note=concentration_note,
        analytical_allocation_range=analytical_allocation_range,
        assumptions=("Analytical guidance is not an execution instruction.",),
    )
    position = PortfolioPositionContext(state=position_state, portfolio_snapshot_hash=portfolio_snapshot_hash, owner_id=owner_id, concentration_state="not_provided" if not concentration_note else "disclosed")
    input_hash = hashlib.sha256(f"{committee_finding.finding_hash}|{evidence_packet.packet_hash}|{portfolio_snapshot_hash}|{action.value}".encode()).hexdigest()
    metadata = {"provider": committee_finding.model_metadata.provider, "model": committee_finding.model_metadata.model, "model_version": committee_finding.model_metadata.model_version, "prompt_template_version": committee_finding.model_metadata.prompt_template_version}
    return RecommendationResult(recommendation=InvestmentRecommendation.with_hash(
        recommendation_id=_recommendation_id(finding=committee_finding, action=action, snapshot_hash=portfolio_snapshot_hash),
        owner_id=owner_id, security_id=committee_finding.subject_security_id, recommendation_type=action,
        status=RecommendationStatus.ACTIVE, committee_run_id=committee_finding.run_id, committee_finding_id=committee_finding.finding_id,
        portfolio_snapshot_hash=portfolio_snapshot_hash, analysis_as_of=committee_finding.analysis_as_of, recommendation_as_of=recommendation_as_of,
        time_horizon=time_horizon, conviction=conviction, thesis=committee_finding.thesis,
        rationale="Recommendation is derived from the validated committee view and immutable evidence packet.",
        supporting_evidence=support, contradicting_evidence=contradicting, key_risks=committee_finding.key_risks,
        invalidation_conditions=committee_finding.invalidation_conditions or ("Revalidate the evidence at the next review.",),
        catalysts=(), portfolio_impact=impact, position_context=position, quality=quality,
        review_after=review, expires_at=expires_at, methodology_version=RECOMMENDATION_METHODOLOGY_VERSION,
        model_metadata=metadata, input_hash=input_hash, created_at=recommendation_as_of,
    ))


__all__ = ["RECOMMENDATION_METHODOLOGY_VERSION", "build_recommendation"]
