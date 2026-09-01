"""INV-10 deterministic CIO reporting projections.

Reports assemble already-validated Atlas outputs. They do not calculate
research, reinterpret recommendations, call providers, persist data, schedule
work, or mutate financial state.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Iterable

from pydantic import Field, field_validator, model_validator

from .committee_contracts import CommitteeDataQuality, CommitteeFinding, CommitteeView
from .recommendation_contracts import InvestmentRecommendation
from .contracts import InvestmentStrictModel

REPORT_METHODOLOGY_VERSION = "cio-report/v1"


class ReportType(StrEnum):
    DAILY_BRIEF = "daily_brief"
    WEEKLY_REVIEW = "weekly_review"


class ReportStatus(StrEnum):
    GENERATED = "generated"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class ReportSectionKind(StrEnum):
    EXECUTIVE = "executive_summary"
    PORTFOLIO = "portfolio"
    MARKET = "market"
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    MACRO = "macro"
    QUANT = "quant"
    COMMITTEE = "committee"
    RECOMMENDATIONS = "recommendations"
    CONFLICTS = "conflicts"
    RISKS = "risks"
    REVIEW = "review_items"
    DATA_QUALITY = "data_quality"


class ReportQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


class ReportEvidence(InvestmentStrictModel):
    evidence_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    category: str = Field(min_length=1, max_length=64)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    state: str = Field(min_length=1, max_length=64)

    @field_validator("as_of")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence as_of must be timezone-aware")
        return value.astimezone(UTC)


class ReportSection(InvestmentStrictModel):
    kind: ReportSectionKind
    title: str = Field(min_length=1, max_length=120)
    items: tuple[str, ...] = Field(default=(), max_length=100)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=100)


class RecommendationSummary(InvestmentStrictModel):
    recommendation_id: str = Field(pattern=r"^investment-recommendation:[A-Za-z0-9._:-]+$")
    security_id: str = Field(min_length=1, max_length=128)
    recommendation_type: str = Field(min_length=1, max_length=16)
    conviction_band: str = Field(min_length=1, max_length=32)
    thesis: str = Field(min_length=1, max_length=1600)
    risks: tuple[str, ...] = Field(default=(), max_length=16)
    supporting_evidence_ids: tuple[str, ...] = Field(default=(), max_length=32)
    contradicting_evidence_ids: tuple[str, ...] = Field(default=(), max_length=32)
    review_after: datetime

    @field_validator("review_after")
    @classmethod
    def review_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("review_after must be timezone-aware")
        return value.astimezone(UTC)


class CommitteeSummary(InvestmentStrictModel):
    run_id: str = Field(pattern=r"^run:[A-Za-z0-9._:-]+$")
    finding_id: str = Field(pattern=r"^committee:[A-Za-z0-9._:-]+$")
    security_id: str = Field(min_length=1, max_length=128)
    view: CommitteeView
    thesis: str = Field(min_length=1, max_length=1600)
    supporting_evidence_ids: tuple[str, ...] = Field(default=(), max_length=32)
    contradicting_evidence_ids: tuple[str, ...] = Field(default=(), max_length=32)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def as_of_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("committee as_of must be timezone-aware")
        return value.astimezone(UTC)


class CIOReport(InvestmentStrictModel):
    """Immutable canonical report snapshot, independent of narrative prose."""
    schema_version: str = "CIOReport/v1"
    report_id: str = Field(pattern=r"^cio-report:[a-f0-9]{64}$")
    owner_id: int = Field(gt=0)
    report_type: ReportType
    period_start: datetime
    period_end: datetime
    as_of: datetime
    generated_at: datetime
    status: ReportStatus = ReportStatus.GENERATED
    portfolio_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    committee_runs: tuple[CommitteeSummary, ...] = Field(default=(), max_length=100)
    recommendations: tuple[RecommendationSummary, ...] = Field(default=(), max_length=100)
    evidence: tuple[ReportEvidence, ...] = Field(default=(), max_length=500)
    sections: tuple[ReportSection, ...] = Field(default=(), max_length=30)
    quality: ReportQuality
    methodology_version: str = REPORT_METHODOLOGY_VERSION
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("period_start", "period_end", "as_of", "generated_at")
    @classmethod
    def timestamps_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("report timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def period_and_evidence(self) -> "CIOReport":
        if self.period_start > self.period_end:
            raise ValueError("report period is inverted")
        if self.as_of < self.period_start:
            raise ValueError("report as_of cannot precede period start")
        if self.generated_at < self.as_of:
            raise ValueError("report cannot be generated before as_of")
        ids = {item.evidence_id for item in self.evidence}
        for section in self.sections:
            if not set(section.evidence_ids) <= ids:
                raise ValueError("section references evidence outside report")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"report_id", "report_hash"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "CIOReport":
        provisional = cls.model_validate({**values, "report_id": "cio-report:" + "0" * 64, "report_hash": "0" * 64})
        input_hash = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        payload = {**values, "input_hash": input_hash}
        provisional = cls.model_validate({**payload, "report_id": "cio-report:" + "0" * 64, "report_hash": "0" * 64})
        report_hash = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**payload, "report_id": f"cio-report:{report_hash}", "report_hash": report_hash})


def period_for(report_type: ReportType, anchor: date) -> tuple[datetime, datetime]:
    end = datetime(anchor.year, anchor.month, anchor.day, 23, 59, 59, tzinfo=UTC)
    if report_type is ReportType.DAILY_BRIEF:
        start = end.replace(hour=0, minute=0, second=0)
    else:
        start_date = anchor - timedelta(days=6)
        start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC)
    return start, end


def _evidence_from_recommendation(recommendation: InvestmentRecommendation) -> Iterable[ReportEvidence]:
    for item in (*recommendation.supporting_evidence, *recommendation.contradicting_evidence):
        yield ReportEvidence(evidence_id=item.evidence_id, category=item.category.value, source_hash=item.source_hash, as_of=item.as_of, state=item.state.value)


def generate_cio_report(
    *,
    owner_id: int,
    report_type: ReportType,
    anchor_date: date,
    as_of: datetime,
    portfolio_snapshot_hash: str,
    recommendations: Iterable[InvestmentRecommendation] = (),
    committee_findings: Iterable[CommitteeFinding] = (),
    additional_evidence: Iterable[ReportEvidence] = (),
    portfolio_items: Iterable[str] = (),
    market_items: Iterable[str] = (),
    fundamental_items: Iterable[str] = (),
    technical_items: Iterable[str] = (),
    macro_items: Iterable[str] = (),
    quant_items: Iterable[str] = (),
    risk_items: Iterable[str] = (),
    review_items: Iterable[str] = (),
    generated_at: datetime | None = None,
) -> CIOReport:
    """Assemble a deterministic report from already-authoritative projections."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware UTC")
    as_of = as_of.astimezone(UTC)
    generated = (generated_at or as_of).astimezone(UTC)
    if generated < as_of:
        raise ValueError("generated_at cannot precede as_of")
    start, end = period_for(report_type, anchor_date)
    # A report may be generated at any point within the requested period;
    # upstream items are still filtered by the explicit as_of boundary below.
    recommendations = tuple(sorted(recommendations, key=lambda item: item.recommendation_id))
    committees = tuple(sorted(committee_findings, key=lambda item: item.finding_id))
    evidence_map: dict[str, ReportEvidence] = {}
    for item in additional_evidence:
        if item.as_of > as_of:
            raise ValueError("future additional evidence cannot enter report")
        if item.evidence_id in evidence_map and evidence_map[item.evidence_id] != item:
            raise ValueError("conflicting additional evidence identity")
        evidence_map[item.evidence_id] = item
    for recommendation in recommendations:
        if recommendation.owner_id != owner_id:
            raise ValueError("recommendation owner mismatch")
        if recommendation.portfolio_snapshot_hash != portfolio_snapshot_hash:
            raise ValueError("recommendation portfolio snapshot mismatch")
        if recommendation.recommendation_as_of > as_of:
            raise ValueError("future recommendation cannot enter report")
        for item in _evidence_from_recommendation(recommendation):
            evidence_map.setdefault(item.evidence_id, item)
    committee_summaries: list[CommitteeSummary] = []
    for finding in committees:
        if finding.analysis_as_of > as_of:
            raise ValueError("future committee finding cannot enter report")
        committee_summaries.append(CommitteeSummary(
            run_id=finding.run_id, finding_id=finding.finding_id, security_id=finding.subject_security_id,
            view=finding.committee_view, thesis=finding.thesis, supporting_evidence_ids=finding.supporting_evidence,
            contradicting_evidence_ids=finding.contradicting_evidence, uncertainties=finding.uncertainties, as_of=finding.analysis_as_of,
        ))
    rec_summaries = tuple(RecommendationSummary(
        recommendation_id=item.recommendation_id, security_id=item.security_id,
        recommendation_type=item.recommendation_type.value, conviction_band=item.conviction.band.value,
        thesis=item.thesis, risks=item.key_risks,
        supporting_evidence_ids=tuple(e.evidence_id for e in item.supporting_evidence),
        contradicting_evidence_ids=tuple(e.evidence_id for e in item.contradicting_evidence), review_after=item.review_after,
    ) for item in recommendations)
    conflicts = [f"{summary.security_id}: committee view {summary.view.value} with supporting and contradicting evidence." for summary in committee_summaries if summary.supporting_evidence_ids and summary.contradicting_evidence_ids]
    recommendation_ids = tuple(evidence_id for item in rec_summaries for evidence_id in (*item.supporting_evidence_ids, *item.contradicting_evidence_ids))
    committee_ids = tuple(evidence_id for item in committee_summaries for evidence_id in (*item.supporting_evidence_ids, *item.contradicting_evidence_ids))
    source_evidence = tuple(sorted(evidence_map.values(), key=lambda item: item.evidence_id))
    category_ids = lambda category: tuple(item.evidence_id for item in source_evidence if item.category == category)
    sections_data = (
        (ReportSectionKind.EXECUTIVE, "Executive summary", ("This is an evidence-backed review-only CIO report.",), ()),
        (ReportSectionKind.PORTFOLIO, "Portfolio", tuple(portfolio_items), category_ids("portfolio")),
        (ReportSectionKind.MARKET, "Market context", tuple(market_items), category_ids("market")),
        (ReportSectionKind.FUNDAMENTAL, "Fundamental developments", tuple(fundamental_items), category_ids("fundamental")),
        (ReportSectionKind.TECHNICAL, "Technical signals", tuple(technical_items), category_ids("technical")),
        (ReportSectionKind.QUANT, "Quantitative signals", tuple(quant_items), category_ids("quant")),
        (ReportSectionKind.MACRO, "Macro context", tuple(macro_items), category_ids("macro")),
        (ReportSectionKind.COMMITTEE, "Committee conclusions", tuple(summary.thesis for summary in committee_summaries), committee_ids),
        (ReportSectionKind.RECOMMENDATIONS, "Active recommendations", tuple(f"{item.recommendation_type}: {item.security_id}" for item in rec_summaries), recommendation_ids),
        (ReportSectionKind.CONFLICTS, "Key conflicts", tuple(conflicts), committee_ids),
        (ReportSectionKind.RISKS, "Risks", tuple(risk_items), recommendation_ids),
        (ReportSectionKind.REVIEW, "Items requiring human review", tuple(review_items), ()),
    )
    sections = tuple(ReportSection(kind=kind, title=title, items=items, evidence_ids=tuple(dict.fromkeys(evidence_ids))) for kind, title, items, evidence_ids in sections_data)
    quality = ReportQuality.CONFLICTING if conflicts else ReportQuality.COMPLETE
    if risk_items or review_items:
        quality = ReportQuality.PARTIAL if quality is ReportQuality.COMPLETE else quality
    report = CIOReport.with_hash(
        owner_id=owner_id, report_type=report_type, period_start=start, period_end=end, as_of=as_of,
        generated_at=generated, status=ReportStatus.GENERATED, portfolio_snapshot_hash=portfolio_snapshot_hash,
        committee_runs=tuple(committee_summaries), recommendations=rec_summaries, evidence=source_evidence,
        sections=sections, quality=quality, methodology_version=REPORT_METHODOLOGY_VERSION,
        input_hash="0" * 64, report_hash="0" * 64,
    )
    # The canonical input hash is reconstructed after the immutable snapshot is
    # built, without wall-clock identity. Rebuild once so both fields agree.
    canonical_input = json.dumps({"owner_id": owner_id, "type": report_type.value, "period": [start.isoformat(), end.isoformat()], "as_of": as_of.isoformat(), "portfolio": portfolio_snapshot_hash, "committees": [item.finding_id for item in committee_summaries], "recommendations": [item.recommendation_id for item in rec_summaries], "evidence": [item.evidence_id for item in source_evidence]}, sort_keys=True, separators=(",", ":"))
    input_hash = hashlib.sha256(canonical_input.encode()).hexdigest()
    values = report.model_dump()
    values["input_hash"] = input_hash
    values.pop("report_id", None)
    values.pop("report_hash", None)
    return CIOReport.with_hash(**values)


__all__ = ["CIOReport", "REPORT_METHODOLOGY_VERSION", "ReportEvidence", "ReportQuality", "ReportSection", "ReportSectionKind", "ReportStatus", "ReportType", "RecommendationSummary", "CommitteeSummary", "generate_cio_report", "period_for"]
