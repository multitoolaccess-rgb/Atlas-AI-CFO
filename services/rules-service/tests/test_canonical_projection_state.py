"""Contract tests for the bounded trusted Atlas projection-state envelope."""

from __future__ import annotations

import json
from pathlib import Path
import traceback

import pytest

from app.forecasts.canonical_state import (
    CANONICAL_JSON_VERSION,
    HASH_SCHEMA_VERSION,
    PROJECTION_STATE_SCHEMA_VERSION,
    CanonicalProjectionState,
    CanonicalStateValidationError,
    ContractValidationError,
    FinlynqProjectionStateAdapter,
    canonicalize_legacy_float_target,
    load_authoritative_projection_state,
    parse_generation_control_body,
    sanitize_contract_error_location,
    validate_idempotency_key,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "atlas_forecast_snapshots_v1.json"


def assert_secret_marker_is_not_exposed(
    error: ContractValidationError, marker: str
) -> None:
    representations = (
        str(error),
        repr(error),
        repr(error.args),
        repr(error.errors()),
        error.json(),
        repr(error.__dict__),
        repr(error.__cause__),
        repr(error.__context__),
        "".join(traceback.format_exception(error)),
    )
    assert all(marker not in representation for representation in representations)
    assert error.__cause__ is None
    assert error.__context__ is None


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

    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_envelope_rejects_nested_raw_payloads_and_unknown_component_fields(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["provenance"][0]["raw_transactions"] = [
        {"description": "Test Merchant Alpha"}
    ]

    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(envelope)


@pytest.mark.parametrize(
    "patch, marker",
    [
        ({"raw_statement": "ATLAS-SECRET-RAW-STATEMENT-001"}, "ATLAS-SECRET-RAW-STATEMENT-001"),
        (
            {"raw_transactions": [{"description": "ATLAS-SECRET-RAW-TXN-002"}]},
            "ATLAS-SECRET-RAW-TXN-002",
        ),
        ({"credentials": "ATLAS-SECRET-CREDENTIAL-003"}, "ATLAS-SECRET-CREDENTIAL-003"),
        ({"access_token": "ATLAS-SECRET-TOKEN-004"}, "ATLAS-SECRET-TOKEN-004"),
        ({"uploaded_file": "ATLAS-SECRET-UPLOAD-005"}, "ATLAS-SECRET-UPLOAD-005"),
    ],
)
def test_contract_validation_errors_do_not_surface_rejected_raw_payloads(
    fixture_case: dict[str, object], patch: dict[str, object], marker: str
) -> None:
    envelope = {**fixture_case["envelope"], **patch}

    with pytest.raises(ContractValidationError) as exc_info:
        CanonicalProjectionState.model_validate(envelope)

    error = exc_info.value
    assert_secret_marker_is_not_exposed(error, marker)
    assert error.errors() == [{"loc": ("<extra-field>",), "type": "extra_forbidden"}]


def test_contract_validation_errors_redact_nested_rejected_payloads(
    fixture_case: dict[str, object]
) -> None:
    marker = "ATLAS-SECRET-NESTED-RAW-PAYLOAD-004"
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["provenance"][0]["raw_transactions"] = [{"description": marker}]

    with pytest.raises(ContractValidationError) as exc_info:
        CanonicalProjectionState.model_validate(envelope)

    error = exc_info.value
    assert_secret_marker_is_not_exposed(error, marker)
    assert {
        "loc": ("provenance", 0, "<extra-field>"),
        "type": "extra_forbidden",
    } in error.errors()


def test_direct_top_level_contract_construction_uses_safe_errors(
    fixture_case: dict[str, object]
) -> None:
    marker = "ATLAS-SECRET-DIRECT-CONSTRUCTION-005"
    envelope = {**fixture_case["envelope"], "raw_statement": marker}

    with pytest.raises(ContractValidationError) as exc_info:
        CanonicalProjectionState(**envelope)

    error = exc_info.value
    assert_secret_marker_is_not_exposed(error, marker)
    assert error.errors() == [{"loc": ("<extra-field>",), "type": "extra_forbidden"}]


def test_json_contract_validation_uses_safe_errors(
    fixture_case: dict[str, object]
) -> None:
    marker = "ATLAS-SECRET-JSON-CONSTRUCTION-006"
    envelope = {**fixture_case["envelope"], "raw_statement": marker}

    with pytest.raises(ContractValidationError) as exc_info:
        CanonicalProjectionState.model_validate_json(json.dumps(envelope))

    error = exc_info.value
    assert_secret_marker_is_not_exposed(error, marker)
    assert error.errors() == [{"loc": ("<extra-field>",), "type": "extra_forbidden"}]


@pytest.mark.parametrize(
    "unknown_key",
    [
        "x" * 10_000,
        "ATLAS-SECRET-UNKNOWN-FIELD-007",
        "line-one\nATLAS-SECRET-CONTROL-008\x1b[31m",
    ],
)
def test_contract_errors_never_echo_unknown_client_field_names(
    fixture_case: dict[str, object], unknown_key: str
) -> None:
    envelope = {**fixture_case["envelope"], unknown_key: "forged-value"}

    with pytest.raises(ContractValidationError) as exc_info:
        CanonicalProjectionState.model_validate(envelope)

    error = exc_info.value
    assert_secret_marker_is_not_exposed(error, unknown_key)
    assert error.errors() == [{"loc": ("<extra-field>",), "type": "extra_forbidden"}]


def test_contract_errors_sanitize_nested_unknown_locations_without_echoing_keys(
    fixture_case: dict[str, object]
) -> None:
    marker = "ATLAS-SECRET-NESTED-UNKNOWN-009"
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["provenance"][0][marker] = "forged-value"

    with pytest.raises(ContractValidationError) as exc_info:
        CanonicalProjectionState.model_validate(envelope)

    error = exc_info.value
    assert_secret_marker_is_not_exposed(error, marker)
    assert {"loc": ("provenance", 0, "<extra-field>"), "type": "extra_forbidden"} in error.errors()


def test_contract_error_locations_bound_components_and_indices() -> None:
    location = sanitize_contract_error_location(
        ("current_value_components", 10_000, "amount", "ignored", "still_ignored"),
        "value_error",
    )

    assert location == (
        "current_value_components",
        "<index>",
        "amount",
        "<truncated-location>",
    )


def test_contract_errors_preserve_known_safe_field_diagnosis(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["current_value_components"][0]["amount"] = "not-a-decimal"

    with pytest.raises(ContractValidationError) as exc_info:
        CanonicalProjectionState.model_validate(envelope)

    error = exc_info.value
    assert error.errors() == [
        {
            "loc": ("current_value_components", 0, "amount"),
            "type": "value_error",
        }
    ]

    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["current_value_components"][0]["raw_statement_text"] = "not-allowed"
    with pytest.raises(ContractValidationError):
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

    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_envelope_enforces_v1_decimal_precision_scale_and_encoded_length_bounds(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["current_value_components"][0]["amount"] = (
        "12345678901234567890.123456789012345678"
    )
    assert (
        CanonicalProjectionState.model_validate(envelope)
        .current_value_components[0]
        .amount
        == "12345678901234567890.123456789012345678"
    )
    envelope["current_value_components"][0]["amount"] = (
        "-12345678901234567890.123456789012345678"
    )
    assert CanonicalProjectionState.model_validate(envelope)

    for amount in (
        "123456789012345678901.123456789012345678",  # 39 digits
        "0.1234567890123456789",  # scale 19
        "-123456789012345678901.123456789012345678",  # length 41
        "0." + ("0" * 10_000) + "1",  # reported overscale regression
    ):
        rejected = json.loads(json.dumps(fixture_case["envelope"]))
        rejected["current_value_components"][0]["amount"] = amount
        with pytest.raises(ContractValidationError):
            CanonicalProjectionState.model_validate(rejected)


def test_envelope_requires_utc_timestamps_and_bounded_collections(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["as_of_timestamp"] = "2026-07-01T12:00:00+01:00"
    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(envelope)


def test_envelope_does_not_coerce_identifier_or_count_types(
    fixture_case: dict[str, object]
) -> None:
    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["goal_id"] = "101"
    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(envelope)

    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["provenance"][0]["record_count"] = True
    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(envelope)

    envelope = json.loads(json.dumps(fixture_case["envelope"]))
    envelope["missing_data_codes"] = ["missing_component"] * 17
    with pytest.raises(ContractValidationError):
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
        with pytest.raises(ContractValidationError):
            parse_generation_control_body({client_owned_field: "forged-value"})

    with pytest.raises(CanonicalStateValidationError, match="Idempotency-Key"):
        validate_idempotency_key("\n")


def test_generation_control_body_rejects_client_assumption_and_driver_fields() -> None:
    for field in ("assumptions", "assumption_profile", "projection_drivers"):
        with pytest.raises(ContractValidationError):
            parse_generation_control_body({field: "forged-value"})


def test_generation_control_body_rejects_client_output_and_result_fields() -> None:
    for field in (
        "projection_output",
        "scenario_outputs",
        "target_status",
        "probability",
        "target_gap",
    ):
        with pytest.raises(ContractValidationError):
            parse_generation_control_body({field: "forged-value"})


def test_generation_control_body_rejects_client_authoritative_state_categories(
) -> None:
    for field in (
        "financial_state",
        "net_worth",
        "balance_components",
        "freshness_metadata",
        "source_records",
        "provenance_references",
        "hash_schema_version",
        "snapshot_schema_version",
    ):
        with pytest.raises(ContractValidationError):
            parse_generation_control_body({field: "forged-value"})


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

    with pytest.raises(
        CanonicalStateValidationError, match="authorized user"
    ) as exc_info:
        load_authoritative_projection_state(
            adapter=MismatchedAdapter(),
            server_user_id="atlas-test-user-alpha",
            server_goal_id=101,
        )
    assert "atlas-test-user-beta" not in str(exc_info.value)


def test_adapter_output_must_match_server_authorized_goal(
    fixture_case: dict[str, object]
) -> None:
    forged = {**fixture_case["envelope"], "goal_id": 102}

    class MismatchedAdapter(FinlynqProjectionStateAdapter):
        def load_projection_state(
            self, *, user_id: str, goal_id: int
        ) -> CanonicalProjectionState:
            return CanonicalProjectionState.model_validate(forged)

    with pytest.raises(CanonicalStateValidationError, match="authorized goal"):
        load_authoritative_projection_state(
            adapter=MismatchedAdapter(),
            server_user_id="atlas-test-user-alpha",
            server_goal_id=101,
        )
