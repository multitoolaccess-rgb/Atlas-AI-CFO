"""Bounded observability telemetry boundary for Phase 1 Slice E.2.

This module is the ONLY Phase-1 sanctioned entry point for emitting
structured forecast-event telemetry.  It enforces these invariants by
construction:

* No PII / no financial payload / no provenance leakage.  Raw canonical
  Decimal strings, pydantic ``BaseModel`` instances, and any key whose
  name contains a forbidden fragment are dropped recursively before any
  sink is touched.
* Strict server-owned field allowlist for top-level payload keys.  No
  value flows to the wire / log / metric unless its key appears in the
  bounded ``_PERMITTED_TOP_LEVEL_KEYS`` frozenset.
* Pure bounded-cardinality counter, labeled only by ``event_type`` and a
  boolean ``success`` flag.  No high-cardinality labels (no ``user_id``,
  no ``goal_id``, no ``account_id``, no timestamp).
* Stdlib ``logging`` + in-memory ``prometheus_client`` ``Counter`` are
  the ONLY emission surfaces.  No network sinks, no OpenTelemetry
  auto-rollout, no scheduled emission.
* External multi-user production enablement is structurally blocked
  pending the Phase 1 retention / user-deletion policy approval.

Slice E.2 is the ONLY authorized telemetry boundary.  Routes or services
that need to emit forecast lifecycle events MUST route through
``record_event`` so the bounded sanitization runs on every payload.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal, Union

from pydantic import BaseModel


_logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public bounded event-type literal (enforced via typing.Literal in tests)
# ---------------------------------------------------------------------------

EventType = Literal[
    "forecast_generation_started",
    "forecast_generation_completed",
    "forecast_generation_unavailable",
    "forecast_read_started",
    "forecast_read_completed",
    "forecast_read_unavailable",
    "forecast_precondition_rejected",
    "forecast_version_conflict",
]


# ---------------------------------------------------------------------------
# Bounded top-level allowlist + substring-based exclusion surface
# ---------------------------------------------------------------------------

_PERMITTED_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "event_type",
        "route",
        "status",
        "latency_ms",
        "model_version",
        "calculation_version",
        "schema_versions",
        "http_method",
        "user_scope",
        "dry_run",
        # ``success`` is the bounded boolean label that pairs with
        # ``event_type`` for the cardinality-safe counter; it is the ONLY
        # boolean outcome marker permitted in the emitted payload.
        "success",
    }
)

_FORBIDDEN_KEY_FRAGMENTS: Final[frozenset[str]] = frozenset(
    {
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
    }
)


# Canonical-rounding Decimal pattern (matches the canonical-money envelope
# AND the calculation-decimal envelope).  Used for defense-in-depth so that
# even if an operator mislabels a value with an allowlisted key, a raw
# money-shaped string is still dropped.
_CANONICAL_DECIMAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$"
)


# ---------------------------------------------------------------------------
# Bounded cardinality metric
# ---------------------------------------------------------------------------

try:  # pragma: no cover - prometheus_client is optional in test envs
    from prometheus_client import Counter as _PromCounter

    _OPS_COUNTER = _PromCounter(
        "atlas_forecast_ops_observability_total",
        "Total bounded forecast lifecycle operations "
        "(Cardinality bounded to event_type x success).",
        ["event_type", "success"],
    )
except ImportError:  # pragma: no cover - fallback is unit-test friendly
    _OPS_COUNTER = None


# ---------------------------------------------------------------------------
# Recursive sanitization helpers (purely private to the module)
# ---------------------------------------------------------------------------


def _key_is_forbidden(key: Any) -> bool:
    """``True`` iff ``key`` contains any forbidden fragment (case-insensitive)."""
    if not isinstance(key, str):
        return True
    normalized = key.lower()
    return any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS)


def _is_decimal_string(value: Any) -> bool:
    """``True`` iff ``value`` is a string that matches the canonical Decimal shape."""
    return (
        isinstance(value, str)
        and bool(_CANONICAL_DECIMAL_PATTERN.fullmatch(value))
    )


def _sanitize_value(value: Any) -> Union[str, int, float, bool, dict[str, Any], list[Any], None]:
    """Recursively scrub Pydantic models, decimal strings, and forbidden shapes.

    Returns a sanitized scalar / dict / list, or ``None`` when the entire
    subtree should be omitted.
    """
    # 1. Pydantic BaseModel: drop entirely (no repr, no hash).  Keeps
    #    financial / snapshot / provenance payloads from leaking through
    #    any accidentally-allowlisted parent key.
    if isinstance(value, BaseModel):
        return None

    # 2. Mapping: recurse, dropping forbidden keys at every depth.
    if isinstance(value, Mapping):
        sanitized_dict: dict[str, Any] = {}
        for nested_key, nested_value in value.items():
            if _key_is_forbidden(nested_key):
                continue
            cleaned = _sanitize_value(nested_value)
            if cleaned is not None:
                sanitized_dict[str(nested_key)] = cleaned
        return sanitized_dict

    # 3. Sequence: recurse, dropping any element that sanitized to ``None``.
    if isinstance(value, (list, tuple, set, frozenset)) and not isinstance(value, (str, bytes, bytearray)):
        sanitized_list: list[Any] = []
        for item in value:
            cleaned_item = _sanitize_value(item)
            if cleaned_item is not None:
                sanitized_list.append(cleaned_item)
        return sanitized_list

    # 4. Decimal-shaped string: defense-in-depth drop, even when the key
    #    is allowlisted.  Prevents raw money values (balances / contributions
    #    / targets) from leaking through mislabeled fields.
    if _is_decimal_string(value):
        return None

    # 5. Plain scalars: pass through.  Caller is responsible for type-narrowing.
    return value


def sanitize_event_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the bounded subset of ``payload`` that may be emitted.

    Drops every top-level key outside ``_PERMITTED_TOP_LEVEL_KEYS`` and
    every forbidden fragment substring; recurses into mappings and
    sequences; drops pydantic BaseModel instances and Decimal-shaped
    strings entirely.
    """
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in _PERMITTED_TOP_LEVEL_KEYS:
            continue
        if _key_is_forbidden(key):
            continue
        cleaned = _sanitize_value(value)
        if cleaned is not None:
            sanitized[key] = cleaned
    return sanitized


def record_event(
    event_type: EventType,
    payload: Mapping[str, Any] = ...,
    *,
    success: bool = True,
) -> dict[str, Any]:
    """Emit one bounded forecast lifecycle event.

    Returns the sanitized payload dict (useful for tests; the caller's
    reference is NOT reused).  Increments the bounded ``event_type`` x
    ``success`` cardinality counter and emits a single stdlib log record.
    """
    if payload is ...:
        payload = {}
    cleaned = sanitize_event_payload(payload)
    cleaned["event_type"] = event_type
    cleaned["success"] = bool(success)

    if _OPS_COUNTER is not None:  # pragma: no cover - guarded import path
        _OPS_COUNTER.labels(
            event_type=event_type,
            success=str(bool(success)).lower(),
        ).inc()

    _logger.info(
        "Atlas forecast lifecycle event: %s",
        event_type,
        extra={"event_payload": cleaned},
    )
    return cleaned


__all__ = [
    "EventType",
    "record_event",
    "sanitize_event_payload",
]
