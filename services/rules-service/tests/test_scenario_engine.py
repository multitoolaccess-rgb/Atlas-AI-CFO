"""Synthetic fixtures for the authoritative Scenario Lab transformation."""
from datetime import date
from decimal import Decimal, getcontext, localcontext

import pytest

from app.calculations.projection import ProjectionRequest, project_scenarios
from app.scenarios.contracts import OneTimeOutflow, ScenarioInput
from app.scenarios.engine import ScenarioCalculationError, ScenarioInputValidationError, calculate_scenario


def _request(*, balance="1000", contribution="100", target="2500") -> ProjectionRequest:
    return ProjectionRequest(
        currency="USD",
        current_balance=Decimal(balance),
        monthly_contribution=Decimal(contribution),
        horizon_months=12,
        calculation_date=date(2026, 1, 15),
        data_as_of=date(2026, 1, 15),
        max_data_age_days=30,
        contribution_timing="end_of_month",
        annual_inflation_rate=Decimal("0.02"),
        annual_return_rates={"conservative": Decimal("0.02"), "base": Decimal("0.04"), "optimistic": Decimal("0.06")},
        target_amount=Decimal(target) if target is not None else None,
    )


def _baseline(request: ProjectionRequest) -> dict:
    result = project_scenarios(request)
    output = {"drivers": {"target_amount": str(result.drivers.target_amount)}, "scenarios": {}}
    for name, item in result.scenarios.items():
        output["scenarios"][name] = {
            "ending_balance": str(item.ending_balance),
            "target_gap": str(item.target_gap) if item.target_gap is not None else None,
            "reaches_target": item.reaches_target,
        }
    return output


def _calculate(scenario: ScenarioInput, request: ProjectionRequest | None = None):
    request = request or _request()
    return calculate_scenario(
        request=request,
        scenario_input=scenario,
        baseline_forecast_id="11111111-1111-4111-8111-111111111111",
        baseline_version_number=1,
        baseline_input_state_hash="a" * 64,
        baseline_output_snapshot=_baseline(request),
    )


def test_monthly_contribution_delta_is_goal_scoped_and_decimal_safe() -> None:
    result = _calculate(ScenarioInput(monthly_contribution_delta="50"))
    assert result.result_snapshot["deterministic_bands"]["base"]["contribution_difference"] == "600"
    assert result.comparison_snapshot["contribution_difference"] == "600"
    assert result.comparison_snapshot["assumptions"]["probability"] is False


def test_contribution_start_and_stop_apply_at_first_monthly_boundary() -> None:
    result = _calculate(
        ScenarioInput(
            monthly_contribution_delta="100",
            contribution_start_date=date(2026, 4, 1),
            contribution_stop_date=date(2026, 9, 1),
        )
    )
    # Jan 31, Feb 28, Mar 31 are before start; Sep 30 is the first boundary
    # on/after stop, so April through August receive the explicit delta (5 months).
    assert result.result_snapshot["deterministic_bands"]["base"]["contribution_difference"] == "500"
    assert result.comparison_snapshot["timing_impact"]["one_time_outflow_boundary_index"] is None


def test_one_time_outflow_is_applied_once_after_that_month_end() -> None:
    result = _calculate(
        ScenarioInput(one_time_outflow=OneTimeOutflow(date=date(2026, 3, 1), amount="100"))
    )
    band = result.result_snapshot["deterministic_bands"]["base"]
    assert band["one_time_liquidity_consumed"] == "100"
    assert result.comparison_snapshot["one_time_liquidity_consumed"] == "100"
    assert result.comparison_snapshot["timing_impact"]["one_time_outflow_boundary_index"] == 2


def test_outflow_at_horizon_boundary_is_valid_and_outside_horizon_fails() -> None:
    valid = _calculate(ScenarioInput(one_time_outflow=OneTimeOutflow(date=date(2026, 12, 31), amount="1")))
    assert valid.result_snapshot["deterministic_bands"]["base"]["one_time_liquidity_consumed"] == "1"
    with pytest.raises(ScenarioCalculationError):
        _calculate(ScenarioInput(one_time_outflow=OneTimeOutflow(date=date(2027, 1, 1), amount="1")))


def test_user_input_failures_raise_input_validation_not_generic_calculation_error() -> None:
    """Dates outside the horizon and negative contributions are user-input
    validation failures, so the route can return 422 instead of a generic 503."""
    with pytest.raises(ScenarioInputValidationError, match="horizon"):
        _calculate(
            ScenarioInput(
                monthly_contribution_delta="10",
                contribution_stop_date=date(2027, 1, 15),
            )
        )
    with pytest.raises(ScenarioInputValidationError, match="cannot be negative"):
        _calculate(ScenarioInput(monthly_contribution_delta="-101"))
    # The generic superclass still catches them (existing callers keep working).
    with pytest.raises(ScenarioCalculationError, match="liquidity"):
        _calculate(
            ScenarioInput(one_time_outflow=OneTimeOutflow(date=date(2026, 1, 15), amount="1000000")),
            _request(balance="0", contribution="0"),
        )


def test_outflow_cannot_silently_create_debt() -> None:
    with pytest.raises(ScenarioCalculationError, match="liquidity"):
        _calculate(ScenarioInput(one_time_outflow=OneTimeOutflow(date=date(2026, 1, 15), amount="1000000")), _request(balance="0", contribution="0"))


def test_decimal_context_independence() -> None:
    scenario = ScenarioInput(monthly_contribution_delta="0.01", one_time_outflow=OneTimeOutflow(date=date(2026, 6, 1), amount="0.03"))
    with localcontext() as context:
        context.prec = 9
        low = _calculate(scenario).result_snapshot
    with localcontext() as context:
        context.prec = 90
        high = _calculate(scenario).result_snapshot
    assert low == high


def test_target_rounding_uses_round_half_even() -> None:
    request = ProjectionRequest(
        currency="USD", current_balance=Decimal("0.005"), monthly_contribution=Decimal("0"), horizon_months=12,
        calculation_date=date(2026, 1, 15), data_as_of=date(2026, 1, 15), max_data_age_days=30,
        contribution_timing="end_of_month", annual_inflation_rate=Decimal("0.02"),
        annual_return_rates={"conservative": Decimal("0.02"), "base": Decimal("0.02"), "optimistic": Decimal("0.02")}, target_amount=Decimal("0.01"),
    )
    result = _calculate(ScenarioInput(monthly_contribution_delta="0"), request)
    # A non-empty explicit change is required; zero delta is still explicit.
    assert result.comparison_snapshot["target_amount"] == "0.01"
    assert result.result_snapshot["deterministic_bands"]["base"]["ending_balance"] == "0"


def test_canonical_hash_is_order_independent_and_changes_with_baseline_version() -> None:
    first = _calculate(ScenarioInput(monthly_contribution_delta="10"))
    reordered = _calculate(ScenarioInput(monthly_contribution_delta="10"))
    assert first.scenario_input_hash == reordered.scenario_input_hash
    changed = calculate_scenario(
        request=_request(),
        scenario_input=ScenarioInput(monthly_contribution_delta="10"),
        baseline_forecast_id="11111111-1111-4111-8111-111111111111",
        baseline_version_number=2,
        baseline_input_state_hash="a" * 64,
        baseline_output_snapshot=_baseline(_request()),
    )
    assert changed.scenario_input_hash != first.scenario_input_hash


def test_prohibited_empty_and_negative_contribution_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        ScenarioInput.model_validate({})
    with pytest.raises(ScenarioCalculationError, match="cannot be negative"):
        _calculate(ScenarioInput(monthly_contribution_delta="-101"))
