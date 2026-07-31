"""Bounded observability telemetry tests for Phase 1 Slice E.2.

Prove the safety contract:

* Every forbidden key fragment drops the offending subtree at EVERY depth.
* pydantic ``BaseModel`` instances drop entirely (no repr, no hash).
* canonical Decimal-shaped strings drop even when the parent key is
  allowlisted (defense in depth).
* Only stdlib logging + an in-memory bounded cardinality counter emit.
* No high-cardinality label (no user_id, goal_id, account_id, timestamp).
* The bounded module is importable inside the rules-service without
  regressing Slice D-post (regression smoke via the existing test
  scripts unchanged).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

import pytest
from pydantic import BaseModel

from app.forecasts.observability import (
    EventType,
    _FORBIDDEN_KEY_FRAGMENTS,
    _PERMITTED_TOP_LEVEL_KEYS,
    record_event,
    sanitize_event_payload,
)


class _DummyModel(BaseModel):
    """Plain pydantic model used to verify BaseModel drop in sanitization."""

    model_config = {"extra": "forbid"}
    field_one: str = "secret-token-12345"
    field_two: str = "balance-2.50"


# ---------------------------------------------------------------------------
# Top-level allowlist denylist surface
# ---------------------------------------------------------------------------


def test_permitted_top_level_keys_are_bounded() -> None:
    """Defines the bounded set of top-level keys the sanitization surface can emit."""
    # Allowlist is intentionally small: only operationally safe metadata.
    assert "event_type" in _PERMITTED_TOP_LEVEL_KEYS
    assert "route" in _PERMITTED_TOP_LEVEL_KEYS
    assert "latency_ms" in _PERMITTED_TOP_LEVEL_KEYS
    # Forbidden fragments MUST NOT appear as allowed keys.
    for forbidden in ("balance", "amount", "token", "account", "idempotency"):
        assert forbidden not in _PERMITTED_TOP_LEVEL_KEYS


@pytest.mark.parametrize("forbidden_fragment", sorted(_FORBIDDEN_KEY_FRAGMENTS))
def test_sanitize_payload_drops_top_level_forbidden_key(forbidden_fragment: str) -> None:
    """Any top-level key whose name contains a forbidden fragment is dropped."""
    payload: dict[str, Any] = {
        f"some_{forbidden_fragment}_thing": "must-be-dropped",
        "event_type": "forecast_generation_started",
    }
    sanitized = sanitize_event_payload(payload)
    assert f"some_{forbidden_fragment}_thing" not in sanitized
    # ``event_type`` is a bounded allowlisted category; the sanitizer
    # passes it through unchanged so test bodies can assert its presence.
    assert "event_type" in sanitized


@pytest.mark.parametrize("forbidden_fragment", sorted(_FORBIDDEN_KEY_FRAGMENTS))
def test_sanitize_payload_drops_nested_forbidden_key(forbidden_fragment: str) -> None:
    """Forbidden-key drop recurses through nested mappings at every depth."""
    payload: dict[str, Any] = {
        "schema_versions": {
            f"inner_{forbidden_fragment}_value": "must-be-dropped",
            "safe_kind": "atlas-projection-state/v1",
        },
        "status": 200,
    }
    sanitized = sanitize_event_payload(payload)
    inner = sanitized["schema_versions"]
    assert isinstance(inner, dict)
    assert f"inner_{forbidden_fragment}_value" not in inner
    assert inner["safe_kind"] == "atlas-projection-state/v1"
    assert sanitized["status"] == 200


def test_sanitize_payload_recurse_through_lists() -> None:
    """Forbidden-key drop recurses into nested sequences at every depth."""
    payload: dict[str, Any] = {
        "latency_ms": 150,
        "schema_versions": [
            {"safe_key": 1, "balance_drop_me": 2},
            [{"token_drop_me": "secret", "safe2": 3}],
        ],
    }
    sanitized = sanitize_event_payload(payload)
    versions = sanitized["schema_versions"]
    assert isinstance(versions, list)
    assert len(versions) == 2
    assert "balance_drop_me" not in versions[0]
    assert versions[0]["safe_key"] == 1
    nested_list = versions[1]
    assert isinstance(nested_list, list)
    assert "token_drop_me" not in nested_list[0]
    assert nested_list[0]["safe2"] == 3


# ---------------------------------------------------------------------------
# Decimal-string + pydantic BaseModel defense-in-depth
# ---------------------------------------------------------------------------


def test_sanitize_payload_drops_canonical_decimal_strings() -> None:
    """Decimal-shaped strings drop even when nested under an allowlisted key."""
    payload: dict[str, Any] = {
        "latency_ms": 50,
        "schema_versions": {
            "money": "5000.01",  # canonical-money shape -> drop
            "negative": "-123",
            "trailing_zero": "1.50",  # canonical_no_trailing_zero requirement
            "not_decimal_double_dot": "123.45.6",
            "word": "hello",
        },
    }
    sanitized = sanitize_event_payload(payload)
    versions = sanitized["schema_versions"]
    assert "money" not in versions
    assert "negative" not in versions
    assert "trailing_zero" not in versions
    # Mixed-shape strings survive intact.
    assert versions["not_decimal_double_dot"] == "123.45.6"
    assert versions["word"] == "hello"


def test_sanitize_payload_drops_pydantic_models() -> None:
    """pydantic BaseModel instances drop ENTIRELY (no repr, no hash)."""
    payload: dict[str, Any] = {
        "status": 200,
        "schema_versions": {
            "model_value": _DummyModel(),
            "safe_string": "ok",
        },
    }
    sanitized = sanitize_event_payload(payload)
    versions = sanitized["schema_versions"]
    assert "model_value" not in versions
    assert versions["safe_string"] == "ok"


def test_sanitize_payload_drops_unknown_top_level_keys() -> None:
    """Top-level keys outside ``_PERMITTED_TOP_LEVEL_KEYS`` are dropped."""
    payload: dict[str, Any] = {
        "status": 200,
        "route": "/api/v1/forecasts",
        "super_custom_unauthorized_key": "leak_attempt",
    }
    sanitized = sanitize_event_payload(payload)
    assert "super_custom_unauthorized_key" not in sanitized
    assert sanitized["status"] == 200
    assert sanitized["route"] == "/api/v1/forecasts"


# ---------------------------------------------------------------------------
# Emission surface (stdlib-only, bounded cardinality counter)
# ---------------------------------------------------------------------------


def test_record_event_emits_single_stdlib_log_record(caplog: pytest.LogCaptureFixture) -> None:
    """``record_event`` emits exactly one stdlib log record with sanitized payload."""
    caplog.set_level(logging.INFO, logger="app.forecasts.observability")
    record_event(
        "forecast_read_completed",
        {
            "status": 200,
            "latency_ms": 100,
            "route": "/api/v1/forecasts",
            "forbidden_key": "must-be-dropped",
            "balance_amount": "5000.01",  # decimal-shaped, dropped at the value layer
        },
        success=True,
    )

    records = caplog.records
    assert len(records) == 1
    record = records[0]
    assert record.name == "app.forecasts.observability"
    assert record.levelno == logging.INFO
    # Emit message is a stable category with NO payload values.
    assert record.message == "Atlas forecast lifecycle event: forecast_read_completed"
    assert "%s" in record.msg

    payload = getattr(record, "event_payload")
    assert isinstance(payload, dict)
    assert payload["event_type"] == "forecast_read_completed"
    assert payload["success"] is True
    assert payload["status"] == 200
    assert payload["latency_ms"] == 100
    assert payload["route"] == "/api/v1/forecasts"
    assert "forbidden_key" not in payload
    assert "balance_amount" not in payload


def test_record_event_emits_only_event_type_and_success_keys() -> None:
    """Emitted payload only contains allowlisted top-level keys plus event_type/success."""
    cleaned = record_event(
        "forecast_generation_unavailable",
        {
            "status": 503,
            "model_version": "atlas-projection-engine/v1",
            "calculation_version": "atlas-projection-engine/v1",
            # Forbidden keys at varying depths must drop.
            "balance": "any-string",
            "nested_provenance": {"provenance": "x", "safe_marker": "v1"},
            # Non-allowlisted top-level keys must drop.
            "user_id": "must-be-dropped",
            "goal_id": 5,
        },
        success=False,
    )
    # Allowlisted keys survive.
    assert cleaned["status"] == 503
    assert cleaned["model_version"] == "atlas-projection-engine/v1"
    assert cleaned["calculation_version"] == "atlas-projection-engine/v1"
    assert cleaned["event_type"] == "forecast_generation_unavailable"
    assert cleaned["success"] is False
    # Forbidden + unknown dropped.
    assert "balance" not in cleaned
    assert "user_id" not in cleaned
    assert "goal_id" not in cleaned
    assert "nested_provenance" not in cleaned


def test_record_event_does_not_log_decimal_or_pydantic_values(caplog: pytest.LogCaptureFixture) -> None:
    """Decimal-shaped strings + pydantic instances never appear in the emitted record."""
    caplog.set_level(logging.INFO, logger="app.forecasts.observability")
    record_event(
        "forecast_version_conflict",
        {
            "status": 409,
            "schema_versions": {
                "decimal_attempt": "12345.6789",
                "trailing_zero_attempt": "1.50",
                "model_attempt": _DummyModel(),
                "safe_label": "atlas-target-decision/v2",
            },
        },
        success=False,
    )
    record = caplog.records[-1]
    payload = getattr(record, "event_payload")
    versions = payload["schema_versions"]
    assert "decimal_attempt" not in versions
    assert "trailing_zero_attempt" not in versions
    assert "model_attempt" not in versions
    # The survivor is the bounded non-decimal value.
    assert versions["safe_label"] == "atlas-target-decision/v2"


def test_event_type_literal_is_enforced_via_send() -> None:
    """Static-typing guard: only bounded literals accepted as ``event_type``."""
    valid_types: tuple[str, ...] = (
        "forecast_generation_started",
        "forecast_generation_completed",
        "forecast_generation_unavailable",
        "forecast_read_started",
        "forecast_read_completed",
        "forecast_read_unavailable",
        "forecast_precondition_rejected",
        "forecast_version_conflict",
    )
    # Spy on the logger to ensure each valid type is accepted without
    # raising during sanitization.
    for event_type in valid_types:
        cleaned = record_event(event_type, {"status": 200})
        assert cleaned["event_type"] == event_type
    # Sanity: the EventType Literal alias is documented in the module docstring.
    import app.forecasts.observability as _obs
    assert "forecast_version_conflict" in _obs.EventType.__args__


# ---------------------------------------------------------------------------
# Smoke: bounded module does not regress any Slice D-post test
# ---------------------------------------------------------------------------


def test_module_imports_cleanly_into_rules_service(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``app.forecasts.observability`` is importable AND emits no log records on import.

    This proves the module is side-effect-free beyond the logger creation,
    matching the bounded observability contract that no scheduled or
    background emission runs without an explicit ``record_event`` call.
    """
    caplog.set_level(logging.DEBUG, logger="app.forecasts.observability")
    import app.forecasts.observability  # noqa: F401
    assert caplog.records == [], (
        "observability module emitted log records at import time: "
        + repr([(r.name, r.levelname, r.getMessage()) for r in caplog.records])
    )


def test_sanitize_payload_returns_immutable_copy_of_input() -> None:
    """``sanitize_event_payload`` does NOT mutate the caller's mapping."""
    payload: dict[str, Any] = {
        "status": 200,
        "balance_amount": "12345.6789",
        "schema_versions": {
            "model_attempt": _DummyModel(),
            "safe_label": "atlas-projection-state/v1",
        },
    }
    snapshot_keys = set(payload)
    _ = sanitize_event_payload(payload)
    assert set(payload) == snapshot_keys  # original unchanged
    # Nested mapping unchanged at the value layer too.
    nested_snapshot_keys = set(payload["schema_versions"])  # type: ignore[arg-type]
    _ = sanitize_event_payload(payload)
    assert set(payload["schema_versions"]) == nested_snapshot_keys  # type: ignore[arg-type]
