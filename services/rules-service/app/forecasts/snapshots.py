"""Deterministic, bounded immutable forecast snapshot serialization.

This boundary accepts only the explicit Phase 0 projection structures.  It does
not accept generic metadata maps: those can conceal raw financial source data
or credentials behind arbitrary keys and would become immutable on persistence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.forecasts.canonical_state import CanonicalProjectionState, canonical_json, hash_input_state

_CANONICAL_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9._:-]*$")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SCENARIOS = frozenset({"conservative", "base", "optimistic"})
_MAX_SNAPSHOT_KEYS = 8
_MAX_SNAPSHOT_STRING_LENGTH = 128


@dataclass(frozen=True)
class ForecastSnapshots:
    """Canonical persisted snapshot strings; raw source payloads are impossible."""

    input_snapshot_json: str
    assumption_snapshot_json: str
    output_snapshot_json: str
    provenance_snapshot_json: str
    input_state_hash: str


def _reject_snapshot() -> None:
    """Raise a stable error without reflecting rejected input or keys."""

    raise ValueError("forecast snapshots must match the bounded projection contract")


def _mapping(value: Any, *, allowed: frozenset[str], required: frozenset[str] = frozenset()) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or len(value) > _MAX_SNAPSHOT_KEYS:
        _reject_snapshot()
    if set(value) - allowed or not required <= set(value):
        _reject_snapshot()
    if not all(isinstance(key, str) for key in value):
        _reject_snapshot()
    return value


def _identifier(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_SNAPSHOT_STRING_LENGTH
        or not _IDENTIFIER.fullmatch(value)
    ):
        _reject_snapshot()
    return value


def _decimal(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 40
        or not _CANONICAL_DECIMAL.fullmatch(value)
    ):
        _reject_snapshot()
    return value


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        _reject_snapshot()
    return value


def _date(value: Any) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        _reject_snapshot()
    return value


def _validate_assumption_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _mapping(
        value,
        allowed=frozenset(
            {
                "assumption_profile",
                "annual_return_rates",
                "annual_inflation_rate",
                "contribution_timing",
                "period",
                "rounding_rule",
                "money_precision",
            }
        ),
        required=frozenset({"assumption_profile"}),
    )
    result: dict[str, Any] = {"assumption_profile": _identifier(snapshot["assumption_profile"])}
    if "annual_return_rates" in snapshot:
        rates = _mapping(
            snapshot["annual_return_rates"], allowed=_SCENARIOS, required=_SCENARIOS
        )
        result["annual_return_rates"] = {
            scenario: _decimal(rates[scenario]) for scenario in sorted(_SCENARIOS)
        }
    if "annual_inflation_rate" in snapshot:
        result["annual_inflation_rate"] = _decimal(snapshot["annual_inflation_rate"])
    if "contribution_timing" in snapshot:
        if snapshot["contribution_timing"] not in {"beginning", "end"}:
            _reject_snapshot()
        result["contribution_timing"] = snapshot["contribution_timing"]
    if "period" in snapshot:
        if snapshot["period"] != "monthly":
            _reject_snapshot()
        result["period"] = "monthly"
    if "rounding_rule" in snapshot:
        if snapshot["rounding_rule"] != "ROUND_HALF_EVEN":
            _reject_snapshot()
        result["rounding_rule"] = "ROUND_HALF_EVEN"
    if "money_precision" in snapshot:
        result["money_precision"] = _decimal(snapshot["money_precision"])
    return result


def _validate_output_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = _mapping(value, allowed=frozenset({"target_status", "drivers", "scenarios"}))
    result: dict[str, Any] = {}
    if "target_status" in snapshot:
        if not isinstance(snapshot["target_status"], bool):
            _reject_snapshot()
        result["target_status"] = snapshot["target_status"]
    if "drivers" in snapshot:
        drivers = _mapping(
            snapshot["drivers"],
            allowed=frozenset(
                {
                    "current_balance",
                    "monthly_contribution",
                    "total_contributions",
                    "target_amount",
                    "horizon_months",
                    "data_as_of",
                    "data_age_days",
                }
            ),
        )
        result["drivers"] = {
            key: (
                _decimal(item, nullable=key == "target_amount")
                if key
                in {"current_balance", "monthly_contribution", "total_contributions", "target_amount"}
                else _nonnegative_int(item)
                if key in {"horizon_months", "data_age_days"}
                else _date(item)
            )
            for key, item in drivers.items()
        }
    if "scenarios" in snapshot:
        scenarios = _mapping(snapshot["scenarios"], allowed=_SCENARIOS, required=_SCENARIOS)
        result["scenarios"] = {}
        for scenario in sorted(_SCENARIOS):
            values = _mapping(
                scenarios[scenario],
                allowed=frozenset(
                    {
                        "annual_return_rate",
                        "monthly_real_rate",
                        "ending_balance",
                        "investment_growth",
                        "target_gap",
                        "reaches_target",
                    }
                ),
                required=frozenset(
                    {"annual_return_rate", "ending_balance", "investment_growth", "reaches_target"}
                ),
            )
            result["scenarios"][scenario] = {
                key: (
                    _decimal(item, nullable=key == "target_gap")
                    if key
                    in {
                        "annual_return_rate",
                        "monthly_real_rate",
                        "ending_balance",
                        "investment_growth",
                        "target_gap",
                    }
                    else item
                )
                for key, item in values.items()
            }
            if not isinstance(result["scenarios"][scenario]["reaches_target"], bool):
                _reject_snapshot()
    return result


def build_forecast_snapshots(
    *,
    state: CanonicalProjectionState,
    assumption_snapshot: Mapping[str, Any],
    output_snapshot: Mapping[str, Any],
) -> ForecastSnapshots:
    """Build deterministic snapshots from bounded server-owned projection data."""

    assumptions = _validate_assumption_snapshot(assumption_snapshot)
    output = _validate_output_snapshot(output_snapshot)
    payload = state.hash_payload()
    return ForecastSnapshots(
        input_snapshot_json=canonical_json(payload),
        assumption_snapshot_json=canonical_json(assumptions),
        output_snapshot_json=canonical_json(output),
        provenance_snapshot_json=canonical_json(
            {"provenance": payload["provenance"], "freshness": payload["freshness"]}
        ),
        input_state_hash=hash_input_state(state),
    )
