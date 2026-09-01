"""INV-09 typed investment recommendation contracts.

These contracts are an immutable analytical projection over Atlas's existing
recommendation/decision lifecycle. They contain no executable order semantics.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .committee_contracts import CommitteeFinding, CommitteeView, EvidenceCategory, CommitteeDataQuality
from .contracts import InvestmentStrictModel


class RecommendationType(StrEnum):
    BUY = "BUY"
    ADD = "ADD"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"
    WATCH = "WATCH"


class RecommendationStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class TimeHorizon(StrEnum):
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class RecommendationFreshness(StrEnum):
    FRESH = "fresh"
    PARTIAL = "partial"
    STALE = "stale"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class ConvictionBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNAVAILABLE = "unavailable"


class RecommendationFailureCode(StrEnum):
    INVALID_COMMITTEE = "invalid_committee"
    INVALID_EVIDENCE = "invalid_evidence"
    TEMPORAL_VIOLATION = "temporal_violation"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    STALE_CONTEXT = "stale_context"
    PORTFOLIO_CONSTRAINT = "portfolio_constraint"
    POLICY_BLOCKED = "policy_blocked"
    UNSUPPORTED_ACTION = "unsupported_action"


class PositionState(StrEnum):
    HELD = "held"
    NOT_HELD = "not_held"
    UNKNOWN = "unknown"


class EvidenceRole(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    CONTEXTUAL = "contextual"
    PORTFOLIO_STATE = "portfolio_state"
    CALCULATION = "calculation"


class RecommendationEvidence(InvestmentStrictModel):
    schema_version: Literal["InvestmentRecommendationEvidence/v1"] = "InvestmentRecommendationEvidence/v1"
    evidence_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    role: EvidenceRole
    category: EvidenceCategory
    subject_security_id: str | None = Field(default=None, max_length=128)
    owner_id: int | None = Field(default=None, gt=0)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    state: CommitteeDataQuality
    numeric_value: str | None = Field(default=None, max_length=64)

    @field_validator("as_of")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence as_of must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("numeric_value")
    @classmethod
    def finite_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("numeric evidence must be decimal") from None
        if not parsed.is_finite():
            raise ValueError("numeric evidence must be finite")
        return format(parsed.normalize(), "f")


class PortfolioPositionContext(InvestmentStrictModel):
    state: PositionState
    current_weight: str | None = Field(default=None, max_length=64)
    concentration_state: str | None = Field(default=None, max_length=64)
    portfolio_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner_id: int = Field(gt=0)

    @field_validator("current_weight")
    @classmethod
    def weight_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("current_weight must be decimal") from None
        if not parsed.is_finite() or parsed < 0 or parsed > 100:
            raise ValueError("current_weight must be between zero and one hundred")
        return format(parsed.normalize(), "f")


class ConvictionAssessment(InvestmentStrictModel):
    """Server-computed conviction; model output cannot set this score."""
    schema_version: Literal["InvestmentConviction/v1"] = "InvestmentConviction/v1"
    score: int = Field(ge=0, le=100)
    band: ConvictionBand
    evidence_coverage: str = Field(pattern=r"^(0|1|0\.[0-9]+)$")
    committee_support: str = Field(pattern=r"^(0|1|0\.[0-9]+)$")
    data_quality: str = Field(pattern=r"^(0|1|0\.[0-9]+)$")
    blockers: tuple[str, ...] = Field(default=(), max_length=12)
    drivers: tuple[str, ...] = Field(default=(), max_length=12)
    methodology_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ConvictionAssessment":
        for name in ("evidence_coverage", "committee_support", "data_quality"):
            value = Decimal(getattr(self, name))
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if self.band is ConvictionBand.UNAVAILABLE and self.score != 0:
            raise ValueError("unavailable conviction must have zero score")
        return self


class PortfolioImpact(InvestmentStrictModel):
    """Analytical portfolio effect; deliberately excludes quantity and price orders."""
    schema_version: Literal["InvestmentPortfolioImpact/v1"] = "InvestmentPortfolioImpact/v1"
    portfolio_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    current_weight: str | None = Field(default=None, max_length=64)
    concentration_note: str | None = Field(default=None, max_length=240)
    liquidity_note: str | None = Field(default=None, max_length=240)
    analytical_allocation_range: str | None = Field(default=None, max_length=128)
    assumptions: tuple[str, ...] = Field(default=(), max_length=12)


class RecommendationQuality(InvestmentStrictModel):
    freshness: RecommendationFreshness
    data_quality: tuple[CommitteeDataQuality, ...] = Field(default=(), max_length=16)
    omissions: tuple[str, ...] = Field(default=(), max_length=16)


class InvestmentRecommendation(InvestmentStrictModel):
    """Canonical INV-09 analytical recommendation projection."""
    schema_version: Literal["InvestmentRecommendation/v1"] = "InvestmentRecommendation/v1"
    recommendation_id: str = Field(min_length=1, max_length=160, pattern=r"^investment-recommendation:[A-Za-z0-9._:-]+$")
    owner_id: int = Field(gt=0)
    security_id: str = Field(min_length=1, max_length=128)
    recommendation_type: RecommendationType
    status: RecommendationStatus = RecommendationStatus.ACTIVE
    committee_run_id: str = Field(pattern=r"^run:[A-Za-z0-9._:-]+$")
    committee_finding_id: str = Field(pattern=r"^committee:[A-Za-z0-9._:-]+$")
    portfolio_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    analysis_as_of: datetime
    recommendation_as_of: datetime
    time_horizon: TimeHorizon
    conviction: ConvictionAssessment
    thesis: str = Field(min_length=1, max_length=1600)
    rationale: str = Field(min_length=1, max_length=1600)
    supporting_evidence: tuple[RecommendationEvidence, ...] = Field(default=(), max_length=32)
    contradicting_evidence: tuple[RecommendationEvidence, ...] = Field(default=(), max_length=32)
    key_risks: tuple[str, ...] = Field(default=(), max_length=16)
    invalidation_conditions: tuple[str, ...] = Field(default=(), max_length=16)
    catalysts: tuple[str, ...] = Field(default=(), max_length=16)
    portfolio_impact: PortfolioImpact
    position_context: PortfolioPositionContext
    quality: RecommendationQuality
    review_after: datetime
    expires_at: datetime | None = None
    methodology_version: str = Field(min_length=1, max_length=64)
    model_metadata: dict[str, str] = Field(default_factory=dict, max_length=8)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    recommendation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime

    @field_validator("analysis_as_of", "recommendation_as_of", "review_after", "expires_at", "created_at")
    @classmethod
    def timestamps_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def invariants(self) -> "InvestmentRecommendation":
        if self.analysis_as_of > self.recommendation_as_of:
            raise ValueError("recommendation cannot precede analysis")
        if self.review_after < self.recommendation_as_of:
            raise ValueError("review_after cannot precede recommendation")
        if self.expires_at is not None and self.expires_at < self.review_after:
            raise ValueError("expires_at cannot precede review_after")
        evidence_ids = [item.evidence_id for item in (*self.supporting_evidence, *self.contradicting_evidence)]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("recommendation evidence IDs must be unique")
        if self.recommendation_type in {RecommendationType.HOLD, RecommendationType.WATCH} and not self.invalidation_conditions:
            raise ValueError("HOLD and WATCH require invalidation conditions")
        if self.recommendation_type is RecommendationType.WATCH and self.conviction.band is ConvictionBand.HIGH:
            raise ValueError("WATCH cannot have high conviction")
        if self.position_context.owner_id != self.owner_id:
            raise ValueError("position context owner mismatch")
        if self.portfolio_impact.portfolio_snapshot_hash != self.portfolio_snapshot_hash:
            raise ValueError("portfolio impact snapshot mismatch")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"recommendation_hash", "created_at"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "InvestmentRecommendation":
        provisional = cls.model_validate({**values, "recommendation_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "recommendation_hash": digest})


class RecommendationResult(InvestmentStrictModel):
    """Safe service result; failed gates never produce an actionable object."""
    recommendation: InvestmentRecommendation | None = None
    failure_code: RecommendationFailureCode | None = None
    failure_reason: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def coherent(self) -> "RecommendationResult":
        if (self.recommendation is None) == (self.failure_code is None):
            raise ValueError("result must contain either recommendation or failure")
        if self.failure_code is not None and not self.failure_reason:
            raise ValueError("failure requires reason")
        return self


__all__ = [
    "ConvictionAssessment", "ConvictionBand", "EvidenceRole", "InvestmentRecommendation",
    "PortfolioImpact", "PortfolioPositionContext", "PositionState", "RecommendationEvidence",
    "RecommendationFailureCode", "RecommendationFreshness", "RecommendationQuality",
    "RecommendationResult", "RecommendationStatus", "RecommendationType", "TimeHorizon",
]
