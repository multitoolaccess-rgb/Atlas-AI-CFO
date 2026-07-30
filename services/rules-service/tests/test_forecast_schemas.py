"""Test-first coverage for Slice C schemas and codecs.

Compact, atomic tests.  One contract per test.  Designed so the file
parses as one module and pytest can collect it without splitting.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.forecasts.api_codecs import (
    CodecError,
    decode_forecast_cursor,
    derive_forecast_etag,
    encode_forecast_cursor,
    format_forecast_etag_header,
    parse_forecast_etag_header,
)
from app.forecasts.snapshots import (
    ASSUMPTION_SCHEMA_VERSION,
    CALCULATION_DECIMAL_SCHEMA_VERSION,
    TARGET_DECISION_SCHEMA_VERSION,
)
from app.forecasts.schemas import (
    ForecastGenerationDisabledEnvelope,
    ForecastListResponse,
    ForecastNotFoundEnvelope,
    ForecastResponse,
    ForecastVersionConflictEnvelope,
    ForecastVersionListResponse,
    ForecastVersionResponse,
    GenerationRequestEnvelope,
    GoalNotFoundEnvelope,
    IdempotencyConflictEnvelope,
    IdempotencyKeyHeader,
    IfMatchHeader,
    IfNoneMatchHeader,
    ReadApiDisabledEnvelope,
    ValidationErrorEnvelope,
)


# ----- Synthetic fixtures -------------------------------------------

UUID_A = "01234567-89ab-cdef-0123-456789abcdef"
UUID_B = "01234567-89ab-cdef-0123-456789abcdee"
NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def _aid(n: int = 1) -> str:
    return f"{n:08x}" * 4 + "-1234"  # not a real UUID; helps satisfy ascii regex for tests
def _etag(n: int = 1) -> str:
    return f"{UUID_A}-v{n}"


def _assumptions() -> dict[str, Any]:
    return {
        "assumption_schema_version": ASSUMPTION_SCHEMA_VERSION,
        "assumption_profile": "phase1.server.default",
        "annual_return_rates": [("conservative", "0.02"), ("base", "0.04"), ("optimistic", "0.06")],
        "annual_inflation_rate": "0.02",
        "contribution_timing": "end",
        "period": "monthly",
        "rounding_rule": "ROUND_HALF_EVEN",
        "money_precision": "0.01",
        "goal_inputs": [("target_amount", "2000"), ("horizon_years", "2"), ("target_date", "2028-07-30")],
    }


def _decision() -> dict[str, Any]:
    return {
        "decision_schema_version": TARGET_DECISION_SCHEMA_VERSION, "scenario": "base",
        "comparison": "greater_than_or_equal", "decision_basis": "currency_rounded",
        "rounding_rule": "ROUND_HALF_EVEN", "money_precision": "0.01",
        "unrounded_ending_balance": "2400", "unrounded_target_amount": "2000",
        "rounded_ending_balance": "2400.00", "rounded_target_amount": "2000.00",
        "target_status": True,
    }


def _scenario(name: str = "base") -> dict[str, Any]:
    reach = name == "base"
    return {
        "annual_return_rate": "0.04",
        "monthly_real_rate": "0.04",
        "ending_balance": "2400" if reach else "1000",
        "investment_growth": "2400" if reach else "1000",
        "target_gap": None if reach else "1000",
        "reaches_target": reach,
    }


def _drivers() -> dict[str, Any]:
    return {
        "current_balance": "0", "monthly_contribution": "100", "total_contributions": "2400",
        "target_amount": "2000.00", "horizon_months": 24,
        "data_as_of": "2026-07-30T00:00:00Z", "data_age_days": 0,
    }


def _output_snapshot_base() -> dict[str, Any]:
    return {
        "calculation_decimal_schema_version": CALCULATION_DECIMAL_SCHEMA_VERSION,
        "target_status": True, "target_decision": _decision(), "drivers": _drivers(),
        "scenarios": [
            ("conservative", _scenario("conservative")),
            ("base", _scenario("base")),
            ("optimistic", _scenario("optimistic")),
        ],
    }


def _forecast_response_dict(**kw: Any) -> dict[str, Any]:
    base = {
        "forecast_id": UUID_A, "goal_id": 1, "forecast_kind": "goal_projection",
        "currency": "USD", "lifecycle_state": "active", "latest_version_number": 1,
        "etag": _etag(1), "latest_version_id": UUID_B,
        "created_at": "2026-07-30T00:00:00Z", "updated_at": "2026-07-30T00:00:00Z",
        "links": (),
    }
    base.update(kw); return base


def _forecast_version_response_dict(**kw: Any) -> dict[str, Any]:
    base = {
        "forecast_id": UUID_A, "version_id": UUID_B, "version_number": 1,
        "etag": _etag(1),
        "input_state_hash": "a" * 64, "idempotency_key_hash": "b" * 64,
        "snapshot": {
            "snapshot_schema_version": ASSUMPTION_SCHEMA_VERSION,
            "hash_schema_version": "atlas-input-state-hash/v1",
            "model_version": "atlas-forecast-v1",
            "calculation_version": "phase0-projection-v1",
        },
        "currency": "USD",
        "calculated_at": "2026-07-30T00:00:00Z",
        "data_as_of": "2026-07-30T00:00:00Z",
        "max_data_age_days": 30, "data_age_days": 0,
        "created_at": "2026-07-30T00:00:00Z",
        "ending_balance": "2400.00", "target_gap": "0.00",
        "target_status": True,
        "target_decision": _decision(),
        "drivers": _drivers(),
        "scenarios": _output_snapshot_base(),
        "assumption_snapshot": _assumptions(),
        "provenance_snapshot": {
            "provenance": ({"source_system": "finlynq", "reference_id": "x", "observed_at": "2026-07-30T00:00:00Z", "record_count": 1, "source_state_hash": "a" * 64},),
            "freshness": {"max_data_age_days": 30, "observed_age_days": 0, "source_updated_at": "2026-07-30T00:00:00Z"},
        },
        "input_snapshot": {}, "links": (),
    }
    base.update(kw); return base


# ----- Cursor codec --------------------------------------------------

def test_cursor_round_trip_is_stable():
    a = encode_forecast_cursor(forecast_id=UUID_A, created_at=NOW, version_number=1)
    b = encode_forecast_cursor(forecast_id=UUID_A, created_at=NOW, version_number=1)
    assert a == b
    decoded = decode_forecast_cursor(a)
    assert decoded.forecast_id == UUID_A
    assert decoded.version_number == 1
    # ISO-string equality avoids datetime-equivalence pitfalls across
    # the round-trip; the codec invariant is that the wire form survives.
    assert decoded.created_at.astimezone(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    ).startswith("2026-07-30T00:00:00")


def test_cursor_rejects_tampered_payload():
    a = encode_forecast_cursor(forecast_id=UUID_A, created_at=NOW, version_number=1)
    # Flip one base64url-safe byte.
    idx = a.index(".") + 5
    flipped = a[:idx] + ("_" if a[idx] != "_" else "-") + a[idx + 1:]
    with pytest.raises(CodecError):
        decode_forecast_cursor(flipped)


def test_cursor_rejects_wrong_prefix():
    with pytest.raises(CodecError):
        decode_forecast_cursor("zz" + encode_forecast_cursor(forecast_id=UUID_A, created_at=NOW, version_number=1))


def test_cursor_rejects_oversize():
    huge = "fc1." + ("a" * 1024)
    with pytest.raises(CodecError):
        decode_forecast_cursor(huge)


# ----- ETag codec ---------------------------------------------------

def test_etag_derive_pass_through():
    assert derive_forecast_etag(forecast_id=UUID_A, version_number=1) == f"{UUID_A}-v1"


def test_etag_format_for_header_quotes():
    assert format_forecast_etag_header(forecast_id=UUID_A, version_number=7) == f'"{UUID_A}-v7"'


def test_etag_parse_returns_none_for_wildcard():
    assert parse_forecast_etag_header("*") is None


def test_etag_parse_rejects_weak():
    with pytest.raises(CodecError):
        parse_forecast_etag_header(f'W/"{UUID_A}-v1"')


def test_etag_parse_rejects_unquoted():
    with pytest.raises(CodecError):
        parse_forecast_etag_header(f"{UUID_A}-v1")


def test_etag_round_trip_through_parser():
    bare = derive_forecast_etag(forecast_id=UUID_A, version_number=3)
    parsed = parse_forecast_etag_header(f'"{bare}"')
    assert parsed is not None and parsed.forecast_id == UUID_A and parsed.version_number == 3


# ----- Headers -------------------------------------------------------

def test_idempotency_key_accepts_visible_ascii():
    h = IdempotencyKeyHeader(value="abc-123")
    assert h.sha256_hex() == hashlib.sha256(b"abc-123").hexdigest()


def test_idempotency_key_rejects_empty():
    with pytest.raises(PydanticValidationError):
        IdempotencyKeyHeader(value="")


def test_idempotency_key_rejects_control_char():
    with pytest.raises(PydanticValidationError):
        IdempotencyKeyHeader(value="abc\x00")


def test_idempotency_key_rejects_oversize():
    with pytest.raises(PydanticValidationError):
        IdempotencyKeyHeader(value="a" * 256)


@pytest.mark.parametrize("value", ["abc\u00e9", "abc\U0001f4a9", "abc \u2603"])
def test_idempotency_key_rejects_non_ascii(value):
    with pytest.raises(PydanticValidationError):
        IdempotencyKeyHeader(value=value)


def test_if_match_accepts_wildcard():
    IfMatchHeader(value="*")


def test_if_match_accepts_quoted_etag():
    IfMatchHeader(value=f'"{UUID_A}-v4"')


def test_if_match_rejects_unquoted():
    with pytest.raises(PydanticValidationError):
        IfMatchHeader(value=f"{UUID_A}-v4")


def test_if_match_rejects_weak():
    with pytest.raises(PydanticValidationError):
        IfMatchHeader(value=f'W/"{UUID_A}-v1"')


def test_if_none_match_accepts_quoted_etag():
    IfNoneMatchHeader(value=f'"{UUID_A}-v1"')


# ----- Generation envelope ------------------------------------------

def test_generation_request_envelope_accepts_empty():
    GenerationRequestEnvelope()


def test_generation_request_envelope_rejects_any_field():
    with pytest.raises(PydanticValidationError):
        GenerationRequestEnvelope.model_validate({"balance": "9999"})


def test_generation_request_envelope_rejects_client_balance_field():
    with pytest.raises(PydanticValidationError):
        GenerationRequestEnvelope.model_validate({"current_balance": "1000"})


# ----- Sanitized error envelopes ------------------------------------

def test_validation_envelope_min_length_1():
    with pytest.raises(PydanticValidationError):
        ValidationErrorEnvelope(errors=[])


def test_validation_envelope_dedupes_loc_type():
    entry = {"loc": ("target_amount",), "type": "value_error"}
    with pytest.raises(PydanticValidationError):
        ValidationErrorEnvelope(errors=[entry, entry])


def test_validation_envelope_accepts_unique_entries():
    env = ValidationErrorEnvelope.model_validate({
        "errors": [{"loc": ("a",), "type": "value_error"},
                   {"loc": ("b",), "type": "too_short"}],
    })
    assert len(env.errors) == 2


def test_goal_not_found_envelope_is_stable():
    env = GoalNotFoundEnvelope.model_validate({})
    assert env.code == "goal_not_found" and env.message == "Goal not found."


def test_forecast_not_found_envelope_is_stable():
    env = ForecastNotFoundEnvelope.model_validate({})
    assert env.code == "forecast_not_found"


def test_idempotency_conflict_envelope_carries_no_input_value():
    env = IdempotencyConflictEnvelope.model_validate({})
    payload = env.model_dump()
    assert "idempotency_key" not in payload and "key" not in payload


def test_forecast_version_conflict_envelope_requires_etag_and_version():
    with pytest.raises(PydanticValidationError):
        # Missing required current_etag + latest_version_number.
        ForecastVersionConflictEnvelope.model_validate({})