"""Contract tests for the bounded trusted Atlas projection-state envelope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.forecasts.canonical_state import (
    CANONICAL_JSON_VERSION,
    HASH_SCHEMA_VERSION,
    PROJECTION_STATE_SCHEMA_VERSION,
    CanonicalProjectionState,
    CanonicalStateValidationError,
    FinlynqProjectionStateAdapter,
    canonicalize_legacy_float_target,
    load_authoritative_projection_state,
    parse_generation_control_body,
    validate_idempotency_key,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "atlas_forecast_snapshots_v1.json"


@pytest.fixture(scope="module")
def fixture_case() -> dict[str, object]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "atlas-projection-state-fixtures/v1"
    assert fixture["synthetic_data_notice"].startswith("SYNTHETIC TEST DATA ONLY")
    return fixture["cases"][0]


def test_envelope_fixture_is_typed_bounded_and_synthetic(
    fixture_case: dict[str, object],
) -> None:
    envelope = CanonicalProjectionState.model_validate(fixture_case["envelope"])

    assert envelope.schema_version == PROJECTION_STATE_SCHEMA_VERSION
    assert envelope.canonicalization.canonical_json_version == CANONICAL_JSON_VERSION
    assert envelope.canonicalization.hash_schema_version == HASH_SCHEMA_VERSION
    assert envelope.currency == "USD"
    assert envelope.user_id == "atlas-test-user-alpha"
    assert envelope.goal_id == 101
    assert [component.amount for component in envelope.current_value_components] == [
        "1234.56",
        "2345.67",
    ]
    assert "raw_statement" not in envelope.model_dump_json()
    assert "raw_transaction" not in envelope.model_dump_json()


@pytest.mark.parametrize(
    "patch",
    [
        {"raw_statement": "SYNTHETIC TEST DATA — NOT A REAL FINANCIAL STATEMENT"},
        {"raw_transactions": [{"description": "Test Merchant Alpha"}]},
        {"uploaded_file": "atlas-test-upload.pdf"},
        {"credentials": "not-allowed"},
        {"unbounded_source_payload": {"anything": "not-allowed"}},
    ],
)
def test_envelope_rejects_raw_or_unbounded_source_payloads(
    fixture_case: dict[str, object], patch: dict[str, object]
) -> None:
    envelope = {**fixture_case["envelope"], **patch}

    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_envelope_rejects_nested_raw_payloads_and_unknown_component_fields(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["provenance"][0]["raw_transactions"] = [
        {"description": "Test Merchant Alpha"}
    ]

    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)

    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["current_value_components"][0]["raw_statement_text"] = "not-allowed"
    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)


@pytest.mark.parametrize(
    "amount",
    ["0.00", "01.2", "+1.2", "1.20", "1e3", "-0", 1.2],
)
def test_envelope_requires_canonical_decimal_strings(
    fixture_case: dict[str, object], amount: object
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["current_value_components"][0]["amount"] = amount

    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_envelope_requires_utc_timestamps_and_bounded_collections(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["as_of_timestamp"] = "2026-07-01T12:00:00+01:00"
    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_envelope_does_not_coerce_identifier_or_count_types(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["goal_id"] = "101"
    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)

    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["provenance"][0]["record_count"] = True
    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)

    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["missing_data_codes"] = ["missing_component"] * 17
    with pytest.raises(ValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_legacy_float_metadata_does_not_claim_restored_precision() -> None:
    metadata = canonicalize_legacy_float_target(0.1)

    assert metadata == {
        "amount": "0.1",
        "source_representation": "float",
        "conversion": "Decimal(str(value))",
        "precision_restored": False,
    }


def test_generation_control_body_is_empty_and_idempotency_key_is_bounded() -> None:
    assert parse_generation_control_body({}).model_dump() == {}
    assert validate_idempotency_key("atlas-test-idempotency-key-0001") == (
        "atlas-test-idempotency-key-0001"
    )

    for client_owned_field in (
        "user_id",
        "household_id",
        "current_balance",
        "contribution_inputs",
        "canonical_snapshot",
        "currency",
        "freshness",
        "provenance",
        "transactions",
        "statements",
        "reconciliation_state",
        "input_state_hash",
        "model_version",
        "calculation_version",
    ):
        with pytest.raises(ValidationError):
            parse_generation_control_body({client_owned_field: "forged-value"})

    with pytest.raises(CanonicalStateValidationError, match="Idempotency-Key"):
        validate_idempotency_key("\n")


def test_authoritative_state_can_only_enter_through_trusted_adapter(
    fixture_case: dict[str, object]
) -> None:
    expected = CanonicalProjectionState.model_validate(fixture_case["envelope"])

    class TestAdapter(FinlynqProjectionStateAdapter):
        calls: list[tuple[str, int]] = []

        def load_projection_state(
            self, *, user_id: str, goal_id: int
        ) -> CanonicalProjectionState:
            self.calls.append((user_id, goal_id))
            return expected

    adapter = TestAdapter()
    actual = load_authoritative_projection_state(
        adapter=adapter,
        server_user_id="atlas-test-user-alpha",
        server_goal_id=101,
    )

    assert actual is expected
    assert adapter.calls == [("atlas-test-user-alpha", 101)]


def test_adapter_output_must_match_server_authorized_scope(
    fixture_case: dict[str, object]
) -> None:
    forged = {**fixture_case["envelope"], "user_id": "atlas-test-user-beta"}

    class MismatchedAdapter(FinlynqProjectionStateAdapter):
        def load_projection_state(
            self, *, user_id: str, goal_id: int
        ) -> CanonicalProjectionState:
            return CanonicalProjectionState.model_validate(forged)

    with pytest.raises(CanonicalStateValidationError, match="authorized user"):
        load_authoritative_projection_state(
            adapter=MismatchedAdapter(),
            server_user_id="atlas-test-user-alpha",
            server_goal_id=101,
        )
