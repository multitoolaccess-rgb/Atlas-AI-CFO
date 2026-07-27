"""Authoritative deterministic Atlas goal-projection mathematics.

The calculation uses monthly periods with end-of-month contributions:

    monthly_real_rate = (((1 + annual_return) / (1 + inflation)) - 1) / 12
    FV = PV * (1 + monthly_real_rate) ** months
       + PMT * (((1 + monthly_real_rate) ** months - 1) / monthly_real_rate)

When the monthly rate is zero, ``FV = PV + PMT * months``.

All arithmetic is Decimal. Intermediate values remain unrounded; monetary
outputs are quantized to USD cents with ROUND_HALF_EVEN at the result boundary.
Scenario bands are deterministic assumptions, not probability estimates.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_EVEN,
    localcontext,
)
from types import MappingProxyType
from typing import Any, Mapping


MODEL_VERSION = "atlas-monthly-scenarios/v1"
SUPPORTED_CURRENCY = "USD"
MONEY_QUANTUM = Decimal("0.01")
SCENARIO_NAMES = ("conservative", "base", "optimistic")
CONTRIBUTION_TIMING = "end_of_month"
CALCULATION_PRECISION = 50
MAX_HORIZON_MONTHS = 2_400
MAX_ABSOLUTE_MONEY = Decimal("1E+24")
MAX_ANNUAL_RATE = Decimal("2")
MAX_ANNUAL_INFLATION = Decimal("1")


class ProjectionValidationError(ValueError):
    """Input validation error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _required_decimal(
    values: Mapping[str, Any],
    field: str,
    *,
    missing_code: str,
) -> Decimal:
    if field not in values or values[field] is None:
        raise ProjectionValidationError(
            missing_code,
            f"{field} is required.",
        )
    try:
        value = Decimal(str(values[field]))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProjectionValidationError(
            "invalid_financial_input",
            f"{field} must be a finite decimal value.",
        ) from exc
    if not value.is_finite():
        raise ProjectionValidationError(
            "invalid_financial_input",
            f"{field} must be a finite decimal value.",
        )
    return value


def _optional_decimal(
    values: Mapping[str, Any],
    field: str,
) -> Decimal | None:
    if field not in values or values[field] is None:
        return None
    return _required_decimal(
        values,
        field,
        missing_code="invalid_financial_input",
    )


def _required_date(
    values: Mapping[str, Any],
    field: str,
    *,
    missing_code: str,
    invalid_code: str,
) -> date:
    raw = values.get(field)
    if raw is None or raw == "":
        raise ProjectionValidationError(missing_code, f"{field} is required.")
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError) as exc:
        raise ProjectionValidationError(
            invalid_code,
            f"{field} must be a valid ISO date.",
        ) from exc


def _month_ends_through(calculation_date: date, target_date: date) -> int:
    """Count month ends after calculation_date and on/before target_date."""

    if target_date <= calculation_date:
        raise ProjectionValidationError(
            "invalid_target_date",
            "target_date must be after calculation_date.",
        )

    calculation_month_end = date(
        calculation_date.year,
        calculation_date.month,
        calendar.monthrange(calculation_date.year, calculation_date.month)[1],
    )
    target_month_end = date(
        target_date.year,
        target_date.month,
        calendar.monthrange(target_date.year, target_date.month)[1],
    )
    months_between = (
        (target_date.year - calculation_date.year) * 12
        + target_date.month
        - calculation_date.month
    )
    first_eligible_month = 0 if calculation_date < calculation_month_end else 1
    last_eligible_month = (
        months_between
        if target_date == target_month_end
        else months_between - 1
    )
    periods = last_eligible_month - first_eligible_month + 1

    if periods < 1:
        raise ProjectionValidationError(
            "invalid_target_date",
            "target_date must include at least one future month end.",
        )
    if periods > MAX_HORIZON_MONTHS:
        raise ProjectionValidationError(
            "invalid_horizon",
            f"horizon_months must not exceed {MAX_HORIZON_MONTHS}.",
        )
    return periods


def _validate_money_input(name: str, value: Decimal | None) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ProjectionValidationError(
            "invalid_financial_input",
            f"{name} must be a finite Decimal value.",
        )
    if abs(value) > MAX_ABSOLUTE_MONEY:
        raise ProjectionValidationError(
            "financial_input_out_of_range",
            f"{name} must not exceed {MAX_ABSOLUTE_MONEY} in absolute value.",
        )


@dataclass(frozen=True)
class ProjectionRequest:
    """Normalized, validated inputs for an Atlas scenario projection."""

    currency: str
    current_balance: Decimal
    monthly_contribution: Decimal
    horizon_months: int
    calculation_date: date
    data_as_of: date
    max_data_age_days: int
    contribution_timing: str
    annual_inflation_rate: Decimal
    annual_return_rates: Mapping[str, Decimal]
    target_amount: Decimal | None = None
    target_date: date | None = None

    def __post_init__(self) -> None:
        """Enforce invariants for direct construction and freeze mappings."""

        if self.currency != SUPPORTED_CURRENCY:
            raise ProjectionValidationError(
                "unsupported_currency",
                f"Only {SUPPORTED_CURRENCY} is supported in this release.",
            )
        _validate_money_input("current_balance", self.current_balance)
        _validate_money_input("monthly_contribution", self.monthly_contribution)
        _validate_money_input("target_amount", self.target_amount)

        if (
            isinstance(self.horizon_months, bool)
            or not isinstance(self.horizon_months, int)
            or not 1 <= self.horizon_months <= MAX_HORIZON_MONTHS
        ):
            raise ProjectionValidationError(
                "invalid_horizon",
                (
                    "horizon_months must be a positive integer no greater than "
                    f"{MAX_HORIZON_MONTHS}."
                ),
            )
        if self.contribution_timing != CONTRIBUTION_TIMING:
            raise ProjectionValidationError(
                "unsupported_contribution_timing",
                "Only end_of_month contributions are supported in Phase 0.",
            )
        if not isinstance(self.calculation_date, date) or not isinstance(
            self.data_as_of,
            date,
        ):
            raise ProjectionValidationError(
                "invalid_data_freshness",
                "calculation_date and data_as_of must be dates.",
            )
        if (
            isinstance(self.max_data_age_days, bool)
            or not isinstance(self.max_data_age_days, int)
            or self.max_data_age_days < 0
        ):
            raise ProjectionValidationError(
                "invalid_data_freshness",
                "max_data_age_days must be a non-negative integer.",
            )
        data_age_days = (self.calculation_date - self.data_as_of).days
        if data_age_days < 0:
            raise ProjectionValidationError(
                "invalid_data_freshness",
                "data_as_of cannot be after calculation_date.",
            )
        if data_age_days > self.max_data_age_days:
            raise ProjectionValidationError(
                "stale_financial_input",
                (
                    f"Financial inputs are {data_age_days} days old; "
                    f"the maximum is {self.max_data_age_days}."
                ),
            )
        if (
            not isinstance(self.annual_inflation_rate, Decimal)
            or not self.annual_inflation_rate.is_finite()
            or not (
                Decimal("-1")
                < self.annual_inflation_rate
                <= MAX_ANNUAL_INFLATION
            )
        ):
            raise ProjectionValidationError(
                "invalid_assumption",
                (
                    "annual_inflation_rate must be finite and in "
                    f"(-1, {MAX_ANNUAL_INFLATION}]."
                ),
            )
        if set(self.annual_return_rates) != set(SCENARIO_NAMES):
            raise ProjectionValidationError(
                "missing_assumption",
                "annual_return_rates must define conservative, base, and optimistic.",
            )
        rates = {name: self.annual_return_rates[name] for name in SCENARIO_NAMES}
        if any(
            not isinstance(rate, Decimal)
            or not rate.is_finite()
            or rate <= Decimal("-1")
            or rate > MAX_ANNUAL_RATE
            for rate in rates.values()
        ):
            raise ProjectionValidationError(
                "invalid_assumption",
                (
                    "Annual return rates must be finite and in "
                    f"(-1, {MAX_ANNUAL_RATE}]."
                ),
            )
        if list(rates.values()) != sorted(rates.values()):
            raise ProjectionValidationError(
                "invalid_scenario_rates",
                "Scenario returns must be conservative <= base <= optimistic.",
            )
        if self.target_date is not None:
            if not isinstance(self.target_date, date):
                raise ProjectionValidationError(
                    "invalid_target_date",
                    "target_date must be a date.",
                )
            derived_horizon = _month_ends_through(
                self.calculation_date,
                self.target_date,
            )
            if derived_horizon != self.horizon_months:
                raise ProjectionValidationError(
                    "conflicting_horizon",
                    "target_date and horizon_months describe different month-end periods.",
                )
        object.__setattr__(
            self,
            "annual_return_rates",
            MappingProxyType(rates),
        )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "ProjectionRequest":
        currency = values.get("currency")
        if currency is None or str(currency).strip() == "":
            raise ProjectionValidationError(
                "missing_currency",
                "currency is required.",
            )
        normalized_currency = str(currency).upper()
        if normalized_currency != SUPPORTED_CURRENCY:
            raise ProjectionValidationError(
                "unsupported_currency",
                f"Only {SUPPORTED_CURRENCY} is supported in this release.",
            )

        current_balance = _required_decimal(
            values,
            "current_balance",
            missing_code="missing_financial_input",
        )
        monthly_contribution = _required_decimal(
            values,
            "monthly_contribution",
            missing_code="missing_financial_input",
        )
        target_amount = _optional_decimal(values, "target_amount")

        calculation_date = _required_date(
            values,
            "calculation_date",
            missing_code="missing_data_freshness",
            invalid_code="invalid_data_freshness",
        )
        data_as_of = _required_date(
            values,
            "data_as_of",
            missing_code="missing_data_freshness",
            invalid_code="invalid_data_freshness",
        )

        raw_max_age = values.get("max_data_age_days")
        if raw_max_age is None:
            raise ProjectionValidationError(
                "missing_data_freshness",
                "max_data_age_days is required.",
            )
        if isinstance(raw_max_age, bool):
            raise ProjectionValidationError(
                "invalid_data_freshness",
                "max_data_age_days must be a non-negative integer.",
            )
        try:
            max_data_age_days = int(raw_max_age)
        except (TypeError, ValueError) as exc:
            raise ProjectionValidationError(
                "invalid_data_freshness",
                "max_data_age_days must be a non-negative integer.",
            ) from exc
        if max_data_age_days < 0 or str(max_data_age_days) != str(raw_max_age):
            raise ProjectionValidationError(
                "invalid_data_freshness",
                "max_data_age_days must be a non-negative integer.",
            )

        data_age_days = (calculation_date - data_as_of).days
        if data_age_days < 0:
            raise ProjectionValidationError(
                "invalid_data_freshness",
                "data_as_of cannot be after calculation_date.",
            )
        if data_age_days > max_data_age_days:
            raise ProjectionValidationError(
                "stale_financial_input",
                (
                    f"Financial inputs are {data_age_days} days old; "
                    f"the maximum is {max_data_age_days}."
                ),
            )

        target_date: date | None = None
        if values.get("target_date") not in (None, ""):
            target_date = _required_date(
                values,
                "target_date",
                missing_code="invalid_target_date",
                invalid_code="invalid_target_date",
            )

        raw_horizon = values.get("horizon_months")
        if raw_horizon is None:
            if target_date is None:
                raise ProjectionValidationError(
                    "invalid_horizon",
                    "horizon_months or target_date is required.",
                )
            horizon_months = _month_ends_through(
                calculation_date,
                target_date,
            )
        else:
            if isinstance(raw_horizon, bool):
                raise ProjectionValidationError(
                    "invalid_horizon",
                    "horizon_months must be a positive integer.",
                )
            try:
                horizon_months = int(raw_horizon)
            except (TypeError, ValueError) as exc:
                raise ProjectionValidationError(
                    "invalid_horizon",
                    "horizon_months must be a positive integer.",
                ) from exc
            if (
                horizon_months < 1
                or horizon_months > MAX_HORIZON_MONTHS
                or str(horizon_months) != str(raw_horizon)
            ):
                raise ProjectionValidationError(
                    "invalid_horizon",
                    "horizon_months must be a positive integer.",
                )

        contribution_timing = str(
            values.get("contribution_timing", CONTRIBUTION_TIMING)
        )
        if contribution_timing != CONTRIBUTION_TIMING:
            raise ProjectionValidationError(
                "unsupported_contribution_timing",
                "Only end_of_month contributions are supported in Phase 0.",
            )

        annual_inflation_rate = _required_decimal(
            values,
            "annual_inflation_rate",
            missing_code="missing_assumption",
        )
        if not Decimal("-1") < annual_inflation_rate <= MAX_ANNUAL_INFLATION:
            raise ProjectionValidationError(
                "invalid_assumption",
                "annual_inflation_rate must be greater than -1.",
            )

        raw_rates = values.get("annual_return_rates")
        if not isinstance(raw_rates, Mapping):
            raise ProjectionValidationError(
                "missing_assumption",
                "annual_return_rates is required.",
            )
        annual_return_rates = {
            name: _required_decimal(
                raw_rates,
                name,
                missing_code="missing_assumption",
            )
            for name in SCENARIO_NAMES
        }
        if any(
            rate <= Decimal("-1") or rate > MAX_ANNUAL_RATE
            for rate in annual_return_rates.values()
        ):
            raise ProjectionValidationError(
                "invalid_assumption",
                "Annual return rates must be greater than -1.",
            )
        if list(annual_return_rates.values()) != sorted(
            annual_return_rates.values()
        ):
            raise ProjectionValidationError(
                "invalid_scenario_rates",
                "Scenario returns must be conservative <= base <= optimistic.",
            )

        return cls(
            currency=normalized_currency,
            current_balance=current_balance,
            monthly_contribution=monthly_contribution,
            target_amount=target_amount,
            horizon_months=horizon_months,
            target_date=target_date,
            calculation_date=calculation_date,
            data_as_of=data_as_of,
            max_data_age_days=max_data_age_days,
            contribution_timing=contribution_timing,
            annual_inflation_rate=annual_inflation_rate,
            annual_return_rates=annual_return_rates,
        )


@dataclass(frozen=True)
class ProjectionAssumptions:
    annual_return_rates: Mapping[str, Decimal]
    annual_inflation_rate: Decimal
    contribution_timing: str
    period: str
    rounding_rule: str
    money_precision: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "annual_return_rates",
            MappingProxyType(dict(self.annual_return_rates)),
        )


@dataclass(frozen=True)
class ProjectionDrivers:
    current_balance: Decimal
    monthly_contribution: Decimal
    total_contributions: Decimal
    target_amount: Decimal | None
    horizon_months: int
    data_as_of: date
    data_age_days: int


@dataclass(frozen=True)
class ScenarioProjection:
    annual_return_rate: Decimal
    monthly_real_rate: Decimal
    ending_balance: Decimal
    investment_growth: Decimal
    target_gap: Decimal | None
    reaches_target: bool | None


@dataclass(frozen=True)
class ProjectionResult:
    currency: str
    model_version: str
    calculated_at: date
    assumptions: ProjectionAssumptions
    drivers: ProjectionDrivers
    scenarios: Mapping[str, ScenarioProjection]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scenarios",
            MappingProxyType(dict(self.scenarios)),
        )


def _money(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _project_scenario(
    request: ProjectionRequest,
    annual_return_rate: Decimal,
) -> ScenarioProjection:
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        real_annual_rate = (
            (Decimal(1) + annual_return_rate)
            / (Decimal(1) + request.annual_inflation_rate)
        ) - Decimal(1)
        monthly_real_rate = real_annual_rate / Decimal(12)

        if monthly_real_rate == 0:
            unrounded_ending_balance = (
                request.current_balance
                + request.monthly_contribution * request.horizon_months
            )
        else:
            growth_factor = (
                Decimal(1) + monthly_real_rate
            ) ** request.horizon_months
            unrounded_ending_balance = (
                request.current_balance * growth_factor
                + request.monthly_contribution
                * ((growth_factor - Decimal(1)) / monthly_real_rate)
            )

        unrounded_total_contributions = (
            request.monthly_contribution * request.horizon_months
        )
        rounded_ending_balance = _money(unrounded_ending_balance)
        rounded_current_balance = _money(request.current_balance)
        rounded_total_contributions = _money(unrounded_total_contributions)
        rounded_target_amount = (
            _money(request.target_amount)
            if request.target_amount is not None
            else None
        )

        return ScenarioProjection(
            annual_return_rate=annual_return_rate,
            monthly_real_rate=monthly_real_rate,
            ending_balance=rounded_ending_balance,
            investment_growth=(
                rounded_ending_balance
                - rounded_current_balance
                - rounded_total_contributions
            ),
            target_gap=(
                max(Decimal(0), rounded_target_amount - rounded_ending_balance)
                if rounded_target_amount is not None
                else None
            ),
            reaches_target=(
                rounded_ending_balance >= rounded_target_amount
                if rounded_target_amount is not None
                else None
            ),
        )


def project_scenarios(request: ProjectionRequest) -> ProjectionResult:
    """Project deterministic conservative, base, and optimistic scenarios."""

    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        scenarios = {
            name: _project_scenario(request, request.annual_return_rates[name])
            for name in SCENARIO_NAMES
        }
        unrounded_total_contributions = (
            request.monthly_contribution * request.horizon_months
        )

        return ProjectionResult(
            currency=request.currency,
            model_version=MODEL_VERSION,
            calculated_at=request.calculation_date,
            assumptions=ProjectionAssumptions(
                annual_return_rates=request.annual_return_rates,
                annual_inflation_rate=request.annual_inflation_rate,
                contribution_timing=request.contribution_timing,
                period="monthly",
                rounding_rule="ROUND_HALF_EVEN",
                money_precision=MONEY_QUANTUM,
            ),
            drivers=ProjectionDrivers(
                current_balance=_money(request.current_balance),
                monthly_contribution=_money(request.monthly_contribution),
                total_contributions=_money(unrounded_total_contributions),
                target_amount=(
                    _money(request.target_amount)
                    if request.target_amount is not None
                    else None
                ),
                horizon_months=request.horizon_months,
                data_as_of=request.data_as_of,
                data_age_days=(request.calculation_date - request.data_as_of).days,
            ),
            scenarios=scenarios,
        )
