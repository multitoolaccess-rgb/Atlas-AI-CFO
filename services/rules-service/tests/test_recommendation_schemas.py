"""Focused contract tests for the Phase 2 recommendation + decision-journal envelopes.

The schemas live in ``services.rules-service.app.forecasts.recommendation_schemas``.
These tests are bounded to the wire-shape contract; route, ORM, and derivation
behavior are exercised in their own test files.

Coverage invariants proven here:

- Top-level ``schema_version`` literals are the single source of truth for
  client-side version drift detection (planning nit 2).
- ``RecommendationNotFoundEnvelope`` is distinct from the Phase-1
  ``ForecastNotFoundEnvelope`` ``code`` literal (planning nit 1).
- Every response model is ``extra='forbid'`` and frozen (the request body
  is ``extra='forbid'`` and mutable per Phase-1 convention).
- Decision ETag uses the bounded ``-d<n>`` form so the decision namespace
  is unambiguously distinct from the forecast ``-v<n>`` form.
- Risk tokens, recommendation kinds, and confidence levels are tightly
  bounded to the literal sets enumerated in the Phase 2 plan.
- Impact-range money values are stress-tested as canonical decimal strings;
  no float, no exponent, no insignificant zeros.
- Sensitive-data invariants: validators reject any sentinel that could
  leak a money payload, account detail, transaction, or statement.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid

import pytest
from pydantic import ValidationError

from app.forecasts.recommendation_schemas import (
    DECISION_JOURNAL_SCHEMA_VERSION,
    DETERMINISTIC_RULES_ISSUER,
    ERROR_CODE_DECISION_CONFLICT,
    ERROR_CODE_RECOMMENDATION_NOT_FOUND,
    RECOMMENDATION_SCHEMA_VERSION,
    DecisionConflictEnvelope,
    DecisionJournalEntryEnvelope,
    DecisionJournalSubmitRequest,
    DeterministicRecommendationEnvelope,
    EvidenceReferenceEntry,
    ImpactRangeEntry,
    LinkEntry,
    RecommendationNotFoundEnvelope,
    RecommendationContractEnvelope,
)
from app.forecasts.schemas import (
    ERROR_CODE_FORECAST_NOT_FOUND,
    ForecastNotFoundEnvelope,
)


# ============================================================
# Fixtures (deterministic across tests; generated via uuid5)
# ============================================================

FORECAST_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "atlas-test/forecast/1"))
RECOMMENDATION_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "atlas-test/rec/1"))
JOURNAL_ENTRY_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "atlas-test/journal/1"))


def _valid_recommendation_payload(**overrides) -> dict[str, object]:
    valid_input_state_hash = "a" * 64
    valid_assumptions_reference = hashlib.sha256(
        b"atlas-test-assumption-snapshot/v1"
    ).hexdigest()
    payload: dict[str, object] = {
        "schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "recommendation_kind": "increase_contribution",
        "action_verb": "Increase",
        "why_now": "Conservative scenario is below target; base scenario clears it.",
        "linked_goal_id": 42,
        "forecast_id": FORECAST_ID,
        "forecast_etag": f"{FORECAST_ID}-v1",
        "evidence_references": {
            "forecast_id": FORECAST_ID,
            "model_version": "atlas-projection/v1",
            "calculation_version": "atlas-calculation/v1",
            "input_state_hash": valid_input_state_hash,
            "data_as_of": "2026-08-01T12:00:00.000000Z",
        },
        "expected_impact_range": {
            "min_delta_decimal": "100",
            "max_delta_decimal": "350",
        },
        "risks": ("liquidity_reduction",),
        "confidence": "medium",
        "assumptions_reference": valid_assumptions_reference,
        "expiration": "2026-08-02T12:00:00Z",
        "issuer": DETERMINISTIC_RULES_ISSUER,
        "links": [
            {"rel": "self", "href": f"/api/v1/forecasts/{FORECAST_ID}/recommendation"},
            {"rel": "forecast", "href": f"/api/v1/forecasts/{FORECAST_ID}"},
        ],
    }
    payload.update(overrides)
    return payload


def _valid_journal_entry_payload(**overrides) -> dict[str, object]:
    decision_etag = f"{RECOMMENDATION_ID}-d1"
    payload: dict[str, object] = {
        "schema_version": DECISION_JOURNAL_SCHEMA_VERSION,
        "journal_entry_id": JOURNAL_ENTRY_ID,
        "recommendation_id": RECOMMENDATION_ID,
        "action_taken": "accept",
        "decided_at": "2026-08-01T12:34:56.789012Z",
        "decision_etag": decision_etag,
        "links": [
            {"rel": "self", "href": f"/api/v1/decisions/{JOURNAL_ENTRY_ID}"},
        ],
    }
    payload.update(overrides)
    return payload


def _valid_recommendation_contract_payload(**overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "atlas-recommendation-contract/v1",
        "recommendation_id": RECOMMENDATION_ID,
        "goal": {"goal_id": 42},
        "evidence": _valid_recommendation_payload()["evidence_references"],
        "risks": ("liquidity_reduction",),
        "confidence": "medium",
        "approvals": [{
            "decision_journal_entry_id": JOURNAL_ENTRY_ID,
            "action": "accept",
            "decided_at": "2026-08-01T12:34:56.789012Z",
            "outcome_evaluations": [{
                "evaluation_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "atlas-test/evaluation/1")),
                "lifecycle": "measured",
                "evidence_source_kind": "account_balance_delta",
                "evidence_reference_hash": "b" * 64,
                "confidence": "high",
                "recorded_at": "2026-08-02T12:34:56.789012Z",
            }],
        }],
    }
    payload.update(overrides)
    return payload


# ============================================================
# 1. Top-level schema_version convention (planning nit 2)
# ============================================================

def test_recommendation_envelope_top_level_schema_version_is_literal() -> None:
    envelope = DeterministicRecommendationEnvelope.model_validate(
        _valid_recommendation_payload()
    )
    assert envelope.schema_version == "atlas-derived-recommendation/v1"
    # Round-trip serialization preserves the literal verbatim.
    dumped = envelope.model_dump(mode="json")
    assert dumped["schema_version"] == "atlas-derived-recommendation/v1"


def test_recommendation_envelope_rejects_non_literal_schema_version() -> None:
    payload = _valid_recommendation_payload(schema_version="atlas-derived-recommendation/v2")
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(payload)


def test_journal_envelope_top_level_schema_version_is_literal() -> None:
    envelope = DecisionJournalEntryEnvelope.model_validate(_valid_journal_entry_payload())
    assert envelope.schema_version == "atlas-decision-journal-entry/v1"


def test_journal_envelope_rejects_non_literal_schema_version() -> None:
    payload = _valid_journal_entry_payload(schema_version="atlas-decision-journal-entry/v0")
    with pytest.raises(ValidationError):
        DecisionJournalEntryEnvelope.model_validate(payload)


def test_recommendation_and_journal_versions_are_distinct() -> None:
    """The two envelopes must not accidentally share a schema_version literal."""
    assert RECOMMENDATION_SCHEMA_VERSION != DECISION_JOURNAL_SCHEMA_VERSION

    # Cross-validation: a journal-shape payload must not validate as a
    # recommendation, and vice versa.  The schema_version literal acts as
    # the discriminator, catching drift regressions.
    rec_payload = _valid_recommendation_payload()
    with pytest.raises(ValidationError):
        DecisionJournalEntryEnvelope.model_validate(rec_payload)

    j_payload = _valid_journal_entry_payload()
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(j_payload)


def test_recommendation_contract_is_read_only_and_hash_only() -> None:
    contract = RecommendationContractEnvelope.model_validate(
        _valid_recommendation_contract_payload()
    )
    dumped = contract.model_dump(mode="json")
    evaluation = dumped["approvals"][0]["outcome_evaluations"][0]
    assert evaluation["evidence_reference_hash"] == "b" * 64
    assert "result_json" not in evaluation
    assert "explanation" not in evaluation
    with pytest.raises(ValidationError):
        RecommendationContractEnvelope.model_validate(
            _valid_recommendation_contract_payload(raw_evidence_reference="https://example.test/evidence")
        )


# ============================================================
# 2. extra='forbid' on every response + request model
# ============================================================

@pytest.mark.parametrize(
    "model,payload,extra_field",
    [
        (
            DeterministicRecommendationEnvelope,
            _valid_recommendation_payload(),
            "extra_money_value",
        ),
        (
            DecisionJournalEntryEnvelope,
            _valid_journal_entry_payload(),
            "user_token",
        ),
        (
            DecisionJournalSubmitRequest,
            {"action": "accept", "decision_etag": f"{RECOMMENDATION_ID}-d1"},
            "client_financial_state",
        ),
        (RecommendationNotFoundEnvelope, {}, "raw_input"),
        (DecisionConflictEnvelope, {"current_etag": f"{RECOMMENDATION_ID}-d1"}, "signal"),
    ],
)
def test_extra_fields_are_forbidden(model, payload, extra_field) -> None:
    tampered = copy.deepcopy(payload)
    tampered[extra_field] = "leak"
    with pytest.raises(ValidationError):
        model.model_validate(tampered)


@pytest.mark.parametrize(
    "model,payload",
    [
        (DeterministicRecommendationEnvelope, _valid_recommendation_payload()),
        (DecisionJournalEntryEnvelope, _valid_journal_entry_payload()),
        (RecommendationNotFoundEnvelope, {}),
        (DecisionConflictEnvelope, {"current_etag": f"{RECOMMENDATION_ID}-d1"}),
    ],
)
def test_response_models_are_frozen(model, payload) -> None:
    envelope = model.model_validate(payload)
    with pytest.raises(ValidationError):
        envelope.schema_version = "tampered"


# ============================================================
# 3. Planning nit 1: distinct RecommendationNotFoundEnvelope
# ============================================================

def test_recommendation_not_found_envelope_code_distinct_from_forecast() -> None:
    """The recommendation 404 envelope must NOT collide with the forecast
    404 envelope; the UI uses both in disjoint flows and conflating them
    would surface a confused affordance."""
    rec_env = RecommendationNotFoundEnvelope.model_validate({})
    fcst_env = ForecastNotFoundEnvelope.model_validate({})

    assert rec_env.code == ERROR_CODE_RECOMMENDATION_NOT_FOUND
    assert fcst_env.code == ERROR_CODE_FORECAST_NOT_FOUND
    assert rec_env.code != fcst_env.code
    assert rec_env.code == "recommendation_not_found"
    assert fcst_env.code == "forecast_not_found"


# ============================================================
# 4. Bounded enum tokens (recommendation_kind, confidence, risks)
# ============================================================

@pytest.mark.parametrize(
    "kind",
    [
        "increase_contribution",
        "rebalance_allocation",
        "extend_horizon",
        "hold",
    ],
)
def test_recommendation_kind_accepts_all_bounded_literals(kind) -> None:
    DeterministicRecommendationEnvelope.model_validate(
        _valid_recommendation_payload(recommendation_kind=kind)
    )


@pytest.mark.parametrize("kind", ["do_something", "monte_carlo", "", None])
def test_recommendation_kind_rejects_non_bounded(kind) -> None:
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(recommendation_kind=kind)
        )


@pytest.mark.parametrize("confidence", ["high", "medium", "low"])
def test_confidence_accepts_all_bounded_literals(confidence) -> None:
    DeterministicRecommendationEnvelope.model_validate(
        _valid_recommendation_payload(confidence=confidence)
    )


@pytest.mark.parametrize("confidence", ["guaranteed", "ULTRA", "", None])
def test_confidence_rejects_non_bounded(confidence) -> None:
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(confidence=confidence)
        )


@pytest.mark.parametrize(
    "risk",
    [
        "liquidity_reduction",
        "reversibility_required",
        "concentration",
        "downside_amplification",
        "stale_input",
    ],
)
def test_risk_tokens_accept_all_bounded_literals(risk) -> None:
    DeterministicRecommendationEnvelope.model_validate(
        _valid_recommendation_payload(risks=(risk,))
    )


@pytest.mark.parametrize("risk", ["rude_risk", "LLM", "MARGIN_CALL", "", None])
def test_risk_tokens_reject_non_bounded(risk) -> None:
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(risks=(risk,))
        )


def test_risks_tuple_bounded_length() -> None:
    # 5 distinct risk tokens must exceed the bounded tuple length cap.
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(
                risks=(
                    "liquidity_reduction",
                    "reversibility_required",
                    "concentration",
                    "downside_amplification",
                    "stale_input",
                )
            )
        )


# ============================================================
# 5. Decision action tokens (accept | reject | defer)
# ============================================================

@pytest.mark.parametrize("action", ["accept", "reject", "defer"])
def test_decision_submit_accepts_bounded_actions(action) -> None:
    DecisionJournalSubmitRequest.model_validate(
        {"action": action, "decision_etag": f"{RECOMMENDATION_ID}-d1"}
    )


@pytest.mark.parametrize("action", ["approve", "deny", "yes", "", None])
def test_decision_submit_rejects_non_bounded_actions(action) -> None:
    with pytest.raises(ValidationError):
        DecisionJournalSubmitRequest.model_validate(
            {"action": action, "decision_etag": f"{RECOMMENDATION_ID}-d1"}
        )


# ============================================================
# 6. Decision ETag namespace (distinct from forecast ETag)
# ============================================================

def test_decision_etag_accepts_decision_namespace_form() -> None:
    DecisionJournalSubmitRequest.model_validate(
        {"action": "accept", "decision_etag": f"{RECOMMENDATION_ID}-d1"}
    )


def test_decision_etag_rejects_forecast_namespace_form() -> None:
    """A forecast ETag shape (``uuid-v<n>``) MUST NOT validate as a decision
    ETag - the two namespaces cannot collide under any client mutation."""
    with pytest.raises(ValidationError):
        DecisionJournalSubmitRequest.model_validate(
            {"action": "accept", "decision_etag": f"{FORECAST_ID}-v1"}
        )


def test_journal_entry_envelope_decision_etag_is_decision_namespace() -> None:
    payload = _valid_journal_entry_payload(decision_etag=f"{FORECAST_ID}-v1")
    with pytest.raises(ValidationError):
        DecisionJournalEntryEnvelope.model_validate(payload)


def test_decision_conflict_envelope_current_etag_must_be_decision_namespace() -> None:
    DecisionConflictEnvelope.model_validate({"current_etag": f"{RECOMMENDATION_ID}-d1"})

    with pytest.raises(ValidationError):
        DecisionConflictEnvelope.model_validate({"current_etag": f"{FORECAST_ID}-v1"})

    with pytest.raises(ValidationError):
        DecisionConflictEnvelope.model_validate({"current_etag": "not-a-uuid-d1"})


# ============================================================
# 7. Decimal-string impact range (canonical / no float)
# ============================================================

@pytest.mark.parametrize(
    "min_value,max_value",
    [
        ("0", "0"),
        ("-100.5", "0"),
        ("100", "350"),
        ("0.01", "99999999999999999.99"),
    ],
)
def test_impact_range_accepts_canonical_decimals(min_value, max_value) -> None:
    ImpactRangeEntry.model_validate(
        {"min_delta_decimal": min_value, "max_delta_decimal": max_value}
    )


@pytest.mark.parametrize(
    "min_value,max_value",
    [
        ("1e3", "1e3"),  # scientific notation forbidden
        (" 100.00 ", "100.00"),  # whitespace forbidden
        ("01.500", "01.500"),  # leading / trailing zeros forbidden
        ("NaN", "0"),
        ("Infinity", "0"),
        ("-", "-"),
    ],
)
def test_impact_range_rejects_non_canonical(min_value, max_value) -> None:
    if min_value == "-":
        # Pydantic rejects empty string before validators fire.
        with pytest.raises(ValidationError):
            ImpactRangeEntry.model_validate(
                {"min_delta_decimal": min_value, "max_delta_decimal": max_value}
            )
        return
    if min_value == "NaN" or min_value == "Infinity":
        with pytest.raises(ValidationError):
            ImpactRangeEntry.model_validate(
                {"min_delta_decimal": min_value, "max_delta_decimal": max_value}
            )
        return
    with pytest.raises(ValidationError):
        ImpactRangeEntry.model_validate(
            {"min_delta_decimal": min_value, "max_delta_decimal": max_value}
        )


# ============================================================
# 7b. M1 tightened canonical-state validator reuse (length + scale caps)
# ============================================================


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("9" * 41, id="length_cap_violation"),
        pytest.param("9" * 40, id="total_digit_cap_violation"),
    ],
)
def test_impact_range_rejects_canonical_state_v1_bounds(value) -> None:
    """Phase 1 v1 bounds the canonical-state validator enforces that the
    inline copy did not: length cap (MAX_DECIMAL_ENCODED_LENGTH=40) and
    total-digit cap (MAX_DECIMAL_TOTAL_DIGITS=38).  Each parametrize case
    is named after its violated invariant so a future regression points
    unambiguously to the right bound; ``9*41`` is rejected on length,
    ``9*40`` on total-digit count (it fits the length cap but exceeds
    the total-digit count)."""

    with pytest.raises(ValidationError) as captured:
        ImpactRangeEntry.model_validate(
            {"min_delta_decimal": value, "max_delta_decimal": "0"}
        )
    detail = next(iter(captured.value.errors()), None)
    assert detail is not None
    # ``canonical-state/v1`` raises ``ValueError`` via ``field_validator``;
    # Pydantic surfaces that as ``type == 'value_error'``. We tighten the
    # prior over-permissive ``in {value_error, string_type}`` assertion
    # because the test payload is always a string and the canonical-state
    # validator always raises ``ValueError``.
    assert detail["type"] == "value_error"


def test_impact_range_rejects_fractional_scale_cap_violation() -> None:
    """M1 reuse enforces MAX_DECIMAL_SCALE=18.  19 fractional digits are
    rejected so impact-range money payload precision cannot exceed the
    contract bound."""

    with pytest.raises(ValidationError):
        ImpactRangeEntry.model_validate(
            {
                "min_delta_decimal": "1." + "0" * 18 + "1",
                "max_delta_decimal": "0",
            }
        )


# ============================================================
# 8. Link href bounded to /api/v1/ server-relative paths
# ============================================================


@pytest.mark.parametrize(
    "href",
    [
        "/api/v1/forecasts/abc/recommendation",
        "/api/v1/decisions/abc",
        "/api/v1/recommendations/abc/decisions",
    ],
)
def test_link_entry_accepts_server_relative_href(href) -> None:
    LinkEntry.model_validate({"rel": "self", "href": href})


@pytest.mark.parametrize(
    "href",
    [
        "https://example.com/api/v1/x",  # absolute url
        "http://localhost/x",  # scheme
        "/dash/goals",  # wrong prefix
        "/api/v2/forecasts/x",  # wrong version prefix
        "/api/v1/forecasts/x?z=1",  # query string
        "/api/v1/forecasts/x#frag",  # fragment
        "",
    ],
)
def test_link_entry_rejects_non_server_relative(href) -> None:
    with pytest.raises(ValidationError):
        LinkEntry.model_validate({"rel": "self", "href": href})


@pytest.mark.parametrize(
    "rel",
    ["self", "forecast", "decide", "goal", "recorded"],
)
def test_link_rel_accepts_bounded(rel) -> None:
    LinkEntry.model_validate(
        {"rel": rel, "href": "/api/v1/forecasts/x/recommendation"}
    )


@pytest.mark.parametrize("rel", ["approve", "PREV", "next", "", None])
def test_link_rel_rejects_non_bounded(rel) -> None:
    with pytest.raises(ValidationError):
        LinkEntry.model_validate(
            {"rel": rel, "href": "/api/v1/forecasts/x/recommendation"}
        )


# ============================================================
# 9. UUID + SHA-256 + RFC 3339 validators
# ============================================================


def test_evidence_reference_rejects_non_canonical_fields() -> None:
    base = _valid_recommendation_payload()["evidence_references"]
    assert isinstance(base, dict)
    bad = dict(base)
    bad["forecast_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        EvidenceReferenceEntry.model_validate(bad)

    bad = dict(base)
    bad["input_state_hash"] = "Z" * 64
    with pytest.raises(ValidationError):
        EvidenceReferenceEntry.model_validate(bad)

    bad = dict(base)
    bad["data_as_of"] = "2026-08-01 12:00:00+00:00"  # not RFC 3339 Z
    with pytest.raises(ValidationError):
        EvidenceReferenceEntry.model_validate(bad)


def test_recommendation_expiration_must_be_rfc3339_z() -> None:
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(expiration="2026-08-01T12:00:00")
        )


def test_journal_decided_at_must_be_rfc3339_z() -> None:
    with pytest.raises(ValidationError):
        DecisionJournalEntryEnvelope.model_validate(
            _valid_journal_entry_payload(decided_at="2026-08-01 12:00:00")
        )


def test_linked_goal_id_bounds() -> None:
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(linked_goal_id=0)
        )
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(linked_goal_id=9_223_372_036_854_775_807 + 1)
        )


# ============================================================
# 10. Deterministic round-trip (golden fixture stability)
# ============================================================


def test_recommendation_envelope_round_trip_is_byte_stable() -> None:
    """The envelope must round-trip through JSON without mutating any
    field; this guarantees the deterministic-derivation contract."""
    payload = _valid_recommendation_payload()
    envelope = DeterministicRecommendationEnvelope.model_validate(payload)
    rendered = json.loads(envelope.model_dump_json())
    rebuilt = DeterministicRecommendationEnvelope.model_validate(rendered)
    assert rebuilt.model_dump(mode="json") == envelope.model_dump(mode="json")


def test_journal_entry_envelope_round_trip_is_byte_stable() -> None:
    payload = _valid_journal_entry_payload()
    envelope = DecisionJournalEntryEnvelope.model_validate(payload)
    rendered = json.loads(envelope.model_dump_json())
    rebuilt = DecisionJournalEntryEnvelope.model_validate(rendered)
    assert rebuilt.model_dump(mode="json") == envelope.model_dump(mode="json")


# ============================================================
# 11. Issuer literal (no LLM must infiltrate)
# ============================================================


def test_recommendation_envelope_issuer_must_be_deterministic() -> None:
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(issuer="atlas-copilot/v1")
        )

    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(
            _valid_recommendation_payload(issuer="atlas-llm/v1")
        )


# ============================================================
# 12. Sensitive-data invariants (private-data guards)
# ============================================================


@pytest.mark.parametrize(
    "sensitive_payload",
    [
        {"idempotency_key_plaintext": "header-token"},
        {"recommendation_prompt": "Pretend you're a financial advisor..."},
        {"client_api_token": "sk_live_supersensitive"},
    ],
)
def test_recommendation_envelope_rejects_sensitive_top_level_fields(
    sensitive_payload,
) -> None:
    tampered = _valid_recommendation_payload()
    tampered.update(sensitive_payload)
    with pytest.raises(ValidationError):
        DeterministicRecommendationEnvelope.model_validate(tampered)


def test_journal_submit_rejects_sensitive_top_level_fields() -> None:
    base = {"action": "accept", "decision_etag": f"{RECOMMENDATION_ID}-d1"}
    for sensitive in (
        "amount",
        "target_amount",
        "current_balance",
        "monthly_contribution",
        "assumptions_override",
        "scenario_override",
    ):
        with pytest.raises(ValidationError):
            DecisionJournalSubmitRequest.model_validate(
                {**base, sensitive: "100"}
            )


# ============================================================
# 13. JSON-string ingestion (model_validate_json parity)
# ============================================================


def test_recommendation_envelope_validates_from_json_string() -> None:
    payload = _valid_recommendation_payload()
    envelope = DeterministicRecommendationEnvelope.model_validate_json(
        json.dumps(payload, sort_keys=True)
    )
    assert envelope.schema_version == RECOMMENDATION_SCHEMA_VERSION


def test_journal_submit_validates_from_json_string() -> None:
    payload = {"action": "accept", "decision_etag": f"{RECOMMENDATION_ID}-d1"}
    body = DecisionJournalSubmitRequest.model_validate_json(json.dumps(payload))
    assert body.action == "accept"
