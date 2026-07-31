"""Bounded dry-run shadow-validation CLI for Phase 1 Slice E.3.

This module is the ONLY sanctioned operator entry point for ad-hoc
shadow validation of the ``CanonicalProjectionState`` pipeline.  It
enforces the bounded invariants by construction at the argparse layer:

* Exactly ONE user (``--user-id``, required, integer-positive).
* Exactly ONE goal (``--goal-id``, required, integer-positive).
* ``--limit`` MUST equal literally 1 (parser-level ``choices=[1]``).
* ``--dry-run`` is the ONLY supported mode; the CLI emits its
  comparison output as a deterministic shallow-fixture pair and
  performs ZERO writes to the immutable forecast repository.

Hardened safety contract (proved by the bounded test suite):

* No external network sinks, no timed jobs, no background task.
* No mutation of any persistent state.  The shadow CLI does NOT
  instantiate a ``ForecastRepository`` and does NOT route through
  ``ForecastGenerationService.generate`` (which persists).
* Lifecycle events route through the already-merged Slice E.2
  ``observability.record_event`` so the bounded sanitization runs on
  every payload.
* External multi-user production enablement remains BLOCKED pending
  the Phase 1 retention / user-deletion policy approval.

The ONLY approved invocation::

    python -m app.forecasts.shadow_validate \\
        --user-id <id> --goal-id <id> --limit 1 --dry-run

with concrete IDs substituted at operator run time.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping
from typing import Any, Final

from app.forecasts.canonical_state import (
    CANONICAL_JSON_VERSION,
    CanonicalProjectionState,
    HASH_ALGORITHM,
    HASH_SCHEMA_VERSION,
    PROJECTION_STATE_SCHEMA_VERSION,
    hash_input_state,
    load_authoritative_projection_state,
)
from app.forecasts.observability import record_event


_logger: logging.Logger = logging.getLogger("app.forecasts.shadow_validate")

_SHADOW_VALIDATION_EVENT_TYPE: Final[str] = "forecast_shadow_validation_completed"

_SHADOW_AS_OF_TIMESTAMP: Final[str] = "2024-01-01T00:00:00Z"

_SHADOW_SYNTHETIC_SOURCE_STATE_HASH: Final[str] = "0" * 64


# ---------------------------------------------------------------------------
# Bounded error envelope (sanitized)
# ---------------------------------------------------------------------------


class ShadowValidationError(RuntimeError):
    """Stable, sanitized error condition; callers surface ``str(exc)`` only."""


def _sanitize_keys(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively strip any key whose name contains a forbidden fragment.

    Mirrors the Slice E.2 ``observability.sanitize_event_payload``
    exclusion surface so the CLI's stdout envelope stays bounded even
    when future versions of the synthetic state add new fields.
    """

    def _walk(value: Any) -> Any:
        if isinstance(value, Mapping):
            cleaned: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    continue
                normalized = key.lower()
                if any(
                    fragment in normalized
                    for fragment in (
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
                    )
                ):
                    continue
                inner = _walk(item)
                if inner is not None:
                    cleaned[key] = inner
            return cleaned
        if isinstance(value, (list, tuple, set, frozenset)) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            return [
                element
                for element in (_walk(item) for item in value)
                if element is not None
            ]
        return value

    return _walk(payload)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Deterministic synthetic canonical-state factory (operator preview)
# ---------------------------------------------------------------------------


def _build_synthetic_canonical_state(
    *, user_id: int, goal_id: int
) -> CanonicalProjectionState:
    """Build a deterministic synthetic canonical state for shadow validation.

    The synthetic state is intentionally minimal AND uses the SAME pydantic
    validation surface (via ``CanonicalProjectionState.model_validate``)
    that the trusted adapter uses in production.  This exercises the
    canonicalization + hashing path end-to-end without any network.
    """
    synthetic_dict: dict[str, Any] = {
        "schema_version": PROJECTION_STATE_SCHEMA_VERSION,
        "canonicalization": {
            "canonical_json_version": CANONICAL_JSON_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "hash_algorithm": HASH_ALGORITHM,
        },
        "user_id": f"shadow-user-{user_id}",
        "goal_id": goal_id,
        "as_of_timestamp": _SHADOW_AS_OF_TIMESTAMP,
        "currency": "USD",
        "current_value_components": [
            {
                "kind": "cash",
                "amount": "0",
                "source_reference": "shadow-cash-component",
                "observed_at": _SHADOW_AS_OF_TIMESTAMP,
            }
        ],
        "contribution_inputs": [
            {
                "kind": "monthly_investable_cash_flow",
                "amount": "0",
                "source_reference": "shadow-monthly-contribution",
                "observed_at": _SHADOW_AS_OF_TIMESTAMP,
            }
        ],
        "freshness": {
            "max_data_age_days": 30,
            "observed_age_days": 0,
            "source_updated_at": _SHADOW_AS_OF_TIMESTAMP,
        },
        "provenance": [
            {
                "source_system": "shadow-validation",
                "reference_id": f"shadow-ref-{goal_id}",
                "observed_at": _SHADOW_AS_OF_TIMESTAMP,
                "record_count": 0,
                "source_state_hash": _SHADOW_SYNTHETIC_SOURCE_STATE_HASH,
            }
        ],
        "missing_data_codes": (),
        "reconciliation_state": "reconciled",
    }
    return CanonicalProjectionState.model_validate(synthetic_dict)


# ---------------------------------------------------------------------------
# Deterministic in-memory trusted adapter (no network)
# ---------------------------------------------------------------------------


class _ShadowTrustedAdapter:
    """In-memory adapter implementing ``FinlynqProjectionStateAdapter``.

    Returns the deterministic synthetic state constructed by
    ``_build_synthetic_canonical_state`` so the shadow CLI can be
    operated without any network access during local validation.
    The shape mirrors the production
    ``HttpFinlynqProjectionStateAdapter`` so a future bounded slice
    could swap in the real adapter once an isolated HTTP fixture
    exists; this stub is the Phase 1 sanctioned operator path.
    """

    def __init__(self, *, user_id: int, goal_id: int) -> None:
        self._state = _build_synthetic_canonical_state(
            user_id=user_id, goal_id=goal_id
        )

    def load_projection_state(
        self, *, user_id: str, goal_id: int
    ) -> CanonicalProjectionState:
        if user_id != self._state.user_id:
            raise ShadowValidationError("shadow_user_scope_mismatch")
        if goal_id != self._state.goal_id:
            raise ShadowValidationError("shadow_goal_scope_mismatch")
        return self._state


# ---------------------------------------------------------------------------
# Bounded CLI parser (structural invariants enforced at parse-time)
# ---------------------------------------------------------------------------


def _positive_int(value: str) -> int:
    """Argparse type: positive integer only.

    Raises ``argparse.ArgumentTypeError`` for non-integer strings,
    zero, or negative integers.  Combined with ``exit_on_error=False``
    on the parser this avoids argparse writing plain-text usage to
    stderr, so ``main()`` can emit a deterministic sanitized JSON
    envelope on every parser failure.
    """
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"must be a positive integer (got {value!r})"
        ) from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            f"must be a positive integer (got {parsed})"
        )
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.forecasts.shadow_validate",
        description=(
            "Bounded dry-run shadow-validation CLI (Phase 1 Slice E.3). "
            "Exactly one user, one goal, limit=1, dry-run only. "
            "No persistence. No background. No cron workloads."
        ),
        exit_on_error=False,
    )
    parser.add_argument(
        "--user-id",
        type=_positive_int,
        required=True,
        help="Single bounded user_id (positive integer, must match the trusted adapter scope).",
    )
    parser.add_argument(
        "--goal-id",
        type=_positive_int,
        required=True,
        help="Single bounded goal_id (positive integer, must match the trusted adapter scope).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        choices=[1],
        required=True,
        help="Structural invariant: must equal exactly 1 (Phase 1 single-pair dry-run).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Required dry-run marker. The CLI ALWAYS runs in dry-run; this flag is informational.",
    )
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _build_parser()
    # With ``exit_on_error=False``, ``parse_args`` raises
    # ``argparse.ArgumentError`` for argument rejection and
    # ``argparse.ArgumentTypeError`` for type-coercion failures rather
    # than calling ``sys.exit`` and writing plain-text usage to stderr.
    # Re-raise as ``SystemExit(2)`` so the caller-side contract is
    # preserved (existing tests in this module expect ``SystemExit``),
    # while ``main()`` still catches the ``SystemExit`` to emit a
    # sanitized JSON envelope to stderr instead of argparse's plain
    # usage output.
    try:
        return parser.parse_args(argv)
    except (argparse.ArgumentError, argparse.ArgumentTypeError) as exc:
        raise SystemExit(2) from exc


# ---------------------------------------------------------------------------
# Shadow validation entry point
# ---------------------------------------------------------------------------


def run_shadow_validation(
    *, user_id: int, goal_id: int, limit: int, dry_run: bool
) -> dict[str, Any]:
    """Execute the bounded shadow-validation comparison envelope.

    Returns a sanitized comparison envelope dict.  ``limit`` MUST equal 1
    and ``dry_run`` MUST be True; callers that bypass the parser WILL
    hit the structural invariant assertion below.
    """
    if limit != 1:
        record_event(
            _SHADOW_VALIDATION_EVENT_TYPE, {"status": 422}, success=False
        )
        raise ShadowValidationError(
            f"shadow_validation_limit_must_equal_one (got {limit})"
        )
    if not dry_run:
        record_event(
            _SHADOW_VALIDATION_EVENT_TYPE, {"status": 422}, success=False
        )
        raise ShadowValidationError("shadow_validation_must_be_dry_run")

    adapter = _ShadowTrustedAdapter(user_id=user_id, goal_id=goal_id)
    state = load_authoritative_projection_state(
        adapter=adapter,
        server_user_id=f"shadow-user-{user_id}",
        server_goal_id=goal_id,
    )
    state_digest = hash_input_state(state)

    sanitized_state_view = _sanitize_keys(
        {
            "schema_version": state.schema_version,
            "currency": state.currency,
            "reconciliation_state": state.reconciliation_state,
        }
    )

    comparison_envelope: dict[str, Any] = {
        "schema_version": PROJECTION_STATE_SCHEMA_VERSION,
        "dry_run": True,
        "limit": 1,
        "canonical_state_digest": state_digest,
        "sanitized_state_view": sanitized_state_view,
    }

    record_event(
        _SHADOW_VALIDATION_EVENT_TYPE,
        {
            "status": 200,
            "route": "shadow_validate_cli",
            "model_version": "atlas-shadow-validation/v1",
            "calculation_version": PROJECTION_STATE_SCHEMA_VERSION,
            "schema_versions": {
                "projection_state": PROJECTION_STATE_SCHEMA_VERSION,
                "canonical_json": CANONICAL_JSON_VERSION,
            },
        },
        success=True,
    )

    return comparison_envelope


def _emit_envelope_json(envelope: Mapping[str, Any]) -> str:
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse args, run shadow validation, emit JSON envelope.

    Emits a bounded sanitized JSON envelope to stderr on EVERY non-zero
    exit so operator output is machine-parseable.  Exit codes:

    * ``0`` — canonical invocation succeeded; envelope on stdout.
    * ``2`` — parser rejection or ``run_shadow_validation`` rejected
      input (bounded validation failure).
    * ``1`` — last-resort internal failure.
    """
    try:
        args = _parse_args(argv)
    except (
        argparse.ArgumentError,
        argparse.ArgumentTypeError,
        SystemExit,
    ) as exc:
        print(
            _emit_envelope_json(
                {
                    "status": "error",
                    "code": "parser_rejection",
                    "message": "bounded argument rejected by parser",
                }
            ),
            file=sys.stderr,
        )
        record_event(
            _SHADOW_VALIDATION_EVENT_TYPE, {"status": 422}, success=False
        )
        return 2
    except Exception as exc:  # pragma: no cover - last-resort guard
        _logger.exception("shadow_validation_parser_unhandled_exception")
        print(
            _emit_envelope_json(
                {
                    "status": "error",
                    "code": "internal_failure",
                    "message": type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        record_event(
            _SHADOW_VALIDATION_EVENT_TYPE, {"status": 500}, success=False
        )
        return 2

    try:
        envelope = run_shadow_validation(
            user_id=int(args.user_id),
            goal_id=int(args.goal_id),
            limit=int(args.limit),
            dry_run=bool(args.dry_run),
        )
    except ShadowValidationError as exc:
        print(
            _emit_envelope_json(
                {
                    "status": "error",
                    "code": "validation_failure",
                    "message": "bounded validation rejected input",
                }
            ),
            file=sys.stderr,
        )
        record_event(
            _SHADOW_VALIDATION_EVENT_TYPE, {"status": 422}, success=False
        )
        return 2
    except Exception as exc:  # pragma: no cover - last-resort guard
        _logger.exception("shadow_validation_unhandled_exception")
        print(
            _emit_envelope_json(
                {
                    "status": "error",
                    "code": "internal_failure",
                    "message": type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        record_event(
            _SHADOW_VALIDATION_EVENT_TYPE, {"status": 500}, success=False
        )
        return 1

    print(_emit_envelope_json(envelope))
    return 0


__all__ = [
    "ShadowValidationError",
    "main",
    "run_shadow_validation",
]


if __name__ == "__main__":  # pragma: no cover - guarded by entry-point tests
    # ``python -m app.forecasts.shadow_validate`` path
    sys.exit(main())
