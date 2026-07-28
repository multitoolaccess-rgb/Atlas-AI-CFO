"""Deterministic canonical JSON and input-state hash contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from decimal import Decimal

import pytest

from app.forecasts.canonical_state import (
    CanonicalProjectionState,
    CanonicalStateValidationError,
    canonical_json,
    canonical_decimal_string,
    hash_input_state,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "atlas_forecast_snapshots_v1.json"


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


def test_hash_changes_when_authoritative_state_changes() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    envelope = CanonicalProjectionState.model_validate(fixture["cases"][0]["envelope"])
    changed = envelope.model_copy(
        update={
            "current_value_components": [
                envelope.current_value_components[0].model_copy(update={"amount": "1234.57"}),
                envelope.current_value_components[1],
            ]
        }
    )

    assert hash_input_state(changed) != hash_input_state(envelope)
