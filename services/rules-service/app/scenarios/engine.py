"""Deterministic Scenario Lab transformation over the Phase 0 projection engine.

This module never replaces ``project_scenarios``. It invokes that authoritative
engine once per monthly boundary, carries the engine's unrounded ending balance
between boundaries, and rounds only the final result snapshots.
"""
from __future__ import annotations

import hashlib
import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Mapping

from app.calculations.projection import (
    CALCULATION_PRECISION,
    ProjectionRequest,
    project_scenarios,
)
from app.forecasts.canonical_state import canonical_decimal_string, canonical_json
from app.scenarios.contracts import (
    MAX_SCENARIO_HORIZON_MONTHS,
    ScenarioInput,
    SCENARIO_SCHEMA_VERSION,
    SCENARIO_MODEL_VERSION,
)

# Kept separate from the Phase 0 model identifier so Scenario Lab contract
# changes are distinguishable while calculation_version remains Phase 0-owned.
SCENARIO_CALCULATION_VERSION = "atlas-scenario-transform/v1"
MONEY_QUANTUM = Decimal("0.01")


class ScenarioCalculationError(ValueError):
    """Sanitized deterministic scenario calculation failure."""


@dataclass(frozen=True)
class ScenarioCalculation:
    """Complete server-derived scenario result and comparison snapshot."""

    scenario_input_hash: str
    input_snapshot: dict[str, Any]
    result_snapshot: dict[str, Any]
    comparison_snapshot: dict[str, Any]
    baseline_input_state_hash: str
    source_data_as_of: date
    data_age_days: int
    max_data_age_days: int


def _money(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + offset
    return absolute // 12, absolute % 12 + 1


def _projection_boundaries(request: ProjectionRequest) -> tuple[date, ...]:
    """Match Phase 0's month-end inclusion semantics exactly."""

    calculation_end = _month_end(request.calculation_date.year, request.calculation_date.month)
    first_offset = 0 if request.calculation_date < calculation_end else 1
    return tuple(
        _month_end(*_add_months(request.calculation_date.year, request.calculation_date.month, first_offset + index))
        for index in range(request.horizon_months)
    )


def _boundary_index(boundaries: tuple[date, ...], value: date | None) -> int | None:
    if value is None:
        return None
    for index, boundary in enumerate(boundaries):
        if boundary >= value:
            return index
    raise ScenarioCalculationError("scenario date is outside the projection horizon")


def _scenario_hash(*, baseline_forecast_id: str, baseline_version_number: int, baseline_input_state_hash: str, scenario_payload: Mapping[str, Any]) -> str:
    payload = {
        "baseline_forecast_id": baseline_forecast_id,
        "baseline_version_number": baseline_version_number,
        "baseline_input_state_hash": baseline_input_state_hash,
        "scenario": dict(scenario_payload),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_output_decimal(value: Decimal) -> str:
    return canonical_decimal_string(_money(value))


def _baseline_decimal(snapshot: Mapping[str, Any], *path: str) -> Decimal:
    value: Any = snapshot
    try:
        for part in path:
            value = value[part]
        return Decimal(str(value))
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise ScenarioCalculationError("baseline snapshot is incomplete") from exc


def _baseline_target(snapshot: Mapping[str, Any]) -> Decimal | None:
    raw = snapshot.get("drivers", {}).get("target_amount")
    return None if raw is None else Decimal(str(raw))


def _band_comparison(
    *,
    baseline_snapshot: Mapping[str, Any],
    scenario_bands: Mapping[str, Mapping[str, Any]],
    target_amount: Decimal | None,
) -> dict[str, Any]:
    bands: dict[str, Any] = {}
    for band in ("conservative", "base", "optimistic"):
        baseline_ending = _baseline_decimal(baseline_snapshot, "scenarios", band, "ending_balance")
        scenario_ending = Decimal(str(scenario_bands[band]["ending_balance"]))
        bands[band] = {
            "baseline_ending_net_worth": canonical_decimal_string(baseline_ending),
            "scenario_ending_net_worth": canonical_decimal_string(scenario_ending),
            "difference_from_baseline": canonical_decimal_string(_money(scenario_ending - baseline_ending)),
            "baseline_target_reached": bool(baseline_snapshot["scenarios"][band]["reaches_target"]),
            "scenario_target_reached": bool(scenario_bands[band]["reaches_target"]),
            "baseline_target_gap": canonical_decimal_string(Decimal(str(baseline_snapshot["scenarios"][band]["target_gap"]))) if baseline_snapshot["scenarios"][band].get("target_gap") is not None else None,
            "scenario_target_gap": scenario_bands[band]["target_gap"],
            "target_amount": canonical_decimal_string(target_amount) if target_amount is not None else None,
        }
    return bands


def calculate_scenario(
    *,
    request: ProjectionRequest,
    scenario_input: Any,
    baseline_forecast_id: str,
    baseline_version_number: int,
    baseline_input_state_hash: str,
    baseline_output_snapshot: Mapping[str, Any],
) -> ScenarioCalculation:
    """Calculate one bounded Scenario Lab result against one immutable baseline."""

    if not isinstance(scenario_input, ScenarioInput):
        raise ScenarioCalculationError("scenario input is invalid")
    if request.horizon_months < 1 or request.horizon_months > MAX_SCENARIO_HORIZON_MONTHS:
        raise ScenarioCalculationError("scenario horizon is outside the supported bound")

    boundaries = _projection_boundaries(request)
    start_index = _boundary_index(boundaries, scenario_input.contribution_start_date)
    stop_index = _boundary_index(boundaries, scenario_input.contribution_stop_date)
    outflow_index = _boundary_index(boundaries, scenario_input.one_time_outflow.date if scenario_input.one_time_outflow else None)
    if scenario_input.contribution_start_date is not None and scenario_input.contribution_start_date < request.calculation_date:
        raise ScenarioCalculationError("contribution start date is before the projection date")
    if scenario_input.contribution_stop_date is not None and scenario_input.contribution_stop_date < request.calculation_date:
        raise ScenarioCalculationError("contribution stop date is before the projection date")
    if scenario_input.one_time_outflow is not None and scenario_input.one_time_outflow.date < request.calculation_date:
        raise ScenarioCalculationError("outflow date is before the projection date")
    if start_index is not None and stop_index is not None and start_index > stop_index:
        raise ScenarioCalculationError("contribution start date is after stop date at the monthly boundary")

    delta = Decimal(scenario_input.monthly_contribution_delta or "0")
    adjusted_contribution = request.monthly_contribution + delta
    if adjusted_contribution < 0:
        raise ScenarioCalculationError("scenario contribution cannot be negative")
    outflow = Decimal(scenario_input.one_time_outflow.amount) if scenario_input.one_time_outflow else Decimal("0")
    scenario_payload = scenario_input.canonical_payload()
    scenario_hash = _scenario_hash(
        baseline_forecast_id=baseline_forecast_id,
        baseline_version_number=baseline_version_number,
        baseline_input_state_hash=baseline_input_state_hash,
        scenario_payload=scenario_payload,
    )

    band_results: dict[str, dict[str, Any]] = {}
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        for band in ("conservative", "base", "optimistic"):
            balance = request.current_balance
            total_contributions = Decimal("0")
            consumed = Decimal("0")
            for index, _boundary in enumerate(boundaries):
                contribution_active = True
                if start_index is not None and index < start_index:
                    contribution_active = False
                if stop_index is not None and index >= stop_index:
                    contribution_active = False
                # Dated start/stop bound the explicit contribution change;
                # outside that window the owned baseline contribution remains
                # in force. This avoids silently inventing a contribution
                # holiday when a user only dates a change.
                contribution = request.monthly_contribution + (delta if contribution_active else Decimal("0"))
                monthly_request = ProjectionRequest(
                    currency=request.currency,
                    current_balance=balance,
                    monthly_contribution=contribution,
                    horizon_months=1,
                    calculation_date=request.calculation_date,
                    data_as_of=request.data_as_of,
                    max_data_age_days=request.max_data_age_days,
                    contribution_timing=request.contribution_timing,
                    annual_inflation_rate=request.annual_inflation_rate,
                    annual_return_rates=request.annual_return_rates,
                )
                month_result = project_scenarios(monthly_request).scenarios[band]
                balance = month_result.unrounded_ending_balance
                total_contributions += contribution
                if outflow_index is not None and index == outflow_index:
                    if balance < outflow:
                        raise ScenarioCalculationError("one-time outflow exceeds available liquidity")
                    balance -= outflow
                    consumed = outflow
            ending = _money(balance)
            target = _money(request.target_amount) if request.target_amount is not None else None
            gap = max(Decimal("0"), target - ending) if target is not None else None
            band_results[band] = {
                "ending_balance": canonical_decimal_string(ending),
                "total_contributions": canonical_decimal_string(_money(total_contributions)),
                "contribution_difference": canonical_decimal_string(_money(total_contributions - (request.monthly_contribution * request.horizon_months))),
                "one_time_liquidity_consumed": canonical_decimal_string(_money(consumed)),
                "target_gap": canonical_decimal_string(gap) if gap is not None else None,
                "reaches_target": ending >= target if target is not None else None,
            }

    target = _baseline_target(baseline_output_snapshot)
    base = band_results["base"]
    baseline_base_ending = _baseline_decimal(baseline_output_snapshot, "scenarios", "base", "ending_balance")
    comparison = {
        "schema_version": "atlas-scenario-comparison/v1",
        "baseline_forecast_id": baseline_forecast_id,
        "baseline_version_number": baseline_version_number,
        "baseline_input_state_hash": baseline_input_state_hash,
        "currency": request.currency,
        "ending_net_worth": base["ending_balance"],
        "difference_from_baseline": canonical_decimal_string(_money(Decimal(base["ending_balance"]) - baseline_base_ending)),
        "target_amount": canonical_decimal_string(target) if target is not None else None,
        "target_gap": base["target_gap"],
        "target_reached": base["reaches_target"],
        "contribution_difference": base["contribution_difference"],
        "one_time_liquidity_consumed": base["one_time_liquidity_consumed"],
        "deterministic_bands": _band_comparison(
            baseline_snapshot=baseline_output_snapshot,
            scenario_bands=band_results,
            target_amount=target,
        ),
        "timing_impact": {
            "contribution_start_date": scenario_payload["contribution_start_date"],
            "contribution_stop_date": scenario_payload["contribution_stop_date"],
            "one_time_outflow_date": scenario_payload["one_time_outflow"]["date"] if scenario_payload["one_time_outflow"] else None,
            "one_time_outflow_boundary_index": outflow_index,
        },
        "assumptions": {
            "annual_return_rates": {name: canonical_decimal_string(value) for name, value in request.annual_return_rates.items()},
            "annual_inflation_rate": canonical_decimal_string(request.annual_inflation_rate),
            "contribution_timing": request.contribution_timing,
            "period": "monthly",
            "rounding_rule": "ROUND_HALF_EVEN",
            "probability": False,
        },
        "source_freshness": {
            "data_as_of": request.data_as_of.isoformat(),
            "data_age_days": (request.calculation_date - request.data_as_of).days,
            "max_data_age_days": request.max_data_age_days,
        },
        "warnings": [
            "Deterministic scenario bands are not probabilities or guarantees.",
            "No financing, debt, taxes, appreciation, resale value, or execution is inferred.",
        ],
        "limitations": [
            "USD-only, one owned goal, monthly end-of-month boundaries, one outflow.",
        ],
    }
    result_snapshot = {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "model_version": SCENARIO_MODEL_VERSION,
        "calculation_version": SCENARIO_CALCULATION_VERSION,
        "currency": request.currency,
        "scenario_input_hash": scenario_hash,
        "canonical_inputs": scenario_payload,
        "deterministic_bands": band_results,
        "source_freshness": comparison["source_freshness"],
        "assumptions": comparison["assumptions"],
    }
    input_snapshot = {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "baseline_forecast_id": baseline_forecast_id,
        "baseline_version_number": baseline_version_number,
        "baseline_input_state_hash": baseline_input_state_hash,
        "scenario": scenario_payload,
    }
    return ScenarioCalculation(
        scenario_input_hash=scenario_hash,
        input_snapshot=input_snapshot,
        result_snapshot=result_snapshot,
        comparison_snapshot=comparison,
        baseline_input_state_hash=baseline_input_state_hash,
        source_data_as_of=request.data_as_of,
        data_age_days=(request.calculation_date - request.data_as_of).days,
        max_data_age_days=request.max_data_age_days,
    )
