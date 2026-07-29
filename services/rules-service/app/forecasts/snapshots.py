"""Deterministic, privacy-minimized immutable forecast snapshot serialization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.forecasts.canonical_state import CanonicalProjectionState, canonical_json, hash_input_state

_FORBIDDEN_RAW_KEYS = frozenset(
    {
        "credentials",
        "idempotency_key",
        "raw_statement",
        "raw_statements",
        "raw_transaction",
        "raw_transactions",
        "statement",
        "statements",
        "token",
        "tokens",
        "upload",
        "uploads",
    }
)


@dataclass(frozen=True)
class ForecastSnapshots:
    """Canonical persisted snapshot strings; no raw source payloads are accepted."""

    input_snapshot_json: str
    assumption_snapshot_json: str
    output_snapshot_json: str
    provenance_snapshot_json: str
    input_state_hash: str


def _reject_raw_payload(value: Any) -> None:
    """Reject known raw-source and secret fields before serialization."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_RAW_KEYS:
                raise ValueError("forecast snapshots must not contain raw source payloads")
            _reject_raw_payload(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_raw_payload(nested)


def build_forecast_snapshots(
    *,
    state: CanonicalProjectionState,
    assumption_snapshot: Mapping[str, Any],
    output_snapshot: Mapping[str, Any],
) -> ForecastSnapshots:
    """Build deterministic snapshots from bounded server-owned data only."""

    _reject_raw_payload(assumption_snapshot)
    _reject_raw_payload(output_snapshot)
    payload = state.hash_payload()
    return ForecastSnapshots(
        input_snapshot_json=canonical_json(payload),
        assumption_snapshot_json=canonical_json(dict(assumption_snapshot)),
        output_snapshot_json=canonical_json(dict(output_snapshot)),
        provenance_snapshot_json=canonical_json(
            {"provenance": payload["provenance"], "freshness": payload["freshness"]}
        ),
        input_state_hash=hash_input_state(state),
    )
