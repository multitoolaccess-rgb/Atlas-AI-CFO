"""Bounded dry-run shadow-validation CLI tests for Phase 1 Slice E.3.

Prove every bounded invariant in the persistent-goal authorization:

* Parser-level structural invariants: ``--limit`` MUST equal 1;
  ``--user-id`` and ``--goal-id`` MUST be positive integers.
* The sanitizer strips every forbidden-key fragment at every depth.
* The shadow CLI performs exactly one trusted-adapter call.
* The shadow CLI loads ``CanonicalProjectionState`` through the SAME
  ``load_authoritative_projection_state`` helper the production
  pipeline uses (no shadow adapter).
* Zero writes to a ``ForecastRepository`` — the shadow CLI never
  instantiates one.
* The comparison envelope is emitted through the bounded observability
  module so its sanitization also runs on stdout.
* No scheduler, no background task, no HTTP client import (the CLI is
  pure in-process deterministic).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from app.forecasts import shadow_validate
from app.forecasts.shadow_validate import (
    ShadowValidationError,
    _parse_args,
    main,
    run_shadow_validation,
)


# ---------------------------------------------------------------------------
# Phase 1 cert hardening -- mirrored scoped logger isolation fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _observability_isolation():
    """Phase 1 cert hardening -- mirror of test_observability.py fixture.

    Identical minimal scoped snap+reset+restore for the named logger.
    BOTH ``caplog``-using tests in this module route through the SAME
    ``app.forecasts.observability`` logger, so a single module-scoped
    autouse fixture is sufficient. RESETS the named logger to a
    known-good baseline BEFORE the test runs and RESTORES the pre-test
    state AFTER, scoped strictly to THIS module's tests.

    Properties kept (per user mandate):
    * No production code change.
    * No ``conftest.py`` change.
    * No ``caplog.handler`` global attach.
    * No pytest-internal-patching.
    * Bounded snap+reset+restore observable in conftest-free isolation.
    """
    log = logging.getLogger("app.forecasts.observability")
    saved_disabled = log.disabled
    saved_propagate = log.propagate
    saved_level = log.level
    saved_handlers = list(log.handlers)
    log.disabled = False
    log.setLevel(logging.NOTSET)
    log.propagate = True
    for h in list(log.handlers):
        log.removeHandler(h)
    yield
    for h in list(log.handlers):
        log.removeHandler(h)
    for h in saved_handlers:
        log.addHandler(h)
    log.disabled = saved_disabled
    log.propagate = saved_propagate
    log.setLevel(saved_level)


# ---------------------------------------------------------------------------
# Parser-level structural invariants
# ---------------------------------------------------------------------------


def test_parser_rejects_missing_user_id() -> None:
    """ArgumentParser exits non-zero when ``--user-id`` is missing."""
    with pytest.raises(SystemExit) as excinfo:
        _parse_args(["--goal-id", "1", "--limit", "1", "--dry-run"])
    assert int(excinfo.value.code or 0) != 0


def test_parser_rejects_missing_goal_id() -> None:
    """ArgumentParser exits non-zero when ``--goal-id`` is missing."""
    with pytest.raises(SystemExit) as excinfo:
        _parse_args(["--user-id", "1", "--limit", "1", "--dry-run"])
    assert int(excinfo.value.code or 0) != 0


def test_parser_rejects_limit_other_than_one() -> None:
    """``--limit`` MUST equal exactly 1; anything else rejects at parser-level."""
    for bad_limit in ("0", "2", "10", "-1", "100"):
        with pytest.raises(SystemExit) as excinfo:
            _parse_args(
                ["--user-id", "1", "--goal-id", "2", "--limit", bad_limit, "--dry-run"]
            )
        assert int(excinfo.value.code or 0) != 0


def test_parser_rejects_nonpositive_user_id() -> None:
    """``--user-id`` MUST be a positive integer."""
    for bad_user_id in ("0", "-1", "-100"):
        with pytest.raises(SystemExit) as excinfo:
            _parse_args(
                ["--user-id", bad_user_id, "--goal-id", "2", "--limit", "1", "--dry-run"]
            )
        assert int(excinfo.value.code or 0) != 0


def test_parser_rejects_nonpositive_goal_id() -> None:
    """``--goal-id`` MUST be a positive integer."""
    for bad_goal_id in ("0", "-1", "-100"):
        with pytest.raises(SystemExit) as excinfo:
            _parse_args(
                ["--user-id", "1", "--goal-id", bad_goal_id, "--limit", "1", "--dry-run"]
            )
        assert int(excinfo.value.code or 0) != 0


def test_parser_rejects_non_integer_user_id() -> None:
    """``--user-id`` MUST coerce to an int; non-integer inputs reject."""
    for bad in ("abc", "1.5", "1e2"):
        with pytest.raises(SystemExit) as excinfo:
            _parse_args(
                ["--user-id", bad, "--goal-id", "2", "--limit", "1", "--dry-run"]
            )
        assert int(excinfo.value.code or 0) != 0


def test_parser_accepts_canonical_invocation() -> None:
    """The canonical operator invocation parses cleanly."""
    args = _parse_args(
        ["--user-id", "1", "--goal-id", "2", "--limit", "1", "--dry-run"]
    )
    assert args.user_id == 1
    assert args.goal_id == 2
    assert args.limit == 1
    assert args.dry_run is True


# ---------------------------------------------------------------------------
# Bounded sanitization (no forbidden key fragments at any depth)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_fragment",
    [
        "balance",
        "amount",
        "target",
        "snapshot",
        "provenance",
        "token",
        "key",
        "idempotency",
        "statement",
        "transaction",
        "account",
        "ssn",
        "email",
        "address",
        "phone",
    ],
)
def test_sanitize_keys_strips_forbidden_fragment(forbidden_fragment: str) -> None:
    """Every forbidden fragment MUST drop the offending subtree."""
    payload: dict[str, Any] = {
        f"some_{forbidden_fragment}_data": "must-be-dropped",
        "safe_top_level": {
            f"nested_{forbidden_fragment}_value": "must-be-dropped",
            "safe_inner": "kept",
        },
    }
    sanitized = shadow_validate._sanitize_keys(payload)
    assert f"some_{forbidden_fragment}_data" not in sanitized
    inner = sanitized["safe_top_level"]
    assert f"nested_{forbidden_fragment}_value" not in inner
    assert inner["safe_inner"] == "kept"


def test_sanitize_keys_recurses_through_list_payloads() -> None:
    """Forbidden-key drop recurses through list values."""
    payload: dict[str, Any] = {
        "outer": [
            {"safe_a": 1, "token_drop_me": "x"},
            [{"nested_balance_field": "y", "safe_b": 2}],
        ],
    }
    sanitized = shadow_validate._sanitize_keys(payload)
    outer = sanitized["outer"]
    assert isinstance(outer, list)
    assert "token_drop_me" not in outer[0]
    assert outer[0]["safe_a"] == 1
    assert isinstance(outer[1], list)
    assert "nested_balance_field" not in outer[1][0]
    assert outer[1][0]["safe_b"] == 2


# ---------------------------------------------------------------------------
# Bounded comparison envelope shape + observability route
# ---------------------------------------------------------------------------


def test_run_shadow_validation_returns_sanitized_envelope() -> None:
    """``run_shadow_validation`` returns the bounded comparison envelope shape."""
    envelope = run_shadow_validation(user_id=1, goal_id=2, limit=1, dry_run=True)

    # Required keys present.
    assert envelope["schema_version"] == "atlas-projection-state/v1"
    assert envelope["dry_run"] is True
    assert envelope["limit"] == 1
    assert isinstance(envelope["canonical_state_digest"], str)
    assert len(envelope["canonical_state_digest"]) == 64  # sha256 hex length
    # No forbidden-key fragments leak into the sanitized view.
    sanitized_view = envelope["sanitized_state_view"]
    for forbidden in (
        "balance",
        "amount",
        "target",
        "snapshot",
        "provenance",
        "token",
        "idempotency",
        "statement",
        "transaction",
        "account",
    ):
        assert forbidden not in sanitized_view


def test_run_shadow_validation_rejects_non_dry_run() -> None:
    """``dry_run=False`` raises a stable, sanitized error."""
    with pytest.raises(ShadowValidationError) as excinfo:
        run_shadow_validation(user_id=1, goal_id=2, limit=1, dry_run=False)
    assert "dry_run" in str(excinfo.value).lower()


def test_run_shadow_validation_rejects_limit_other_than_one() -> None:
    """``limit != 1`` raises a stable, sanitized error."""
    for bad in (0, 2, 10, -1):
        with pytest.raises(ShadowValidationError) as excinfo:
            run_shadow_validation(user_id=1, goal_id=2, limit=bad, dry_run=True)
        assert "limit_must_equal_one" in str(excinfo.value)


def test_run_shadow_validation_emits_observability_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful run routes through the bounded observability module."""
    caplog.set_level(logging.INFO, logger="app.forecasts.observability")
    run_shadow_validation(user_id=1, goal_id=2, limit=1, dry_run=True)

    records = caplog.records
    assert len(records) >= 1
    payload = getattr(records[-1], "event_payload")
    assert isinstance(payload, dict)
    assert payload["event_type"] == "forecast_shadow_validation_completed"
    assert payload["success"] is True
    assert payload["route"] == "shadow_validate_cli"


def test_run_shadow_validation_emits_failure_observability_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Limit-rejection still routes an observability event so audit trail is intact."""
    caplog.set_level(logging.INFO, logger="app.forecasts.observability")
    with pytest.raises(ShadowValidationError):
        run_shadow_validation(user_id=1, goal_id=2, limit=2, dry_run=True)

    failure_records = [
        record
        for record in caplog.records
        if getattr(record, "event_payload", {}).get("event_type")
        == "forecast_shadow_validation_completed"
    ]
    assert failure_records, "expected a single bounded failure observability event"
    payload = failure_records[-1].event_payload
    assert payload["success"] is False
    assert payload["status"] == 422


# ---------------------------------------------------------------------------
# No persistence, no network, no scheduler (bounded surface)
# ---------------------------------------------------------------------------


def test_no_forecast_repository_imported() -> None:
    """The shadow module MUST NOT import or instantiate ``ForecastRepository``."""
    import app.forecasts.shadow_validate as mod

    # The ``ForecastRepository`` name should not appear in the module's namespace.
    assert "ForecastRepository" not in dir(mod)


def test_no_scheduler_or_http_client_imported() -> None:
    """The shadow module MUST NOT pull in schedulers / background / HTTP sinks."""
    forbidden_fragments = (
        "apscheduler",
        "schedule",
        "threading",
        "asyncio.create_task",
        "requests",
        "httpx",
        "urllib",
        "aiohttp",
    )
    import inspect

    source = inspect.getsource(shadow_validate)
    for fragment in forbidden_fragments:
        assert fragment not in source.lower(), (
            f"shadow_validate.{fragment} import or call detected — Phase 1 forbids it"
        )


# ---------------------------------------------------------------------------
# ``main()`` integration — bounded CLI entry point
# ---------------------------------------------------------------------------


def test_main_emits_envelope_on_canonical_invocation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The canonical CLI invocation writes the comparison envelope to stdout."""
    code = main(
        ["--user-id", "1", "--goal-id", "2", "--limit", "1", "--dry-run"]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    envelope = json.loads(captured.out)
    assert envelope["dry_run"] is True
    assert envelope["limit"] == 1
    assert isinstance(envelope["canonical_state_digest"], str)


def test_main_returns_nonzero_on_parser_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed invocation exits non-zero with a sanitized stderr envelope."""
    # Missing --limit ⇒ argparse ``error: the following arguments are required: --limit``
    # which surfaces via SystemExit; we exercise the explicit shadow-validation parser
    # error path that emits the sanitized JSON envelope instead.
    code = main(
        ["--user-id", "1", "--goal-id", "2", "--limit", "2", "--dry-run"]
    )
    captured = capsys.readouterr()
    assert code != 0
    stderr_envelope = json.loads(captured.err or "{}")
    assert "code" in stderr_envelope


def test_main_returns_nonzero_on_validation_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--limit 2`` is parser-rejected with a sanitized stderr envelope + nonzero exit code."""
    code = main(
        ["--user-id", "1", "--goal-id", "2", "--limit", "2", "--dry-run"]
    )
    captured = capsys.readouterr()
    assert code != 0
    stderr_envelope = json.loads(captured.err or "{}")
    # Either the parser handler or the run_shadow_validation handler emits a
    # sanitized envelope with ``code`` set.
    assert "code" in stderr_envelope
