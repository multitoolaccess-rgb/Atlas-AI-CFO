"""Bounded Pydantic schemas for the Phase 2 decision-journal + recommendation API.

Single rewrite boundary for the wire shapes the Rules Service ships under:

- ``GET  /api/v1/forecasts/{forecast_id}/recommendation``  (deterministic derivation)
- ``POST /api/v1/recommendations/{recommendation_id}/decisions`` (append-only journal)

Phase-2 invariants enforced here are inherited verbatim from
``services.rules-service.app.forecasts.schemas`` plus:

- Top-level ``schema_version`` literal is the single source of truth for
  client-side version drift detection (planning nit 2) and is the only
  shape-stable identifier for contract evolution.
- Distinct ``RecommendationNotFoundEnvelope`` so cross-user 404 on the
  journal endpoint preserves semantic tightness (planning nit 1).
- ``DecisionJournalSubmitRequest`` enforces ``extra='forbid'`` so the
  server never echoes client financial state, assumption overrides, or
  any field beyond ``{action, decision_etag}`` (planning AC8).
- All impact-range money values remain canonical decimal strings; no
  float, no exponent, no insignificant zeros (``canonical_decimal_string``).
- Every model uses ``extra='forbid'`` so a future leak of a financial
  field via a new attribute is blocked at the schema layer.
- Decision ETag uses the bounded ``-d<n>`` form so the recommendation
  namespace is unambiguously distinct from the forecast ``-v<n>`` form.

No Phase-1 financial-mathematics behavior is changed here.  The schema
file is the rewrite boundary; ORM, derivation, and route layers all
compose these ``BaseModel`` RO classes directly.
"""
from __future__ import annotations

import re
from typing import Any, Final, Literal

from pydantic import BaseModel, Field, field_validator

from app.forecasts.canonical_state import validate_canonical_decimal
from app.forecasts.schemas import (
    _check_bare_etag,
    _check_sha256_hex,
    _check_utc_rfc3339_z,
    _check_uuid_lower,
    _phase1_request_config,
    _phase1_response_config,
)


# ============================================================
# Schema version literals (top-level schema_version convention)
# ============================================================

RECOMMENDATION_SCHEMA_VERSION: Final[str] = "atlas-derived-recommendation/v1"
DECISION_JOURNAL_SCHEMA_VERSION: Final[str] = "atlas-decision-journal-entry/v1"
RECOMMENDATION_CONTRACT_SCHEMA_VERSION: Final[str] = "atlas-recommendation-contract/v1"

# Issuer literal for the deterministic (no-LLM) recommendation engine.
DETERMINISTIC_RULES_ISSUER: Final[Literal["atlas-deterministic-rules/v1"]] = (
    "atlas-deterministic-rules/v1"
)


# ============================================================
# Bounded decision ETag (distinct from forecast ETag form)
# ============================================================

_DECISION_ETAG_BARE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-d[1-9][0-9]{0,9}$"
)


def _check_decision_etag_bare(value: Any) -> str:
    """Validate a bare decision ETag (uuid-d{n}). Distinct from the forecast
    ``-v{n}`` form so the two namespaces cannot collide."""
    if (
        not isinstance(value, str)
        or not _DECISION_ETAG_BARE.fullmatch(value)
        or len(value) > 96
    ):
        raise ValueError("must be a bare decision ETag (uuid-d<n>)")
    return value


# ============================================================
# Stable error code constants
# ============================================================

ERROR_CODE_RECOMMENDATION_NOT_FOUND: Final[str] = "recommendation_not_found"
ERROR_CODE_DECISION_CONFLICT: Final[str] = "decision_version_conflict"


# ============================================================
# HATEOAS link entry (bounded rel set; server-relative href under /api/v1/)
# ============================================================

_REL_VALUES: Final[tuple[str, ...]] = (
    "self",
    "forecast",
    "decide",
    "goal",
    "recorded",
)


class LinkEntry(BaseModel):
    """Bounded HATEOAS link entry. ``href`` must be a server-relative
    path under ``/api/v1/`` (no absolute URLs, no schemes, no query
    strings). The bounded ``rel`` literal prevents any future leak of a
    financial-bearing endpoint name through the wire shape."""

    model_config = _phase1_response_config()

    rel: str = Field(
        ...,
        min_length=1,
        max_length=16,
        description=f"Bounded link relation literal; one of {_REL_VALUES!r}.",
    )
    href: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Server-relative path under /api/v1/.",
    )

    @field_validator("rel")
    @classmethod
    def _rel_must_be_bounded(cls, value: Any) -> str:
        if value not in _REL_VALUES:
            raise ValueError(f"rel must be one of {_REL_VALUES!r}")
        return value

    @field_validator("href")
    @classmethod
    def _href_must_be_server_relative(cls, value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value.startswith("/api/v1/")
            or "://" in value
            or "?" in value
            or "#" in value
        ):
            raise ValueError("href must be a server-relative path under /api/v1/")
        return value


# ============================================================
# Sanitized provenance / evidence fragment
# ============================================================

class EvidenceReferenceEntry(BaseModel):
    """Provenance fragment embedded in recommendation envelopes. Carries NO
    Decimal money payload, NO snapshot JSON, NO raw idempotency-key plaintext,
    and NO statement-level data - only bounded identity strings."""

    model_config = _phase1_response_config()

    forecast_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Lowercase canonical UUID of the source forecast.",
    )
    model_version: str = Field(..., min_length=1, max_length=64)
    calculation_version: str = Field(..., min_length=1, max_length=64)
    input_state_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Lowercase SHA-256 hex digest of the canonical projection state.",
    )
    data_as_of: str = Field(..., description="UTC RFC 3339 Z timestamp.")

    @field_validator("forecast_id")
    @classmethod
    def _forecast_id_uuid(cls, value: Any) -> str:
        return _check_uuid_lower(value)

    @field_validator("input_state_hash")
    @classmethod
    def _input_state_hash_sha(cls, value: Any) -> str:
        return _check_sha256_hex(value)

    @field_validator("data_as_of")
    @classmethod
    def _data_as_of_rfc3339(cls, value: Any) -> str:
        return _check_utc_rfc3339_z(value)


# ============================================================
# Canonical Decimal-string impact range
# ============================================================

class ImpactRangeEntry(BaseModel):
    """Bounded canonical-decimal impact range (min, max). Preserves the
    Phase 1 Decimal-string end-to-end contract (``canonical_decimal_string``);
    no float, no exponent, no insignificant zeros, no whitespace, no
    NaN or Infinity, no scientific notation.

    Reuses ``validate_canonical_decimal`` from the canonical-state v1
    contract so this envelope inherits the canonical-state length cap,
    total-digit + fractional-scale bounds, and MAX_ABSOLUTE_MONEY guard.
    A raw ``decimal.InvalidOperation`` cannot leak to the wire; the
    per-field ``type`` becomes ``value_error``.
    """

    model_config = _phase1_response_config()

    min_delta_decimal: str
    max_delta_decimal: str

    _min_decimal = field_validator("min_delta_decimal")(validate_canonical_decimal)
    _max_decimal = field_validator("max_delta_decimal")(validate_canonical_decimal)


# ============================================================
# Deterministic Recommendation Envelope (response, frozen)
# ============================================================

RecommendationKind = Literal[
    "increase_contribution",
    "rebalance_allocation",
    "extend_horizon",
    "hold",
]

RecommendationConfidence = Literal["high", "medium", "low"]

RecommendationRiskToken = Literal[
    "liquidity_reduction",
    "reversibility_required",
    "concentration",
    "downside_amplification",
    "stale_input",
]


class DeterministicRecommendationEnvelope(BaseModel):
    """Phase 2 deterministic recommendation contract.

    Mirrors ``ForecastResponse`` envelope discipline: frozen RO model,
    ``extra='forbid'``, top-level ``schema_version`` literal is the
    single source of truth for client-side version drift detection
    (planning nit 2).  Money payload appears only as canonical decimal
    strings inside ``expected_impact_range``; the rest of the envelope
    is identity-bearing only.
    """

    model_config = _phase1_response_config()

    schema_version: Literal[RECOMMENDATION_SCHEMA_VERSION] = RECOMMENDATION_SCHEMA_VERSION
    recommendation_kind: RecommendationKind
    action_verb: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="One bounded verb phrase (e.g., 'Increase', 'Reallocate', 'Extend', 'Hold').",
    )
    why_now: str = Field(..., min_length=1, max_length=280)
    linked_goal_id: int = Field(..., ge=1, le=9_223_372_036_854_775_807)
    forecast_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Lowercase canonical UUID of the source forecast.",
    )
    forecast_etag: str = Field(
        ...,
        min_length=1,
        max_length=96,
        description="Bare server-derived forecast ETag (uuid-v<n>).",
    )
    evidence_references: EvidenceReferenceEntry
    expected_impact_range: ImpactRangeEntry
    risks: tuple[RecommendationRiskToken, ...] = Field(
        default_factory=tuple,
        max_length=4,
        description="Bounded set of risk tokens; empty tuple allowed.",
    )
    confidence: RecommendationConfidence
    assumptions_reference: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Lowercase SHA-256 hex digest of the assumption snapshot.",
    )
    expiration: str = Field(
        ...,
        min_length=20,
        max_length=32,
        description="UTC RFC 3339 Z timestamp; refresh-by / stale-by deadline.",
    )
    issuer: Literal["atlas-deterministic-rules/v1"] = DETERMINISTIC_RULES_ISSUER
    links: tuple[LinkEntry, ...] = Field(..., min_length=1, max_length=8)

    @field_validator("forecast_id")
    @classmethod
    def _forecast_id_uuid(cls, value: Any) -> str:
        return _check_uuid_lower(value)

    @field_validator("forecast_etag")
    @classmethod
    def _forecast_etag_bare(cls, value: Any) -> str:
        return _check_bare_etag(value)

    @field_validator("assumptions_reference")
    @classmethod
    def _assumptions_reference_sha(cls, value: Any) -> str:
        return _check_sha256_hex(value)

    @field_validator("expiration")
    @classmethod
    def _expiration_rfc3339(cls, value: Any) -> str:
        return _check_utc_rfc3339_z(value)


# ============================================================
# Decision Journal Strict Submit Request (request, mutable)
# ============================================================

DecisionAction = Literal["accept", "reject", "defer"]


class DecisionJournalSubmitRequest(BaseModel):
    """Strict POST body for ``/api/v1/recommendations/{recommendation_id}/decisions``.

    Accepts ONLY ``action`` (``accept|reject|defer``) and ``decision_etag``
    (bare decision ETag ``uuid-d<n>``). No money, no assumption overrides,
    no body fields beyond these two (planning AC8).

    ``extra='forbid'`` ensures any unknown field is rejected at the
    schema layer rather than reaching the derivation or persistence
    boundary - the trusted-generation contract is preserved verbatim.
    """

    model_config = _phase1_request_config()

    action: DecisionAction
    decision_etag: str = Field(
        ...,
        min_length=1,
        max_length=96,
        description="Bare server-derived decision ETag (uuid-d<n>).",
    )

    @field_validator("decision_etag")
    @classmethod
    def _decision_etag_bare(cls, value: Any) -> str:
        return _check_decision_etag_bare(value)


# ============================================================
# Decision Journal Entry Envelope (response, frozen)
# ============================================================

class DecisionJournalEntryEnvelope(BaseModel):
    """Phase 2 bounded append-only decision-journal response. Frozen RO
    with ``schema_version`` literal at top level (planning nit 2 so the
    client can short-circuit on contract drift). No money payload;
    ``decision_etag`` is the bare ETag the client saw at read time."""

    model_config = _phase1_response_config()

    schema_version: Literal[DECISION_JOURNAL_SCHEMA_VERSION] = (
        DECISION_JOURNAL_SCHEMA_VERSION
    )
    journal_entry_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Lowercase canonical UUID of the appended row.",
    )
    recommendation_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Lowercase canonical UUID of the source recommendation.",
    )
    action_taken: DecisionAction
    decided_at: str = Field(
        ...,
        min_length=20,
        max_length=32,
        description="UTC RFC 3339 Z timestamp (microsecond-truncated).",
    )
    decision_etag: str = Field(
        ...,
        min_length=1,
        max_length=96,
        description="Bare decision ETag echoed from the request.",
    )
    links: tuple[LinkEntry, ...] = Field(..., min_length=1, max_length=8)

    @field_validator("journal_entry_id", "recommendation_id")
    @classmethod
    def _uuid_lower(cls, value: Any) -> str:
        return _check_uuid_lower(value)

    @field_validator("decision_etag")
    @classmethod
    def _decision_etag_bare(cls, value: Any) -> str:
        return _check_decision_etag_bare(value)

    @field_validator("decided_at")
    @classmethod
    def _decided_at_rfc3339(cls, value: Any) -> str:
        return _check_utc_rfc3339_z(value)


# ============================================================
# Phase 3 goal-linked recommendation contract (read-only)
# ============================================================

class GoalReferenceEntry(BaseModel):
    """Bounded goal linkage; financial goal detail stays in its own API."""

    model_config = _phase1_response_config()
    goal_id: int = Field(..., ge=1, le=9_223_372_036_854_775_807)


class OutcomeEvaluationLinkEntry(BaseModel):
    """Privacy-safe linkage to an immutable outcome evaluation.

    The reference is an opaque server-derived SHA-256 hash. Raw evidence
    locations and measured result payloads are deliberately absent.
    """

    model_config = _phase1_response_config()
    evaluation_id: str = Field(..., min_length=36, max_length=36)
    lifecycle: Literal["pending", "not_yet_measurable", "measured"]
    evidence_source_kind: Literal[
        "forecast_projection", "account_balance_delta", "transaction_pattern"
    ] | None = None
    evidence_reference_hash: str | None = Field(default=None, min_length=64, max_length=64)
    confidence: RecommendationConfidence | None = None
    recorded_at: str = Field(..., min_length=20, max_length=32)

    @field_validator("evaluation_id")
    @classmethod
    def _evaluation_id_uuid(cls, value: Any) -> str:
        return _check_uuid_lower(value)

    @field_validator("evidence_reference_hash")
    @classmethod
    def _evidence_reference_hash_sha(cls, value: Any) -> str | None:
        return None if value is None else _check_sha256_hex(value)

    @field_validator("recorded_at")
    @classmethod
    def _recorded_at_rfc3339(cls, value: Any) -> str:
        return _check_utc_rfc3339_z(value)


class RecommendationApprovalEntry(BaseModel):
    """One accepted append-only decision and its linked evaluations."""

    model_config = _phase1_response_config()
    decision_journal_entry_id: str = Field(..., min_length=36, max_length=36)
    action: Literal["accept"] = "accept"
    decided_at: str = Field(..., min_length=20, max_length=32)
    outcome_evaluations: tuple[OutcomeEvaluationLinkEntry, ...] = Field(default_factory=tuple)

    @field_validator("decision_journal_entry_id")
    @classmethod
    def _decision_id_uuid(cls, value: Any) -> str:
        return _check_uuid_lower(value)

    @field_validator("decided_at")
    @classmethod
    def _approval_decided_at_rfc3339(cls, value: Any) -> str:
        return _check_utc_rfc3339_z(value)


class RecommendationContractEnvelope(BaseModel):
    """Read-only Phase 3 linkage across immutable recommendation ledgers."""

    model_config = _phase1_response_config()
    schema_version: Literal[RECOMMENDATION_CONTRACT_SCHEMA_VERSION] = RECOMMENDATION_CONTRACT_SCHEMA_VERSION
    recommendation_id: str = Field(..., min_length=36, max_length=36)
    goal: GoalReferenceEntry
    evidence: EvidenceReferenceEntry
    risks: tuple[RecommendationRiskToken, ...] = Field(default_factory=tuple, max_length=4)
    confidence: RecommendationConfidence
    approvals: tuple[RecommendationApprovalEntry, ...] = Field(default_factory=tuple)

    @field_validator("recommendation_id")
    @classmethod
    def _recommendation_id_uuid(cls, value: Any) -> str:
        return _check_uuid_lower(value)


# ============================================================
# Recommendation-not-found envelope (planning nit 1)
# ============================================================

class RecommendationNotFoundEnvelope(BaseModel):
    """404 envelope returned by the journal POST when the recommendation
    is missing OR owned by a different user. Semantically distinct from
    ``ForecastNotFoundEnvelope`` so the UI client can render a tighter
    routing path; the indistinguishability-vs-cross-user property is
    preserved at the wire-level (same code family, no leaked identity).
    """

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_RECOMMENDATION_NOT_FOUND] = ERROR_CODE_RECOMMENDATION_NOT_FOUND
    message: Literal["Recommendation not found."] = "Recommendation not found."


# ============================================================
# 409 conflict envelopes (decision_etag staleness)
# ============================================================

class DecisionConflictEnvelope(BaseModel):
    """409 envelope returned when the client-supplied ``decision_etag``
    does not match the server-derived latest immutable decision_etag.
    Carries the current decision_etag so the UI can refresh and retry."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_DECISION_CONFLICT] = ERROR_CODE_DECISION_CONFLICT
    message: Literal["Decision etag conflict."] = "Decision etag conflict."
    current_etag: str = Field(
        ...,
        min_length=1,
        max_length=96,
        description="Bare server-derived current decision ETag.",
    )

    @field_validator("current_etag")
    @classmethod
    def _current_etag_bare(cls, value: Any) -> str:
        return _check_decision_etag_bare(value)


__all__ = [
    "RECOMMENDATION_SCHEMA_VERSION",
    "DECISION_JOURNAL_SCHEMA_VERSION",
    "RECOMMENDATION_CONTRACT_SCHEMA_VERSION",
    "DETERMINISTIC_RULES_ISSUER",
    "ERROR_CODE_RECOMMENDATION_NOT_FOUND",
    "ERROR_CODE_DECISION_CONFLICT",
    "RecommendationKind",
    "RecommendationConfidence",
    "RecommendationRiskToken",
    "DecisionAction",
    "LinkEntry",
    "EvidenceReferenceEntry",
    "ImpactRangeEntry",
    "DeterministicRecommendationEnvelope",
    "DecisionJournalSubmitRequest",
    "DecisionJournalEntryEnvelope",
    "GoalReferenceEntry",
    "OutcomeEvaluationLinkEntry",
    "RecommendationApprovalEntry",
    "RecommendationContractEnvelope",
    "RecommendationNotFoundEnvelope",
    "DecisionConflictEnvelope",
]
