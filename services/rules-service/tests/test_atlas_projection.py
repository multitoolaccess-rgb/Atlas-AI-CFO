"""Golden-contract tests for the pure Atlas projection calculation."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from app.calculations.projection import (
    ProjectionRequest,
    ProjectionValidationError,
    project_scenarios,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "atlas_projection_cases.json"
)


@pytest.fixture(scope="module")
def golden_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_contract_covers_required_phase_zero_cases(
    golden_fixture: dict[str, Any],
) -> None:
    assert golden_fixture["schema_version"] == "atlas-projection-fixtures/v1"
    assert golden_fixture["money"] == {
        "currency": "USD",
        "precision": "0.01",
        "rounding": "ROUND_HALF_EVEN",
    }

    tags = {
        tag
        for case in golden_fixture["cases"]
        for tag in case["tags"]
    }
    assert {
        "zero-current-balance",
        "zero-monthly-contribution",
        "positive-monthly-contribution",
        "negative-monthly-cash-flow",
        "zero-return",
        "scenario-returns",
        "one-month-horizon",
        "target-date-derived-horizon",
        "multi-year-horizon",
        "invalid-target-date",
        "conflicting-target-date-and-horizon",
        "unsupported-currency",
        "missing-currency",
        "currency-rounding-boundary",
        "very-large-target-value",
        "missing-financial-input",
        "missing-data-freshness",
        "stale-financial-input",
    }.issubset(tags)


def test_valid_golden_cases_match_authoritative_decimal_results(
    golden_fixture: dict[str, Any],
) -> None:
    valid_cases = [
        case for case in golden_fixture["cases"] if "valid" in case["tags"]
    ]

    for case in valid_cases:
        request = ProjectionRequest.from_mapping(case["input"])
        result = project_scenarios(request)

        assert result.currency == "USD", case["id"]
        assert result.model_version == golden_fixture["model_version"], case["id"]
        assert result.assumptions.contribution_timing == "end_of_month", case["id"]
        expected_horizon = case["expected"].get(
            "horizon_months",
            case["input"].get("horizon_months"),
        )
        assert result.drivers.horizon_months == expected_horizon, case["id"]
        assert isinstance(result.drivers.current_balance, Decimal), case["id"]

        expected = case["expected"]["scenario_ending_balances"]
        actual = {
            name: format(scenario.ending_balance, ".2f")
            for name, scenario in result.scenarios.items()
        }
        assert actual == expected, case["id"]


def test_invalid_golden_cases_return_stable_validation_codes(
    golden_fixture: dict[str, Any],
) -> None:
    invalid_cases = [
        case for case in golden_fixture["cases"] if "invalid" in case["tags"]
    ]

    for case in invalid_cases:
        with pytest.raises(ProjectionValidationError) as exc_info:
            ProjectionRequest.from_mapping(case["input"])

        assert exc_info.value.code == case["expected_error"], case["id"]


def test_scenario_results_are_ordered_without_probability_claims(
    golden_fixture: dict[str, Any],
) -> None:
    case = next(
        case
        for case in golden_fixture["cases"]
        if case["id"] == "positive-monthly-contribution"
    )
    result = project_scenarios(ProjectionRequest.from_mapping(case["input"]))

    assert list(result.scenarios) == ["conservative", "base", "optimistic"]
    assert (
        result.scenarios["conservative"].ending_balance
        < result.scenarios["base"].ending_balance
        < result.scenarios["optimistic"].ending_balance
    )
    assert not hasattr(result, "probability")
    assert all(
        not hasattr(scenario, "probability")
        for scenario in result.scenarios.values()
    )


def test_projection_is_independent_of_ambient_decimal_context(
    golden_fixture: dict[str, Any],
) -> None:
    case = next(
        case
        for case in golden_fixture["cases"]
        if case["id"] == "very-large-target-value"
    )
    request = ProjectionRequest.from_mapping(case["input"])

    with localcontext() as context:
        context.prec = 10
        result = project_scenarios(request)

    assert format(result.scenarios["base"].ending_balance, ".2f") == (
        case["expected"]["scenario_ending_balances"]["base"]
    )


@pytest.mark.parametrize(
    ("patch", "expected_code"),
    [
        ({"horizon_months": 2401}, "invalid_horizon"),
        ({"current_balance": "1e25"}, "financial_input_out_of_range"),
        (
            {
                "annual_return_rates": {
                    "conservative": "0.02",
                    "base": "0.05",
                    "optimistic": "2.01",
                }
            },
            "invalid_assumption",
        ),
    ],
)
def test_business_bounds_return_stable_validation_errors(
    golden_fixture: dict[str, Any],
    patch: dict[str, Any],
    expected_code: str,
) -> None:
    case = next(
        case
        for case in golden_fixture["cases"]
        if case["id"] == "positive-monthly-contribution"
    )
    values = {**case["input"], **patch}

    with pytest.raises(ProjectionValidationError) as exc_info:
        ProjectionRequest.from_mapping(values)

    assert exc_info.value.code == expected_code


def test_request_and_result_scenario_mappings_are_immutable(
    golden_fixture: dict[str, Any],
) -> None:
    case = next(
        case
        for case in golden_fixture["cases"]
        if case["id"] == "positive-monthly-contribution"
    )
    request = ProjectionRequest.from_mapping(case["input"])
    result = project_scenarios(request)

    assert isinstance(request.annual_return_rates, MappingProxyType)
    assert isinstance(result.assumptions.annual_return_rates, MappingProxyType)
    assert isinstance(result.scenarios, MappingProxyType)
    with pytest.raises(TypeError):
        request.annual_return_rates["base"] = Decimal("0.99")  # type: ignore[index]
    with pytest.raises(TypeError):
        result.scenarios["base"] = result.scenarios["conservative"]  # type: ignore[index]


def test_direct_request_construction_still_enforces_invariants(
    golden_fixture: dict[str, Any],
) -> None:
    case = next(
        case
        for case in golden_fixture["cases"]
        if case["id"] == "positive-monthly-contribution"
    )
    request = ProjectionRequest.from_mapping(case["input"])

    with pytest.raises(ProjectionValidationError) as exc_info:
        replace(request, currency="EUR")

    assert exc_info.value.code == "unsupported_currency"


def test_target_status_uses_the_same_currency_rounding_boundary(
    golden_fixture: dict[str, Any],
) -> None:
    case = next(
        case
        for case in golden_fixture["cases"]
        if case["id"] == "rounding-half-even-up"
    )
    request = ProjectionRequest.from_mapping(
        {**case["input"], "target_amount": "0.02"}
    )
    result = project_scenarios(request)
    base = result.scenarios["base"]

    assert base.ending_balance == Decimal("0.02")
    assert base.target_gap == Decimal("0.00")
    assert base.reaches_target is True


def test_inflation_and_driver_outputs_are_structured_and_consistent(
    golden_fixture: dict[str, Any],
) -> None:
    case = next(
        case
        for case in golden_fixture["cases"]
        if case["id"] == "positive-monthly-contribution"
    )
    request = ProjectionRequest.from_mapping(
        {**case["input"], "annual_inflation_rate": "0.02"}
    )
    result = project_scenarios(request)

    assert result.assumptions.annual_inflation_rate == Decimal("0.02")
    assert result.assumptions.period == "monthly"
    assert result.drivers.total_contributions == Decimal("6000.00")
    assert result.drivers.data_age_days == 1
    assert (
        result.scenarios["base"].investment_growth
        == result.scenarios["base"].ending_balance
        - result.drivers.current_balance
        - result.drivers.total_contributions
    )


def test_maximum_date_returns_a_stable_horizon_error() -> None:
    values = {
        "currency": "USD",
        "current_balance": "1000",
        "monthly_contribution": "100",
        "target_date": "9999-12-31",
        "calculation_date": "2026-07-26",
        "data_as_of": "2026-07-25",
        "max_data_age_days": 30,
        "contribution_timing": "end_of_month",
        "annual_inflation_rate": "0",
        "annual_return_rates": {
            "conservative": "0.02",
            "base": "0.05",
            "optimistic": "0.08",
        },
    }

    with pytest.raises(ProjectionValidationError) as exc_info:
        ProjectionRequest.from_mapping(values)

    assert exc_info.value.code == "invalid_horizon"
