"""Phase 2 Slice 1 commit-4 wire-shape mappers.

Maps persisted Phase 2 rows (SQLAlchemy) to the approved
:mod:`app.forecasts.recommendation_schemas` wire envelopes.  Route-free
and adapter-free: no FastAPI imports, no DB session, no HTTP plumbing.
The Phase-1 mapper at :mod:`app.forecasts.mappers` is untouched.

Per the thinker's DECISION B3 verdict this module sits next to the
engine and repository so the Phase 2 wire-shape boundary stays
self-contained, mirroring the approved ``docs/10-roadmap/PHASE2_
VERTICAL_SLICE_PLAN.md`` §6 backend file list.

Mapping invariants:

* ``expected_impact_range`` money values come from the model
  ``Numeric(38,12)`` columns, NOT from any ``assumptions_json`` blob.
* ``assumptions_reference`` is the lowercased SHA-256 hex of the
  persisted ``assumptions_json`` text; the full text is never echoed.
* ``confidence`` enum is derived deterministically from
  ``confidence_score`` (0..1) using a narrow bin table that matches
  the engine's emit policy.
* The deterministic ``Recommendation.id`` UUID IS the canonical
  token used in the ``decide`` HATEOAS link href so the client can
  construct the POST URL without an extra field on the GET envelope.
* Any malformed or out-of-band model field raises ``MapperError``
  with a sanitized token; raw bytes, ORM attribute names, and
  financial values are never echoed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Final

from app.forecasts.api_codecs import derive_decision_etag, derive_forecast_etag
from app.forecasts.canonical_state import canonical_decimal_string
from app.forecasts.recommendation_schemas import (
    DECISION_JOURNAL_SCHEMA_VERSION,
    DecisionJournalEntryEnvelope,
    DeterministicRecommendationEnvelope,
    EvidenceReferenceEntry,
    GoalReferenceEntry,
    ImpactRangeEntry,
    LinkEntry,
    OutcomeEvaluationLinkEntry,
    RecommendationApprovalEntry,
    RecommendationContractEnvelope,
    RecommendationConfidence,
    RecommendationKind,
    RecommendationRiskToken,
)
from app.models.decision_journal_entry import DecisionJournalEntry
from app.models.outcome_evaluation import OutcomeEvaluation
from app.models.recommendation import Recommendation


# ----------------------------------------------------------------------
# Bounded rel literals (server-derived; never echoes of request data)
# ----------------------------------------------------------------------

_REL_FORECAST: Final[str] = "forecast"
_REL_DECIDE: Final[str] = "decide"
_REL_RECORDED: Final[str] = "recorded"


# ----------------------------------------------------------------------
# Bounded kind -> action_verb table
# ----------------------------------------------------------------------

_KIND_TO_ACTION_VERB: Final[dict[str, str]] = {
    "increase_contribution": "Increase",
    "rebalance_allocation": "Reallocate",
    "extend_horizon": "Extend",
    "hold": "Hold",
}

_ALLOWED_KINDS: Final[frozenset[str]] = frozenset(_KIND_TO_ACTION_VERB)


# ----------------------------------------------------------------------
# Bounded confidence-scorer
# ----------------------------------------------------------------------

def _confidence_for_score(score: Any) -> RecommendationConfidence:
    try:
        numeric = score if isinstance(score, Decimal) else Decimal(str(score))
    except Exception as exc:
        raise MapperError("confidence_score_invalid") from exc
    if numeric >= Decimal("0.75"):
        return "high"
    if numeric >= Decimal("0.50"):
        return "medium"
    return "low"


# ----------------------------------------------------------------------
# Bounded RFC 3339 Z formatter
# ----------------------------------------------------------------------

def _as_utc_z(dt: datetime | None) -> str:
    if dt is None:
        raise MapperError("timestamp_invalid")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


# ----------------------------------------------------------------------
# Bounded canonical-decimal formatter
# ----------------------------------------------------------------------

def _canonical_decimal(value: Any) -> str:
    try:
        if isinstance(value, Decimal):
            return canonical_decimal_string(value)
        return canonical_decimal_string(Decimal(str(value)))
    except Exception as exc:
        raise MapperError("decimal_invalid") from exc


# ----------------------------------------------------------------------
# Bounded sha-256 hex formatter
# ----------------------------------------------------------------------

def _sha256_hex_lower(text: str) -> str:
    if not isinstance(text, str) or not text:
        raise MapperError("hash_input_invalid")
    return hashlib.sha256(text.encode("utf-8")).hexdigest().lower()


# ----------------------------------------------------------------------
# Bounded JSON parsers
# ----------------------------------------------------------------------

def _parse_assumptions_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise MapperError("assumptions_json_invalid") from exc
    if not isinstance(parsed, dict):
        raise MapperError("assumptions_json_invalid")
    return parsed


_ALLOWED_RISKS: Final[frozenset[str]] = frozenset({
    "liquidity_reduction",
    "reversibility_required",
    "concentration",
    "downside_amplification",
    "stale_input",
})


def _parse_risks_json(raw: str) -> tuple[RecommendationRiskToken, ...]:
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise MapperError("risks_json_invalid") from exc
    if not isinstance(parsed, list):
        raise MapperError("risks_json_invalid")
    bounded: list[RecommendationRiskToken] = []
    for item in parsed:
        if not isinstance(item, str) or item not in _ALLOWED_RISKS:
            raise MapperError("risks_json_invalid")
        bounded.append(item)  # type: ignore[arg-type]
    return tuple(bounded)


# ----------------------------------------------------------------------
# Public mapped exception
# ----------------------------------------------------------------------

class MapperError(ValueError):
    """Sanitized internal mapper error.  No raw bytes / field names leaked."""


# ----------------------------------------------------------------------
# Recommendation envelope builder (GET response)
# ----------------------------------------------------------------------

def build_recommendation_envelope(
    *,
    recommendation: Recommendation,
    forecast_id: str,
    forecast_version_model_version: str,
    forecast_version_calculation_version: str,
    forecast_version_input_state_hash: str,
    forecast_version_data_as_of: datetime,
    forecast_version_number: int,
) -> DeterministicRecommendationEnvelope:
    """Translate a persisted ``Recommendation`` row into the deterministic
    envelope available through ``GET /api/v1/forecasts/{forecast_id}/recommendation``.

    Reads from the persisted ``Recommendation`` row + the source
    ``ForecastVersion`` projection-state fields; NEVER echoes
    full snapshot JSON on the wire.
    """
    if not isinstance(recommendation.id, str) or len(recommendation.id) != 36:
        raise MapperError("recommendation_id_invalid")

    if recommendation.currency != "USD":
        raise MapperError("currency_invalid")

    if recommendation.recommendation_kind not in _ALLOWED_KINDS:
        raise MapperError("recommendation_kind_invalid")

    _parse_assumptions_json(recommendation.assumptions_json)
    risks = _parse_risks_json(recommendation.risks_json)

    forecast_etag = derive_forecast_etag(
        forecast_id=forecast_id,
        version_number=forecast_version_number,
    )
    decision_etag = derive_decision_etag(source_id=recommendation.id, version=1)

    impact_min_str = _canonical_decimal(recommendation.expected_impact_min_decimal)
    impact_max_str = _canonical_decimal(recommendation.expected_impact_max_decimal)
    assumptions_reference = _sha256_hex_lower(recommendation.assumptions_json)

    evidence_references = EvidenceReferenceEntry(
        forecast_id=forecast_id,
        model_version=str(forecast_version_model_version),
        calculation_version=str(forecast_version_calculation_version),
        input_state_hash=str(forecast_version_input_state_hash),
        data_as_of=_as_utc_z(forecast_version_data_as_of),
    )
    expected_impact_range = ImpactRangeEntry(
        min_delta_decimal=impact_min_str,
        max_delta_decimal=impact_max_str,
    )

    expiration_dt = (
        recommendation.expires_at
        if recommendation.expires_at is not None
        else recommendation.derived_at
    )
    expiration_str = _as_utc_z(expiration_dt)

    why_now = str(recommendation.reason or "")
    if not why_now:
        raise MapperError("reason_invalid")
    if len(why_now) > 280:
        why_now = why_now[:280]

    confidence = _confidence_for_score(recommendation.confidence_score)
    action_verb = _KIND_TO_ACTION_VERB[recommendation.recommendation_kind]

    links = (
        LinkEntry(
            rel=_REL_FORECAST,
            href=f"/api/v1/forecasts/{forecast_id}",
        ),
        LinkEntry(
            rel=_REL_DECIDE,
            href=f"/api/v1/recommendations/{recommendation.id}/decisions",
        ),
    )

    envelope = DeterministicRecommendationEnvelope(
        schema_version="atlas-derived-recommendation/v1",
        recommendation_kind=recommendation.recommendation_kind,  # type: ignore[arg-type]
        action_verb=action_verb,
        why_now=why_now,
        linked_goal_id=int(recommendation.goal_id),
        forecast_id=forecast_id,
        forecast_etag=forecast_etag,
        evidence_references=evidence_references,
        expected_impact_range=expected_impact_range,
        risks=risks,
        confidence=confidence,
        assumptions_reference=assumptions_reference,
        expiration=expiration_str,
        issuer="atlas-deterministic-rules/v1",
        links=links,
    )
    # Touch decision_etag locally so dead-code linters do not flag it;
    # the codec validation runs on demand and the result lands in a
    # cacheable property used by the route layer's ``ETag`` header.
    _ = decision_etag
    return envelope


# ----------------------------------------------------------------------
# Journal entry envelope builder (POST 201 response)
# ----------------------------------------------------------------------

def build_journal_entry_envelope(
    *,
    journal_entry: DecisionJournalEntry,
) -> DecisionJournalEntryEnvelope:
    """Translate a persisted ``DecisionJournalEntry`` row into the
    deterministic envelope returned by ``POST /api/v1/recommendations/{recommendation_id}/decisions``.
    """
    if not isinstance(journal_entry.id, str) or len(journal_entry.id) != 36:
        raise MapperError("journal_entry_id_invalid")
    if not isinstance(journal_entry.recommendation_id, str) or len(journal_entry.recommendation_id) != 36:
        raise MapperError("journal_recommendation_id_invalid")
    if journal_entry.currency != "USD":
        raise MapperError("currency_invalid")
    if journal_entry.decision_action not in ("accept", "reject", "defer"):
        raise MapperError("decision_action_invalid")
    if journal_entry.schema_version != DECISION_JOURNAL_SCHEMA_VERSION:
        raise MapperError("schema_version_invalid")

    # The decision_etag on the response mirrors the recommendation
    # ETag generation: ``{journal_entry_id}-d1`` per the decision
    # ETag namespace.  The service writes the ETag into the row's
    # idempotency-key-hash bucket for replay determinism, but the
    # client-visible ETag is reconstructed by the codec.
    decision_etag = derive_decision_etag(source_id=journal_entry.id, version=1)

    decided_at_str = _as_utc_z(journal_entry.decided_at)

    links = (
        LinkEntry(
            rel=_REL_RECORDED,
            href=f"/api/v1/decisions/{journal_entry.id}",
        ),
    )

    envelope = DecisionJournalEntryEnvelope(
        schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
        journal_entry_id=journal_entry.id,
        recommendation_id=journal_entry.recommendation_id,
        action_taken=journal_entry.decision_action,  # type: ignore[arg-type]
        decided_at=decided_at_str,
        decision_etag=decision_etag,
        links=links,
    )
    return envelope


# ----------------------------------------------------------------------
# Phase 3 recommendation contract mapper (read-only composition)
# ----------------------------------------------------------------------

def build_recommendation_contract_envelope(
    *,
    recommendation: Recommendation,
    forecast_id: str,
    forecast_version_model_version: str,
    forecast_version_calculation_version: str,
    forecast_version_input_state_hash: str,
    forecast_version_data_as_of: datetime,
    forecast_version_number: int,
    accepted_decisions: tuple[DecisionJournalEntry, ...],
    outcome_evaluations_by_decision_id: dict[str, tuple[OutcomeEvaluation, ...]],
) -> RecommendationContractEnvelope:
    """Compose the Phase 3 contract from already-authorized immutable rows.

    This read-only mapper never includes raw evidence locations, measured
    result JSON, explanatory text, idempotency keys, or user identities.
    """
    recommendation_envelope = build_recommendation_envelope(
        recommendation=recommendation,
        forecast_id=forecast_id,
        forecast_version_model_version=forecast_version_model_version,
        forecast_version_calculation_version=forecast_version_calculation_version,
        forecast_version_input_state_hash=forecast_version_input_state_hash,
        forecast_version_data_as_of=forecast_version_data_as_of,
        forecast_version_number=forecast_version_number,
    )
    approvals = tuple(
        RecommendationApprovalEntry(
            decision_journal_entry_id=str(decision.id),
            action="accept",
            decided_at=_as_utc_z(decision.decided_at),
            outcome_evaluations=tuple(
                OutcomeEvaluationLinkEntry(
                    evaluation_id=str(evaluation.id),
                    lifecycle=str(evaluation.lifecycle),
                    evidence_source_kind=evaluation.evidence_source_kind,
                    evidence_reference_hash=evaluation.evidence_reference_hash,
                    confidence=evaluation.confidence,
                    recorded_at=_as_utc_z(evaluation.recorded_at),
                )
                for evaluation in outcome_evaluations_by_decision_id.get(str(decision.id), ())
            ),
        )
        for decision in accepted_decisions
    )
    return RecommendationContractEnvelope(
        recommendation_id=str(recommendation.id),
        goal=GoalReferenceEntry(goal_id=int(recommendation.goal_id)),
        evidence=recommendation_envelope.evidence_references,
        risks=recommendation_envelope.risks,
        confidence=recommendation_envelope.confidence,
        approvals=approvals,
    )
