"""INV-12 typed evaluation and durable-store contracts (frozen by the design gate).

``ATLAS-INVESTMENT-INV-12-DESIGN.md`` §5–§7 define the canonical artifacts:

- ``InvestmentEvaluationArtifact/v1`` — the append-only evaluation record that
  references a frozen ``RecommendationOutcome`` (or a blocked/insufficient
  result) with replay metadata, deterministic ``input_hash``/``evaluation_hash``
  and a typed ``result_state``. Computed values are never duplicated here; they
  live in the existing ``investment_outcome_records`` payloads.
- ``StoredMarketObservation/v1`` — the durable observation-store payload that
  supersets the two pre-existing ``MarketObservation`` shapes (INV-02
  validation metadata + ``outcome_tracking`` evaluation fields). Writes
  validate with INV-02 semantics; evaluation reads project to the
  ``outcome_tracking`` shape so ``evaluate_outcome()`` is called unchanged.

Hash conventions follow the repository standard: ``canonical_payload()`` is
sorted compact JSON of the model excluding the hash field, and ``with_hash()``
computes ``sha256`` over it. Stored hashes are lowercase 64-hex.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .contracts import DataState, InvestmentStrictModel
from .market_observations import AdjustmentBasis, ObservationQuality

METHODOLOGY_VERSION = "investment-evaluation/v1"


class EvaluationState(StrEnum):
    """Lifecycle of an evaluation artifact record (design §5c).

    Rows are written once in their terminal state by the internal evaluator;
    ``pending``/``evaluable`` mirror ``OutcomeState.PENDING`` vocabulary and are
    only used by the internal evaluation request path inside one transaction.
    """

    PENDING = "pending"
    EVALUABLE = "evaluable"
    EVALUATED = "evaluated"
    BLOCKED = "blocked"


class EvaluationResultState(StrEnum):
    """Typed result vocabulary (design §5c).

    The first four values reuse ``OutcomeState`` verbatim; ``not_comparable``
    is new and belongs on the evaluation artifact only — it never appears on an
    INV-11 outcome and covers adjustment-basis or currency mismatch.
    """

    AVAILABLE = "available"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNAVAILABLE = "unavailable"
    TEMPORAL_VIOLATION = "temporal_violation"
    NOT_COMPARABLE = "not_comparable"


class EvaluationReplayState(StrEnum):
    """Deterministic re-verification result for one evaluation (design §4/§5b)."""

    MATCH = "match"
    METHODOLOGY_CHANGED = "methodology_changed"
    INPUTS_UNAVAILABLE = "inputs_unavailable"
    HASH_MISMATCH = "hash_mismatch"


HORIZONS = ("1D", "1W", "1M", "3M", "6M", "1Y")

_HASH64 = r"^[a-f0-9]{64}$"


class StoredMarketObservation(InvestmentStrictModel):
    """Canonical durable observation-store payload (design §6b)."""

    schema_version: Literal["StoredMarketObservation/v1"] = "StoredMarketObservation/v1"
    observation_id: str = Field(pattern=r"^market-observation:[a-f0-9]{64}$")
    security_id: str = Field(min_length=1, max_length=128)
    observed_value: str = Field(max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    adjustment_basis: AdjustmentBasis
    observed_at: datetime
    as_known_at: datetime
    retrieved_at: datetime
    source: str = Field(min_length=1, max_length=160)
    source_identifier: str | None = Field(default=None, max_length=160)
    state: DataState = DataState.OBSERVED
    quality: ObservationQuality
    freshness: DataState
    observation_hash: str = Field(pattern=_HASH64)

    @field_validator("observed_at", "as_known_at", "retrieved_at")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @field_validator("observed_value")
    @classmethod
    def finite_nonnegative_value(cls, value: str) -> str:
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("observed_value must be decimal") from None
        if not number.is_finite() or number < 0:
            raise ValueError("observed_value must be finite and non-negative")
        return format(number.normalize(), "f")

    @model_validator(mode="after")
    def coherent(self) -> "StoredMarketObservation":
        if self.state is not DataState.OBSERVED:
            raise ValueError("stored observations must be in observed state")
        if self.freshness is not DataState.OBSERVED:
            raise ValueError("stored observations must be fresh (observed)")
        if self.quality is ObservationQuality.INVALID:
            raise ValueError("invalid observations cannot enter the durable store")
        if self.as_known_at < self.observed_at:
            raise ValueError("as_known_at cannot precede observed_at")
        if self.retrieved_at < self.as_known_at:
            raise ValueError("retrieved_at cannot precede as_known_at")
        return self

    def canonical_payload(self) -> str:
        # ``observation_id`` is derived from ``observation_hash`` and must not
        # participate in the digest (otherwise hashing is circular).
        return json.dumps(self.model_dump(mode="json", exclude={"observation_hash", "observation_id"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "StoredMarketObservation":
        provisional = cls.model_validate({**values, "observation_hash": "0" * 64, "observation_id": "market-observation:" + "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "observation_hash": digest, "observation_id": f"market-observation:{digest}"})


class InvestmentEvaluationArtifact(InvestmentStrictModel):
    """Canonical INV-12 evaluation artifact (design §5b)."""

    schema_version: Literal["InvestmentEvaluationArtifact/v1"] = "InvestmentEvaluationArtifact/v1"
    evaluation_id: str = Field(pattern=r"^investment-evaluation:[a-f0-9]{64}$")
    owner_id: int = Field(gt=0)
    recommendation_id: str = Field(min_length=1, max_length=160)
    recommendation_hash: str = Field(pattern=_HASH64)
    decision_id: str | None = Field(default=None, min_length=1, max_length=160)
    outcome_id: str | None = Field(default=None, min_length=1, max_length=160)
    outcome_hash: str | None = Field(default=None, pattern=_HASH64)
    security_id: str = Field(min_length=1, max_length=128)
    evaluation_window_start: datetime
    evaluation_as_of: datetime
    horizon: str = Field(pattern=r"^(1D|1W|1M|3M|6M|1Y)$")
    benchmark_security_id: str | None = Field(default=None, max_length=128)
    evaluation_state: EvaluationState
    result_state: EvaluationResultState | None = None
    blocked_reason: str | None = Field(default=None, max_length=64)
    methodology_version: str = Field(min_length=1, max_length=64)
    vintage_bound: datetime
    replay_state: EvaluationReplayState = EvaluationReplayState.MATCH
    input_hash: str = Field(pattern=_HASH64)
    evaluation_hash: str = Field(pattern=_HASH64)
    created_at: datetime

    @field_validator("evaluation_window_start", "evaluation_as_of", "vintage_bound", "created_at")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("artifact timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def coherent(self) -> "InvestmentEvaluationArtifact":
        if self.evaluation_as_of < self.evaluation_window_start:
            raise ValueError("evaluation_as_of cannot precede the window start")
        if self.vintage_bound > self.evaluation_as_of:
            raise ValueError("vintage_bound cannot follow evaluation_as_of")
        if self.evaluation_state is EvaluationState.EVALUATED and self.result_state is None:
            raise ValueError("evaluated artifacts require a result state")
        if self.evaluation_state is EvaluationState.EVALUATED and (self.outcome_id is None or self.outcome_hash is None):
            raise ValueError("evaluated artifacts require an outcome reference")
        if self.evaluation_state is EvaluationState.EVALUATED and self.blocked_reason is not None:
            raise ValueError("evaluated artifacts cannot carry a blocked reason")
        if self.evaluation_state is EvaluationState.BLOCKED and self.blocked_reason is None:
            raise ValueError("blocked artifacts require a typed blocked reason")
        if self.result_state is EvaluationResultState.AVAILABLE and (self.outcome_id is None or self.outcome_hash is None):
            raise ValueError("available results require an outcome reference")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"evaluation_hash", "created_at"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "InvestmentEvaluationArtifact":
        provisional = cls.model_validate({**values, "evaluation_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "evaluation_hash": digest})


class InvestmentEvaluationReplay(InvestmentStrictModel):
    """Typed result of a deterministic replay re-verification (design §4/§17).

    Read-only output of the internal replay over one stored artifact; it is
    computed on demand and never persisted.
    """

    schema_version: Literal["InvestmentEvaluationReplay/v1"] = "InvestmentEvaluationReplay/v1"
    evaluation_id: str = Field(pattern=r"^investment-evaluation:[a-f0-9]{64}$")
    replay_state: EvaluationReplayState
    verified: bool
    evaluation_hash: str = Field(pattern=_HASH64)
    input_hash: str = Field(pattern=_HASH64)
    replayed_at: datetime

    @field_validator("replayed_at")
    @classmethod
    def replay_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("replayed_at must be timezone-aware UTC")
        return value.astimezone(UTC)


__all__ = [
    "EvaluationReplayState",
    "EvaluationResultState",
    "EvaluationState",
    "HORIZONS",
    "InvestmentEvaluationArtifact",
    "InvestmentEvaluationReplay",
    "METHODOLOGY_VERSION",
    "StoredMarketObservation",
]
