"""INV-11 immutable investment recommendation outcome tracking.

This domain module is intentionally independent of the legacy goal/forecast
persistence substrate. It tracks investment recommendations by reference,
records human decisions separately, and evaluates frozen market observations
without mutating recommendations or portfolio state.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable

from pydantic import Field, field_validator, model_validator

from .contracts import DataState, InvestmentStrictModel
from .recommendation_contracts import InvestmentRecommendation, RecommendationType
from .securities import SecurityIdentity

METHODOLOGY_VERSION = "investment-outcome/v1"


class TrackingStatus(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    EVALUATED = "evaluated"


class HumanDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"
    MODIFY = "modify"
    NO_ACTION = "no_action"


class OutcomeState(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNAVAILABLE = "unavailable"
    TEMPORAL_VIOLATION = "temporal_violation"


class ThesisStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_SUPPORTED = "not_supported"
    INCONCLUSIVE = "inconclusive"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MarketObservation(InvestmentStrictModel):
    observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    security_id: str = Field(min_length=1, max_length=128)
    price: str = Field(max_length=64)
    observed_at: datetime
    as_known_at: datetime
    state: DataState = DataState.OBSERVED

    @field_validator("price")
    @classmethod
    def decimal_price(cls, value: str) -> str:
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("price must be decimal") from None
        if not number.is_finite() or number < 0:
            raise ValueError("price must be finite and non-negative")
        return format(number.normalize(), "f")

    @field_validator("observed_at", "as_known_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def temporal(self) -> "MarketObservation":
        if self.as_known_at < self.observed_at:
            raise ValueError("as_known_at cannot precede observed_at")
        return self


class TrackedRecommendation(InvestmentStrictModel):
    schema_version: str = "TrackedInvestmentRecommendation/v1"
    tracking_id: str = Field(pattern=r"^tracked-recommendation:[a-f0-9]{64}$")
    recommendation_id: str
    recommendation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner_id: int = Field(gt=0)
    security_id: str = Field(min_length=1, max_length=128)
    action: RecommendationType
    conviction_score: int = Field(ge=0, le=100)
    created_at: datetime
    as_of: datetime
    review_at: datetime
    expires_at: datetime | None = None
    status: TrackingStatus = TrackingStatus.OPEN
    portfolio_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    committee_finding_id: str
    evidence_packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    methodology_version: str = METHODOLOGY_VERSION

    @field_validator("created_at", "as_of", "review_at", "expires_at")
    @classmethod
    def timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("tracking timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "TrackedRecommendation":
        if self.as_of > self.created_at:
            raise ValueError("tracking as_of cannot follow creation")
        if self.review_at < self.created_at:
            raise ValueError("review_at cannot precede creation")
        if self.expires_at is not None and self.expires_at < self.review_at:
            raise ValueError("expires_at cannot precede review_at")
        return self


class HumanDecisionRecord(InvestmentStrictModel):
    schema_version: str = "InvestmentDecision/v1"
    decision_id: str = Field(pattern=r"^investment-decision:[a-f0-9]{64}$")
    tracking_id: str
    recommendation_id: str
    recommendation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner_id: int = Field(gt=0)
    decision: HumanDecision
    decided_at: datetime
    rationale: str | None = Field(default=None, max_length=2000)

    @field_validator("decided_at")
    @classmethod
    def decision_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decision timestamp must be timezone-aware")
        return value.astimezone(UTC)


class RecommendationOutcome(InvestmentStrictModel):
    schema_version: str = "RecommendationOutcome/v1"
    outcome_id: str = Field(pattern=r"^recommendation-outcome:[a-f0-9]{64}$")
    tracking_id: str
    recommendation_id: str
    recommendation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner_id: int = Field(gt=0)
    security_id: str
    evaluation_as_of: datetime
    horizon: str = Field(pattern=r"^(1D|1W|1M|3M|6M|1Y)$")
    state: OutcomeState
    baseline_observation_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    evaluation_observation_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    benchmark_security_id: str | None = None
    benchmark_baseline_observation_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    benchmark_evaluation_observation_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    reference_price: str | None = None
    evaluation_price: str | None = None
    simple_return: str | None = None
    benchmark_return: str | None = None
    excess_return: str | None = None
    thesis_status: ThesisStatus
    methodology_version: str = METHODOLOGY_VERSION
    source_observation_hashes: tuple[str, ...] = ()
    outcome_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("evaluation_as_of")
    @classmethod
    def evaluation_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluation_as_of must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("reference_price", "evaluation_price", "simple_return", "benchmark_return", "excess_return")
    @classmethod
    def finite_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("outcome number must be finite")
        return format(number.normalize(), "f")


class OutcomeResult(InvestmentStrictModel):
    tracking: TrackedRecommendation
    outcome: RecommendationOutcome


def track_recommendation(recommendation: InvestmentRecommendation, *, evidence_packet_hash: str) -> TrackedRecommendation:
    payload = {"recommendation_id": recommendation.recommendation_id, "recommendation_hash": recommendation.recommendation_hash, "owner_id": recommendation.owner_id, "action": recommendation.recommendation_type.value, "as_of": recommendation.recommendation_as_of.isoformat(), "portfolio": recommendation.portfolio_snapshot_hash, "evidence": evidence_packet_hash, "methodology": METHODOLOGY_VERSION}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TrackedRecommendation(
        tracking_id=f"tracked-recommendation:{digest}", recommendation_id=recommendation.recommendation_id,
        recommendation_hash=recommendation.recommendation_hash, owner_id=recommendation.owner_id,
        security_id=recommendation.security_id, action=recommendation.recommendation_type,
        conviction_score=recommendation.conviction.score, created_at=recommendation.created_at,
        as_of=recommendation.recommendation_as_of, review_at=recommendation.review_after,
        expires_at=recommendation.expires_at, portfolio_snapshot_hash=recommendation.portfolio_snapshot_hash,
        committee_finding_id=recommendation.committee_finding_id, evidence_packet_hash=evidence_packet_hash,
    )


def record_decision(tracking: TrackedRecommendation, *, owner_id: int, decision: HumanDecision, decided_at: datetime, rationale: str | None = None) -> HumanDecisionRecord:
    if owner_id != tracking.owner_id:
        raise ValueError("decision owner mismatch")
    if decided_at.astimezone(UTC) < tracking.created_at:
        raise ValueError("decision cannot precede recommendation")
    raw = f"{tracking.tracking_id}|{tracking.recommendation_hash}|{owner_id}|{decision.value}|{decided_at.astimezone(UTC).isoformat()}|{rationale or ''}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return HumanDecisionRecord(decision_id=f"investment-decision:{digest}", tracking_id=tracking.tracking_id, recommendation_id=tracking.recommendation_id, recommendation_hash=tracking.recommendation_hash, owner_id=owner_id, decision=decision, decided_at=decided_at, rationale=rationale)


def supersede(old: TrackedRecommendation, new: TrackedRecommendation, *, owner_id: int) -> tuple[TrackedRecommendation, TrackedRecommendation]:
    if owner_id != old.owner_id or owner_id != new.owner_id:
        raise ValueError("supersession owner mismatch")
    if old.tracking_id == new.tracking_id or new.created_at <= old.created_at:
        raise ValueError("supersession must point forward to a distinct record")
    return old.model_copy(update={"status": TrackingStatus.SUPERSEDED}), new


def _choose_baseline(observations: Iterable[MarketObservation], *, security_id: str, as_of: datetime) -> MarketObservation | None:
    candidates = [item for item in observations if item.security_id == security_id and item.as_known_at <= as_of and item.observed_at <= as_of and item.state is DataState.OBSERVED]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.observed_at, item.as_known_at, item.observation_hash))
    return candidates[-1]


def _choose_evaluation(observations: Iterable[MarketObservation], *, security_id: str, as_of: datetime) -> MarketObservation | None:
    candidates = [item for item in observations if item.security_id == security_id and item.as_known_at <= as_of and item.observed_at <= as_of and item.state is DataState.OBSERVED]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.observed_at, item.as_known_at, item.observation_hash))
    return candidates[-1]


def evaluate_outcome(tracking: TrackedRecommendation, *, evaluation_as_of: datetime, observations: Iterable[MarketObservation], horizon: str, benchmark_security_id: str | None = None, benchmark_observations: Iterable[MarketObservation] = ()) -> OutcomeResult:
    if evaluation_as_of.tzinfo is None or evaluation_as_of.utcoffset() is None:
        raise ValueError("evaluation_as_of must be timezone-aware")
    evaluation_as_of = evaluation_as_of.astimezone(UTC)
    if evaluation_as_of < tracking.as_of:
        raise ValueError("evaluation cannot precede recommendation")
    all_observations = tuple(observations)
    all_observations = tuple(item for item in all_observations if item.as_known_at <= evaluation_as_of and item.observed_at <= evaluation_as_of)
    baseline = _choose_baseline(all_observations, security_id=tracking.security_id, as_of=tracking.as_of)
    baseline_zero = baseline is not None and Decimal(baseline.price) == 0
    if baseline_zero:
        baseline = None
    evaluated = _choose_evaluation(all_observations, security_id=tracking.security_id, as_of=evaluation_as_of)
    benchmark_return = None
    benchmark_base = benchmark_eval = None
    if baseline is None and baseline_zero:
        state, thesis = OutcomeState.UNAVAILABLE, ThesisStatus.INCONCLUSIVE
    elif baseline is None:
        state, thesis = OutcomeState.INSUFFICIENT_HISTORY, ThesisStatus.INSUFFICIENT_EVIDENCE
    elif evaluated is None:
        state, thesis = OutcomeState.UNAVAILABLE, ThesisStatus.INCONCLUSIVE
    elif Decimal(baseline.price) == 0:
        state, thesis = OutcomeState.UNAVAILABLE, ThesisStatus.INCONCLUSIVE
    else:
        simple = (Decimal(evaluated.price) / Decimal(baseline.price)) - Decimal(1)
        benchmark_return = None
        benchmark_base = benchmark_eval = None
        if benchmark_security_id:
            benchmark_items = tuple(item for item in benchmark_observations if item.as_known_at <= evaluation_as_of and item.observed_at <= evaluation_as_of)
            benchmark_base = _choose_baseline(benchmark_items, security_id=benchmark_security_id, as_of=tracking.as_of)
            benchmark_eval = _choose_evaluation(benchmark_items, security_id=benchmark_security_id, as_of=evaluation_as_of)
            if benchmark_base is not None and Decimal(benchmark_base.price) == 0:
                benchmark_base = None
            if benchmark_base is None or benchmark_eval is None or Decimal(benchmark_base.price) == 0:
                state, thesis = OutcomeState.UNAVAILABLE, ThesisStatus.INCONCLUSIVE
            else:
                benchmark_return = (Decimal(benchmark_eval.price) / Decimal(benchmark_base.price)) - Decimal(1)
                state, thesis = OutcomeState.AVAILABLE, ThesisStatus.SUPPORTED if _supports(tracking.action, simple, simple - benchmark_return) else ThesisStatus.PARTIALLY_SUPPORTED
        else:
            state, thesis = OutcomeState.AVAILABLE, ThesisStatus.SUPPORTED if _supports(tracking.action, simple, None) else ThesisStatus.PARTIALLY_SUPPORTED
        excess = simple - benchmark_return if benchmark_return is not None else None
        values = {"reference_price": format(Decimal(baseline.price).normalize(), "f"), "evaluation_price": format(Decimal(evaluated.price).normalize(), "f"), "simple_return": format(simple.normalize(), "f"), "benchmark_return": format(benchmark_return.normalize(), "f") if benchmark_return is not None else None, "excess_return": format(excess.normalize(), "f") if excess is not None else None}
    if baseline is None or evaluated is None or state is not OutcomeState.AVAILABLE:
        values = {"reference_price": None, "evaluation_price": None, "simple_return": None, "benchmark_return": None, "excess_return": None}
    hashes = tuple(item.observation_hash for item in (baseline, evaluated) if item is not None)
    if benchmark_base is not None:
        hashes += tuple(item.observation_hash for item in (benchmark_base, benchmark_eval) if item is not None)
    data = {"tracking": tracking.tracking_id, "recommendation": tracking.recommendation_hash, "evaluation": evaluation_as_of.isoformat(), "horizon": horizon, "hashes": hashes, "values": values, "state": state.value, "thesis": thesis.value, "methodology": METHODOLOGY_VERSION}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    outcome = RecommendationOutcome(outcome_id=f"recommendation-outcome:{digest}", tracking_id=tracking.tracking_id, recommendation_id=tracking.recommendation_id, recommendation_hash=tracking.recommendation_hash, owner_id=tracking.owner_id, security_id=tracking.security_id, evaluation_as_of=evaluation_as_of, horizon=horizon, state=state, baseline_observation_hash=baseline.observation_hash if baseline else None, evaluation_observation_hash=evaluated.observation_hash if evaluated else None, benchmark_security_id=benchmark_security_id, benchmark_baseline_observation_hash=benchmark_base.observation_hash if benchmark_base else None, benchmark_evaluation_observation_hash=benchmark_eval.observation_hash if benchmark_eval else None, **values, thesis_status=thesis, source_observation_hashes=hashes, outcome_hash=digest)
    return OutcomeResult(tracking=tracking, outcome=outcome)


def _supports(action: RecommendationType, simple: Decimal, excess: Decimal | None) -> bool:
    if action in {RecommendationType.BUY, RecommendationType.ADD}:
        return simple > 0
    if action is RecommendationType.HOLD:
        return (excess is not None and excess >= 0) or (excess is None and simple >= 0)
    if action in {RecommendationType.REDUCE, RecommendationType.SELL}:
        return simple <= 0
    return abs(simple) < Decimal("0.05")


def update_status(tracking: TrackedRecommendation, *, at: datetime, evaluated: bool = False) -> TrackedRecommendation:
    at = at.astimezone(UTC)
    if evaluated:
        status = TrackingStatus.EVALUATED
    elif tracking.expires_at is not None and at >= tracking.expires_at:
        status = TrackingStatus.EXPIRED
    elif at >= tracking.review_at:
        status = TrackingStatus.REVIEWED
    else:
        status = tracking.status
    return tracking.model_copy(update={"status": status})


__all__ = ["HumanDecision", "HumanDecisionRecord", "MarketObservation", "METHODOLOGY_VERSION", "OutcomeResult", "OutcomeState", "RecommendationOutcome", "ThesisStatus", "TrackedRecommendation", "TrackingStatus", "evaluate_outcome", "record_decision", "supersede", "track_recommendation", "update_status"]
