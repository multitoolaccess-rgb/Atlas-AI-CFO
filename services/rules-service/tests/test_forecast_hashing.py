"""Deterministic canonical JSON and input-state hash contract tests."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from decimal import Decimal, ROUND_DOWN, ROUND_UP, localcontext

import pytest

from app.forecasts.canonical_state import (
    CanonicalProjectionState,
    CanonicalStateValidationError,
    ContractValidationError,
    canonical_json,
    canonical_decimal_string,
    hash_input_state,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "atlas_forecast_snapshots_v1.json"


@pytest.fixture(scope="module")
def fixture_case() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"][0]


def test_fixture_canonical_json_and_hash_are_deterministic() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    case = fixture["cases"][0]
    envelope = CanonicalProjectionState.model_validate(case["envelope"])

    assert canonical_json(envelope.hash_payload()) == case["expected_canonical_json"]
    assert hash_input_state(envelope) == case["expected_input_state_hash"]


def test_key_order_does_not_change_canonical_json_or_hash() -> None:
    left = {"z": "last", "nested": {"b": "two", "a": "one"}, "a": "first"}
    right = {"a": "first", "nested": {"a": "one", "b": "two"}, "z": "last"}

    assert canonical_json(left) == canonical_json(right)


def test_canonical_json_rejects_binary_floats_and_normalizes_decimal_values() -> None:
    assert canonical_json({"amount": Decimal("1234.560")}) == '{"amount":"1234.56"}'
    assert canonical_decimal_string(Decimal("0.00")) == "0"
    with pytest.raises(CanonicalStateValidationError, match="floating-point"):
        canonical_json({"amount": 1234.56})


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1E+1000"),
        Decimal("1E+1000000"),
        Decimal("1E-1000"),
        Decimal("1E-1000000"),
    ],
)
def test_direct_decimal_serialization_rejects_extreme_exponents_before_expansion(
    value: Decimal,
) -> None:
    with pytest.raises(CanonicalStateValidationError, match="v1 decimal bounds"):
        canonical_json({"amount": value})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1E+24"), '{"amount":"1000000000000000000000000"}'),
        (Decimal("-1E+24"), '{"amount":"-1000000000000000000000000"}'),
        (Decimal("1E-18"), '{"amount":"0.000000000000000001"}'),
        (Decimal("-1E-18"), '{"amount":"-0.000000000000000001"}'),
    ],
)
def test_direct_decimal_serialization_accepts_exact_exponent_boundaries(
    value: Decimal, expected: str
) -> None:
    assert canonical_json({"amount": value}) == expected


@pytest.mark.parametrize(
    "value", [Decimal("1E+25"), Decimal("-1E+25"), Decimal("1E-19"), Decimal("-1E-19")]
)
def test_direct_decimal_serialization_rejects_one_step_beyond_exponent_boundaries(
    value: Decimal,
) -> None:
    with pytest.raises(CanonicalStateValidationError, match="v1 decimal bounds"):
        canonical_json({"amount": value})


@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP])
def test_decimal_canonicalization_and_hashing_ignore_ambient_context(
    fixture_case: dict[str, object], rounding: str
) -> None:
    exact = Decimal("12345678901234567890.123456789012345678")
    expected_amount = "12345678901234567890.123456789012345678"
    baseline = json.loads(json.dumps(fixture_case["envelope"]))
    baseline["current_value_components"][0]["amount"] = expected_amount
    expected_state = CanonicalProjectionState.model_validate(baseline)
    expected_json = canonical_json({"amount": exact})
    expected_hash = hash_input_state(expected_state)

    with localcontext() as context:
        context.prec = 5
        context.rounding = rounding
        actual_amount = canonical_decimal_string(exact)
        actual_json = canonical_json({"amount": exact})
        actual = json.loads(json.dumps(fixture_case["envelope"]))
        actual["current_value_components"][0]["amount"] = actual_amount
        actual_state = CanonicalProjectionState.model_validate(actual)

    assert actual_amount == expected_amount
    assert actual_json == expected_json
    assert hash_input_state(actual_state) == expected_hash
    assert hashlib.sha256(actual_json.encode("utf-8")).hexdigest() == hashlib.sha256(
        expected_json.encode("utf-8")
    ).hexdigest()


def test_order_insensitive_envelope_collections_are_canonicalized(
    fixture_case: dict[str, object]
) -> None:
    canonical = json.loads(json.dumps(fixture_case["envelope"]))
    canonical["contribution_inputs"].append(
        {
            "kind": "monthly_investable_cash_flow",
            "amount": "12.34",
            "source_reference": "atlas-test-cash-flow-002",
            "observed_at": "2026-07-01T12:00:00Z",
        }
    )
    canonical["provenance"].append(
        {
            "source_system": "finlynq",
            "reference_id": "atlas-test-aggregate-002",
            "observed_at": "2026-07-01T12:00:00Z",
            "record_count": 1,
            "source_state_hash": (
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            ),
        }
    )
    canonical["missing_data_codes"] = ["missing_cash_flow", "missing_investment"]
    reversed_input = json.loads(json.dumps(canonical))
    for key in (
        "current_value_components",
        "contribution_inputs",
        "provenance",
        "missing_data_codes",
    ):
        reversed_input[key].reverse()

    first = CanonicalProjectionState.model_validate(canonical)
    second = CanonicalProjectionState.model_validate(reversed_input)

    assert first.hash_payload() == second.hash_payload()
    assert canonical_json(first.hash_payload()) == canonical_json(second.hash_payload())
    assert hash_input_state(first) == hash_input_state(second)


def test_duplicate_order_insensitive_collection_identity_is_rejected(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["current_value_components"].append(
        {**envelope["current_value_components"][0], "amount": "999.99"}
    )

    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_validated_envelope_collections_are_immutable(
    fixture_case: dict[str, object]
) -> None:
    state = CanonicalProjectionState.model_validate(fixture_case["envelope"])

    with pytest.raises(AttributeError):
        state.current_value_components.append(state.current_value_components[0])
    with pytest.raises(AttributeError):
        state.missing_data_codes.append("missing_cash_flow")


def test_hash_changes_when_authoritative_state_changes() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    envelope = CanonicalProjectionState.model_validate(fixture["cases"][0]["envelope"])
    changed_payload = envelope.model_dump(mode="json")
    changed_payload["current_value_components"][0]["amount"] = "1234.57"
    changed = CanonicalProjectionState.model_validate(changed_payload)

    assert hash_input_state(changed) != hash_input_state(envelope)
