"""INV-08 typed AI Investment Committee contracts.

These models are analysis records, not canonical financial facts or
recommendations. Model output is bounded before it can become a finding, and
all material claims point back to a frozen Atlas evidence packet.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .contracts import DataState, EvidenceKind, EvidenceReference, InvestmentStrictModel


class SpecialistRole(StrEnum):
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    MACRO = "macro"
    QUANT = "quant"
    PORTFOLIO = "portfolio"
    RISK = "risk"
    BULL = "bull"
    BEAR = "bear"
    CHAIR = "chair"


class ClaimClass(StrEnum):
    OBSERVED_FACT = "observed_fact"
    CALCULATED_METRIC = "calculated_metric"
    ASSUMPTION = "assumption"
    INTERPRETATION = "interpretation"
    UNCERTAINTY = "uncertainty"


class FindingDirection(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class CommitteeView(StrEnum):
    CONSTRUCTIVE = "constructive"
    NEUTRAL = "neutral"
    CAUTIOUS = "cautious"
    MIXED = "mixed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ConfidenceBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNAVAILABLE = "unavailable"


class CommitteeStatus(StrEnum):
    COMPLETE = "complete"
    ABSTAINED = "abstained"
    FAILED = "failed"


class CommitteeFailureCode(StrEnum):
    INSUFFICIENT_DATA = "insufficient_data"
    INVALID_EVIDENCE = "invalid_evidence"
    STALE_CONTEXT = "stale_context"
    TEMPORAL_VIOLATION = "temporal_violation"
    SPECIALIST_FAILURE = "specialist_failure"
    SCHEMA_VALIDATION_FAILURE = "schema_validation_failure"
    EVIDENCE_VALIDATION_FAILURE = "evidence_validation_failure"
    CONFLICT_UNRESOLVED = "conflict_unresolved"
    MODEL_UNAVAILABLE = "model_unavailable"


class EvidenceCategory(StrEnum):
    PORTFOLIO = "portfolio"
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    MACRO = "macro"
    QUANT = "quant"
    MARKET = "market"
    FILING = "filing"
    EARNINGS = "earnings"
    CALCULATION = "calculation"


class CommitteeDataQuality(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"
    MISSING = "missing"
    STALE = "stale"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


class CommitteeModelMetadata(InvestmentStrictModel):
    """Non-secret model trace metadata; credentials and raw prompts are excluded."""

    schema_version: Literal["CommitteeModelMetadata/v1"] = "CommitteeModelMetadata/v1"
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:/-]+$")
    model_version: str = Field(min_length=1, max_length=128)
    prompt_template_version: str = Field(min_length=1, max_length=64)


class EvidenceItem(InvestmentStrictModel):
    """One bounded packet item; raw provider payloads never enter this model."""

    schema_version: Literal["CommitteeEvidenceItem/v1"] = "CommitteeEvidenceItem/v1"
    evidence_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    category: EvidenceCategory
    subject_security_id: str | None = Field(default=None, max_length=128)
    owner_id: int | None = Field(default=None, gt=0)
    reference: EvidenceReference
    excerpt: str | None = Field(default=None, max_length=1200)
    numeric_value: str | None = Field(default=None, max_length=64)

    @field_validator("excerpt")
    @classmethod
    def sanitize_excerpt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # External text remains data. Control characters are removed, but no
        # instruction-like content is executed or promoted to authority.
        return " ".join(value.replace("\x00", " ").split())

    @field_validator("numeric_value")
    @classmethod
    def finite_numeric_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("numeric evidence must be decimal") from None
        if not number.is_finite():
            raise ValueError("numeric evidence must be finite")
        return format(number.normalize(), "f")


class EvidencePacket(InvestmentStrictModel):
    """Immutable owner-scoped evidence snapshot used by one committee run."""

    schema_version: Literal["CommitteeEvidencePacket/v1"] = "CommitteeEvidencePacket/v1"
    packet_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    owner_id: int = Field(gt=0)
    subject_security_id: str = Field(min_length=1, max_length=128)
    analysis_as_of: datetime
    items: tuple[EvidenceItem, ...] = Field(default=(), max_length=500)
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("analysis_as_of")
    @classmethod
    def utc_analysis_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("analysis_as_of must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def unique_item_ids(self) -> "EvidencePacket":
        ids = [item.evidence_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique within a packet")
        for item in self.items:
            if item.subject_security_id not in (None, self.subject_security_id):
                raise ValueError("evidence subject does not match packet subject")
            if item.owner_id not in (None, self.owner_id):
                raise ValueError("evidence owner does not match packet owner")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"packet_hash"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "EvidencePacket":
        provisional = cls.model_validate({**values, "packet_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "packet_hash": digest})


class CommitteeContext(InvestmentStrictModel):
    """Bounded context passed to specialists; no database or credential access."""

    schema_version: Literal["InvestmentCommitteeContext/v1"] = "InvestmentCommitteeContext/v1"
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^run:[A-Za-z0-9._:-]+$")
    owner_id: int = Field(gt=0)
    subject_security_id: str = Field(min_length=1, max_length=128)
    analysis_as_of: datetime
    evidence_packet: EvidencePacket
    portfolio_snapshot_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    input_hashes: tuple[str, ...] = Field(min_length=1, max_length=100)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("analysis_as_of")
    @classmethod
    def context_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("analysis_as_of must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def context_matches_packet(self) -> "CommitteeContext":
        if self.evidence_packet.owner_id != self.owner_id:
            raise ValueError("context owner does not match evidence packet")
        if self.evidence_packet.subject_security_id != self.subject_security_id:
            raise ValueError("context subject does not match evidence packet")
        if self.evidence_packet.analysis_as_of != self.analysis_as_of:
            raise ValueError("context as_of does not match evidence packet")
        if self.evidence_packet.packet_hash not in self.input_hashes:
            raise ValueError("context input hashes must include evidence packet hash")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"context_hash"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "CommitteeContext":
        provisional = cls.model_validate({**values, "context_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "context_hash": digest})


class NumericClaim(InvestmentStrictModel):
    """Explicit numerical assertion that must reconcile to packet evidence."""

    value: str = Field(min_length=1, max_length=64)
    evidence_ref: str = Field(min_length=1, max_length=128)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: str) -> str:
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("numeric claim must be decimal") from None
        if not number.is_finite():
            raise ValueError("numeric claim must be finite")
        return format(number.normalize(), "f")


class ModelFindingPayload(InvestmentStrictModel):
    """Strict response shape accepted from an injected model adapter."""

    claim: str = Field(min_length=1, max_length=1200)
    claim_class: ClaimClass
    direction: FindingDirection
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    calculation_refs: tuple[str, ...] = Field(default=(), max_length=32)
    risks: tuple[str, ...] = Field(default=(), max_length=16)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)
    data_quality: tuple[CommitteeDataQuality, ...] = Field(default=(), max_length=16)
    numeric_claims: tuple[NumericClaim, ...] = Field(default=(), max_length=16)
    abstained: bool = False
    abstention_reason: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def claim_support(self) -> "ModelFindingPayload":
        if self.abstained:
            if not self.abstention_reason:
                raise ValueError("abstention requires a reason")
            return self
        if not self.evidence_refs and not self.calculation_refs:
            raise ValueError("non-abstained finding requires evidence")
        if self.claim_class is not ClaimClass.UNCERTAINTY and not self.evidence_refs and not self.calculation_refs:
            raise ValueError("material finding requires evidence")
        if self.numeric_claims and not self.evidence_refs:
            raise ValueError("numeric claims require evidence references")
        return self


class AgentFinding(InvestmentStrictModel):
    """Server-attributed specialist finding; model identity is never caller-owned."""

    schema_version: Literal["AgentFinding/v1"] = "AgentFinding/v1"
    finding_id: str = Field(min_length=1, max_length=160, pattern=r"^finding:[A-Za-z0-9._:-]+$")
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^run:[A-Za-z0-9._:-]+$")
    specialist: SpecialistRole
    subject_security_id: str = Field(min_length=1, max_length=128)
    claim: str = Field(min_length=1, max_length=1200)
    claim_class: ClaimClass
    direction: FindingDirection
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    calculation_refs: tuple[str, ...] = Field(default=(), max_length=32)
    risks: tuple[str, ...] = Field(default=(), max_length=16)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)
    data_quality: tuple[CommitteeDataQuality, ...] = Field(default=(), max_length=16)
    numeric_claims: tuple[NumericClaim, ...] = Field(default=(), max_length=16)
    as_of: datetime
    methodology_version: str = Field(min_length=1, max_length=64)
    model_metadata: CommitteeModelMetadata
    abstained: bool = False
    abstention_reason: str | None = Field(default=None, max_length=240)
    finding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of")
    @classmethod
    def finding_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("finding as_of must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def finding_support(self) -> "AgentFinding":
        if self.abstained:
            if not self.abstention_reason:
                raise ValueError("abstention requires a reason")
        elif not self.evidence_refs and not self.calculation_refs:
            raise ValueError("finding requires evidence")
        if self.numeric_claims and not self.evidence_refs:
            raise ValueError("numeric claims require evidence references")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"finding_hash"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "AgentFinding":
        provisional = cls.model_validate({**values, "finding_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "finding_hash": digest})


class ConfidenceAssessment(InvestmentStrictModel):
    """Deterministically computed confidence; model-authored scores are excluded."""

    schema_version: Literal["CommitteeConfidence/v1"] = "CommitteeConfidence/v1"
    score: int = Field(ge=0, le=100)
    band: ConfidenceBand
    evidence_coverage: str = Field(pattern=r"^0(?:\.\d+)?|1(?:\.0+)?$")
    valid_evidence_quality: str = Field(pattern=r"^0(?:\.\d+)?|1(?:\.0+)?$")
    specialist_agreement: str = Field(pattern=r"^0(?:\.\d+)?|1(?:\.0+)?$")
    drivers: tuple[str, ...] = Field(default=(), max_length=12)
    limitations: tuple[str, ...] = Field(default=(), max_length=12)
    methodology_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def fractions_are_bounded(self) -> "ConfidenceAssessment":
        for field_name in ("evidence_coverage", "valid_evidence_quality", "specialist_agreement"):
            value = Decimal(getattr(self, field_name))
            if value < 0 or value > 1:
                raise ValueError(f"{field_name} must be between zero and one")
        if self.band is ConfidenceBand.UNAVAILABLE and self.score != 0:
            raise ValueError("unavailable confidence must have a zero score")
        return self


class ResearchFinding(InvestmentStrictModel):
    """A bounded research handoff assembled from validated findings."""

    schema_version: Literal["ResearchFinding/v1"] = "ResearchFinding/v1"
    specialist_findings: tuple[str, ...] = Field(default=(), max_length=20)
    supporting_evidence: tuple[str, ...] = Field(default=(), max_length=32)
    contradicting_evidence: tuple[str, ...] = Field(default=(), max_length=32)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)


class RiskAssessment(InvestmentStrictModel):
    """Structured risk handoff; risk text is evidence-linked by the finding."""

    schema_version: Literal["RiskAssessment/v1"] = "RiskAssessment/v1"
    risks: tuple[str, ...] = Field(default=(), max_length=16)
    blocking: bool = False
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)


class InvestmentThesis(InvestmentStrictModel):
    """Non-actionable thesis projection for later recommendation phases."""

    schema_version: Literal["InvestmentThesis/v1"] = "InvestmentThesis/v1"
    subject_security_id: str = Field(min_length=1, max_length=128)
    committee_view: CommitteeView
    thesis: str = Field(min_length=1, max_length=1600)
    bull_case: str = Field(min_length=1, max_length=1200)
    bear_case: str = Field(min_length=1, max_length=1200)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)


class RecommendationDraft(InvestmentStrictModel):
    """Future INV-09 handoff without an action or executable semantics."""

    schema_version: Literal["RecommendationDraft/v1"] = "RecommendationDraft/v1"
    subject_security_id: str = Field(min_length=1, max_length=128)
    committee_finding_id: str = Field(min_length=1, max_length=160)
    status: Literal["analysis_only", "abstain"] = "analysis_only"
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    limitation: str | None = Field(default=None, max_length=240)


class Abstention(InvestmentStrictModel):
    """Explicit safe result when committee analysis cannot complete."""

    schema_version: Literal["Abstention/v1"] = "Abstention/v1"
    code: CommitteeFailureCode
    reason: str = Field(min_length=1, max_length=240)
    analysis_as_of: datetime

    @field_validator("analysis_as_of")
    @classmethod
    def abstention_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("abstention timestamp must be timezone-aware UTC")
        return value.astimezone(UTC)


class ModelChairPayload(InvestmentStrictModel):
    """Strict chair response; it contains a view, never an action."""

    committee_view: CommitteeView
    thesis: str = Field(min_length=1, max_length=1600)
    supporting_evidence: tuple[str, ...] = Field(default=(), max_length=32)
    contradicting_evidence: tuple[str, ...] = Field(default=(), max_length=32)
    key_risks: tuple[str, ...] = Field(default=(), max_length=16)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)
    invalidation_conditions: tuple[str, ...] = Field(default=(), max_length=16)
    specialist_disagreement: tuple[str, ...] = Field(default=(), max_length=16)
    numeric_claims: tuple[NumericClaim, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def chair_support(self) -> "ModelChairPayload":
        if self.committee_view is not CommitteeView.INSUFFICIENT_EVIDENCE and not self.supporting_evidence and not self.contradicting_evidence:
            raise ValueError("chair conclusion requires evidence")
        if self.numeric_claims and not (self.supporting_evidence or self.contradicting_evidence):
            raise ValueError("numeric chair claims require evidence")
        return self


class CommitteeFinding(InvestmentStrictModel):
    """Typed chair conclusion for INV-08; not an INV-09 recommendation."""

    schema_version: Literal["CommitteeFinding/v1"] = "CommitteeFinding/v1"
    finding_id: str = Field(min_length=1, max_length=160, pattern=r"^committee:[A-Za-z0-9._:-]+$")
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^run:[A-Za-z0-9._:-]+$")
    subject_security_id: str = Field(min_length=1, max_length=128)
    committee_view: CommitteeView
    thesis: str = Field(min_length=1, max_length=1600)
    supporting_evidence: tuple[str, ...] = Field(default=(), max_length=32)
    contradicting_evidence: tuple[str, ...] = Field(default=(), max_length=32)
    key_risks: tuple[str, ...] = Field(default=(), max_length=16)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)
    invalidation_conditions: tuple[str, ...] = Field(default=(), max_length=16)
    specialist_disagreement: tuple[str, ...] = Field(default=(), max_length=16)
    numeric_claims: tuple[NumericClaim, ...] = Field(default=(), max_length=16)
    confidence: ConfidenceAssessment
    analysis_as_of: datetime
    methodology_version: str = Field(min_length=1, max_length=64)
    model_metadata: CommitteeModelMetadata
    input_hashes: tuple[str, ...] = Field(min_length=1, max_length=100)
    finding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("analysis_as_of")
    @classmethod
    def chair_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("analysis_as_of must be timezone-aware UTC")
        return value.astimezone(UTC)

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"finding_hash"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "CommitteeFinding":
        provisional = cls.model_validate({**values, "finding_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "finding_hash": digest})


class CommitteeRun(InvestmentStrictModel):
    """Append-only in-memory run record; new challenges create new runs."""

    schema_version: Literal["InvestmentCommitteeRun/v1"] = "InvestmentCommitteeRun/v1"
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^run:[A-Za-z0-9._:-]+$")
    original_run_id: str | None = Field(default=None, max_length=128)
    owner_id: int = Field(gt=0)
    subject_security_id: str = Field(min_length=1, max_length=128)
    analysis_as_of: datetime
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    specialist_findings: tuple[AgentFinding, ...] = Field(default=(), max_length=20)
    bull_finding: AgentFinding | None = None
    bear_finding: AgentFinding | None = None
    chair_finding: CommitteeFinding | None = None
    status: CommitteeStatus
    failure_code: CommitteeFailureCode | None = None
    failure_reason: str | None = Field(default=None, max_length=240)
    created_at: datetime
    methodology_version: str = Field(min_length=1, max_length=64)
    model_metadata: CommitteeModelMetadata
    run_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("analysis_as_of", "created_at")
    @classmethod
    def run_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("run timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def status_coherence(self) -> "CommitteeRun":
        if self.status is CommitteeStatus.COMPLETE and self.chair_finding is None:
            raise ValueError("complete run requires chair finding")
        if self.status is not CommitteeStatus.COMPLETE and self.chair_finding is not None:
            raise ValueError("failed or abstained run cannot contain chair finding")
        if self.status is not CommitteeStatus.COMPLETE and not self.failure_code:
            raise ValueError("non-complete run requires failure code")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"run_hash", "created_at"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "CommitteeRun":
        provisional = cls.model_validate({**values, "run_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "run_hash": digest})


__all__ = [
    "AgentFinding", "ClaimClass", "CommitteeContext", "CommitteeDataQuality",
    "CommitteeFailureCode", "CommitteeFinding", "CommitteeModelMetadata",
    "CommitteeRun", "CommitteeStatus", "CommitteeView", "ConfidenceAssessment",
    "ConfidenceBand", "EvidenceCategory", "EvidenceItem", "EvidencePacket",
    "FindingDirection", "ModelChairPayload", "ModelFindingPayload", "NumericClaim",
    "SpecialistRole", "ResearchFinding", "RiskAssessment", "InvestmentThesis",
    "RecommendationDraft", "Abstention",
]
