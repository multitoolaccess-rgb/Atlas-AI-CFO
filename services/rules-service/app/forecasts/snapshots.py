"""Deterministic, bounded immutable forecast snapshot serialization.

This boundary accepts only the explicit Phase 0 projection structures.  It does
not accept generic metadata maps: those can conceal raw financial source data
or credentials behind arbitrary keys and would become immutable on persistence.
"""

from __future__ import annotations

import re
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.forecasts.canonical_state import (
    CanonicalProjectionState,
    CanonicalStateValidationError,
    canonical_decimal_string,
    canonical_json,
)

_CANONICAL_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9._:-]*$")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SCENARIOS = frozenset({"conservative", "base", "optimistic"})
ASSUMPTION_SCHEMA_VERSION = "atlas-projection-assumptions/v1"
TARGET_DECISION_SCHEMA_VERSION = "atlas-target-decision/v1"
CALCULATION_DECIMAL_SCHEMA_VERSION = "atlas-calculation-decimal/v1"
_MAX_SNAPSHOT_KEYS = 8
_MAX_SNAPSHOT_STRING_LENGTH = 128
_MAX_CALCULATION_DIGITS = 50
_MAX_CALCULATION_SCALE = 64
_MAX_CALCULATION_LENGTH = 128


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
    if not isinstance(value, str) or not _CANONICAL_DECIMAL.fullmatch(value):
        _reject_snapshot()
    try:
        if canonical_decimal_string(value) != value:
            _reject_snapshot()
    except CanonicalStateValidationError:
        _reject_snapshot()
    return value


def calculation_decimal_string(value: Decimal) -> str:
    """Serialize a finite Phase 0 Decimal exactly, without ambient context.

    This is deliberately distinct from canonical input-money strings. Bounds are
    checked from Decimal tuple metadata before any exponent expansion.
    """
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("forecast_output_out_of_range")
    sign, digits, exponent = value.as_tuple()
    first = next((i for i, digit in enumerate(digits) if digit), None)
    if first is None:
        return "0"
    last = len(digits) - 1 - next(i for i, digit in enumerate(reversed(digits)) if digit)
    coefficient = "".join(str(digit) for digit in digits[first:last + 1])
    effective_exponent = exponent + (len(digits) - 1 - last)
    significant = len(coefficient)
    scale = max(-effective_exponent, 0)
    integral = significant + effective_exponent if effective_exponent >= 0 else max(significant + effective_exponent, 1)
    length = (1 if sign else 0) + integral + (1 + scale if scale else 0)
    if significant > _MAX_CALCULATION_DIGITS or scale > _MAX_CALCULATION_SCALE or length > _MAX_CALCULATION_LENGTH:
        raise ValueError("forecast_output_out_of_range")
    if effective_exponent >= 0:
        result = coefficient + ("0" * effective_exponent)
    else:
        point = len(coefficient) + effective_exponent
        result = coefficient[:point] + "." + coefficient[point:] if point > 0 else "0." + ("0" * -point) + coefficient
    result = result.rstrip("0").rstrip(".") if "." in result else result
    return f"-{result}" if sign else result


def _calculation_decimal(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or "e" in value.lower():
        _reject_snapshot()
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        _reject_snapshot()
    if calculation_decimal_string(parsed) != value:
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
                "assumption_schema_version",
                "annual_return_rates",
                "annual_inflation_rate",
                "contribution_timing",
                "period",
                "rounding_rule",
                "money_precision",
            }
        ),
        required=frozenset(
            {
                "assumption_profile",
                "assumption_schema_version",
                "annual_return_rates",
                "annual_inflation_rate",
                "contribution_timing",
                "period",
                "rounding_rule",
                "money_precision",
            }
        ),
    )
    if snapshot["assumption_schema_version"] != ASSUMPTION_SCHEMA_VERSION:
        _reject_snapshot()
    result: dict[str, Any] = {
        "assumption_profile": _identifier(snapshot["assumption_profile"]),
        "assumption_schema_version": ASSUMPTION_SCHEMA_VERSION,
    }
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
    snapshot = _mapping(
        value,
        allowed=frozenset({"calculation_decimal_schema_version", "target_status", "target_decision", "drivers", "scenarios"}),
        required=frozenset(
            {"calculation_decimal_schema_version", "target_status", "target_decision", "drivers", "scenarios"}
        ),
    )
    if snapshot["calculation_decimal_schema_version"] != CALCULATION_DECIMAL_SCHEMA_VERSION:
        _reject_snapshot()
    result: dict[str, Any] = {"calculation_decimal_schema_version": CALCULATION_DECIMAL_SCHEMA_VERSION}
    if "target_status" in snapshot:
        if not isinstance(snapshot["target_status"], bool):
            _reject_snapshot()
        result["target_status"] = snapshot["target_status"]
    decision = _mapping(
        snapshot["target_decision"],
        allowed=frozenset(
            {
                "decision_schema_version",
                "scenario",
                "comparison",
                "unrounded_ending_balance",
                "unrounded_target_amount",
                "target_status",
            }
        ),
        required=frozenset(
            {
                "decision_schema_version",
                "scenario",
                "comparison",
                "unrounded_ending_balance",
                "unrounded_target_amount",
                "target_status",
            }
        ),
    )
    if (
        decision["decision_schema_version"] != TARGET_DECISION_SCHEMA_VERSION
        or decision["scenario"] != "base"
        or decision["comparison"] != "greater_than_or_equal"
        or not isinstance(decision["target_status"], bool)
    ):
        _reject_snapshot()
    unrounded_ending_balance = _decimal(decision["unrounded_ending_balance"])
    unrounded_target_amount = _decimal(decision["unrounded_target_amount"])
    expected_status = (
        Decimal(unrounded_ending_balance) >= Decimal(unrounded_target_amount)
    )
    if decision["target_status"] != expected_status or decision["target_status"] != result["target_status"]:
        _reject_snapshot()
    result["target_decision"] = {
        "decision_schema_version": TARGET_DECISION_SCHEMA_VERSION,
        "scenario": "base",
        "comparison": "greater_than_or_equal",
        "unrounded_ending_balance": unrounded_ending_balance,
        "unrounded_target_amount": unrounded_target_amount,
        "target_status": decision["target_status"],
    }
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
            required=frozenset(
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
                    {
                        "annual_return_rate",
                        "monthly_real_rate",
                        "ending_balance",
                        "investment_growth",
                        "target_gap",
                        "reaches_target",
                    }
                ),
            )
            result["scenarios"][scenario] = {
                key: (
                    (_calculation_decimal(item, nullable=key == "target_gap") if key == "monthly_real_rate" else _decimal(item, nullable=key == "target_gap"))
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
    if result["scenarios"]["base"]["reaches_target"] != result["target_status"]:
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
    input_hash_payload = {"assumptions": assumptions, "state": payload}
    input_snapshot_json = canonical_json(input_hash_payload)
    return ForecastSnapshots(
        input_snapshot_json=input_snapshot_json,
        assumption_snapshot_json=canonical_json(assumptions),
        output_snapshot_json=canonical_json(output),
        provenance_snapshot_json=canonical_json(
            {"provenance": payload["provenance"], "freshness": payload["freshness"]}
        ),
        input_state_hash=hashlib.sha256(input_snapshot_json.encode("utf-8")).hexdigest(),
    )
