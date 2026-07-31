"""Trusted, route-free Phase 1 forecast generation application service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculations.projection import (
    MODEL_VERSION,
    ProjectionRequest,
    ProjectionValidationError,
    project_scenarios,
)
from app.forecasts.canonical_state import (
    CanonicalProjectionState,
    CanonicalStateValidationError,
    FinlynqProjectionStateAdapter,
    canonical_decimal_string,
    load_authoritative_projection_state,
)
from app.forecasts.repository import ForecastRepository, PersistedForecastVersion
from app.forecasts.snapshots import ASSUMPTION_SCHEMA_VERSION, TARGET_DECISION_SCHEMA_VERSION, CALCULATION_DECIMAL_SCHEMA_VERSION, calculation_decimal_string
from app.models import Goal
from app.config import settings


class ForecastGenerationUnavailable(RuntimeError):
    """Safe internal failure; callers must not expose source financial state."""


@dataclass(frozen=True)
class GeneratedForecast:
    persisted: PersistedForecastVersion


_RATES = {"conservative": Decimal("0.02"), "base": Decimal("0.04"), "optimistic": Decimal("0.06")}


class ForecastGenerationService:
    """Authorize, load one trusted state, calculate unchanged Phase 0 math, persist."""

    def __init__(self, session: Session, adapter: FinlynqProjectionStateAdapter) -> None:
        self._session, self._adapter = session, adapter

    def generate(
        self,
        *,
        user_id: int,
        user_sub: str,
        goal_id: int,
        idempotency_key: str,
        now: datetime,
        expected_latest_version: int | None = None,
    ) -> GeneratedForecast:
        goal = self._session.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id, Goal.is_archived.is_(False)))
        if goal is None:
            raise ForecastGenerationUnavailable("forecast_generation_unavailable")
        if not settings.atlas_forecast_persistence_enabled:
            raise ForecastGenerationUnavailable("forecast_generation_unavailable")
        adapter_failure = False
        try:
            state = load_authoritative_projection_state(
                adapter=self._adapter,
                server_user_id=user_sub,
                server_goal_id=goal_id,
            )
        except CanonicalStateValidationError:
            adapter_failure = True
        if adapter_failure:
            raise ForecastGenerationUnavailable("forecast_generation_unavailable")
        self._validate_state(state, user_sub, goal_id)
        request = self._request(goal, state, now.date())
        result = project_scenarios(request)
        assumptions = {
            "assumption_profile": "phase1-server-default", "assumption_schema_version": ASSUMPTION_SCHEMA_VERSION,
            "annual_return_rates": {k: canonical_decimal_string(v) for k, v in _RATES.items()},
            "annual_inflation_rate": "0.02", "contribution_timing": "end", "period": "monthly",
            "rounding_rule": "ROUND_HALF_EVEN", "money_precision": "0.01",
            "goal_inputs": {"target_amount": canonical_decimal_string(Decimal(str(goal.target_amount))), "horizon_years": goal.horizon_years, "target_date": goal.target_date.isoformat() if goal.target_date is not None else None, "source_representation": "float", "conversion": "decimal-str", "precision_restored": False},
        }
        output = self._output(result)
        base = result.scenarios["base"]
        persisted = ForecastRepository(self._session).persist(
            user_id=user_id, goal_id=goal_id, state=state, idempotency_key=idempotency_key,
            model_version=result.model_version, calculation_version=MODEL_VERSION, calculated_at=now,
            assumption_snapshot=assumptions, output_snapshot=output, ending_balance=base.ending_balance,
            target_gap=base.target_gap or Decimal("0"),
            expected_latest_version=expected_latest_version,
        )
        return GeneratedForecast(persisted)

    @staticmethod
    def _validate_state(state: CanonicalProjectionState, user_sub: str, goal_id: int) -> None:
        if state.user_id != user_sub or state.goal_id != goal_id or state.currency != "USD":
            raise ForecastGenerationUnavailable("forecast_generation_unavailable")
        if state.reconciliation_state != "reconciled" or state.missing_data_codes or state.freshness.observed_age_days > state.freshness.max_data_age_days:
            raise ForecastGenerationUnavailable("forecast_generation_unavailable")

    @staticmethod
    def _request(goal: Goal, state: CanonicalProjectionState, calculation_date: date) -> ProjectionRequest:
        if goal.target_date is None and (
            goal.horizon_years is None or not 1 <= goal.horizon_years <= 50
        ):
            raise ForecastGenerationUnavailable("forecast_generation_unavailable")
        current = sum((Decimal(c.amount) for c in state.current_value_components), Decimal("0"))
        contribution = sum((Decimal(c.amount) for c in state.contribution_inputs), Decimal("0"))
        values = {
            "currency": "USD", "current_balance": current,
            "monthly_contribution": contribution, "calculation_date": calculation_date,
            "data_as_of": date.fromisoformat(state.as_of_timestamp[:10]),
            "max_data_age_days": state.freshness.max_data_age_days,
            "contribution_timing": "end_of_month", "annual_inflation_rate": Decimal("0.02"),
            "annual_return_rates": _RATES, "target_amount": Decimal(str(goal.target_amount)),
        }
        if goal.target_date is not None:
            values["target_date"] = goal.target_date
        else:
            values["horizon_months"] = goal.horizon_years * 12
        try:
            return ProjectionRequest.from_mapping(values)
        except ProjectionValidationError:
            raise ForecastGenerationUnavailable("forecast_generation_unavailable") from None

    @staticmethod
    def _output(result):
        scenarios = {}
        for name, value in result.scenarios.items():
            scenarios[name] = {"annual_return_rate": canonical_decimal_string(value.annual_return_rate), "monthly_real_rate": calculation_decimal_string(value.monthly_real_rate), "ending_balance": canonical_decimal_string(value.ending_balance), "investment_growth": canonical_decimal_string(value.investment_growth), "target_gap": canonical_decimal_string(value.target_gap) if value.target_gap is not None else None, "reaches_target": bool(value.reaches_target)}
        base = result.scenarios["base"]
        target = base.unrounded_target_amount or Decimal("0")
        status = bool(base.reaches_target)
        return {"calculation_decimal_schema_version": CALCULATION_DECIMAL_SCHEMA_VERSION, "target_status": status, "target_decision": {"decision_schema_version": TARGET_DECISION_SCHEMA_VERSION, "scenario": "base", "comparison": "greater_than_or_equal", "decision_basis": "currency_rounded", "rounding_rule": "ROUND_HALF_EVEN", "money_precision": "0.01", "unrounded_ending_balance": calculation_decimal_string(base.unrounded_ending_balance), "unrounded_target_amount": calculation_decimal_string(target), "rounded_ending_balance": canonical_decimal_string(base.ending_balance), "rounded_target_amount": canonical_decimal_string(result.drivers.target_amount), "target_status": status}, "drivers": {"current_balance": canonical_decimal_string(result.drivers.current_balance), "monthly_contribution": canonical_decimal_string(result.drivers.monthly_contribution), "total_contributions": canonical_decimal_string(result.drivers.total_contributions), "target_amount": canonical_decimal_string(result.drivers.target_amount) if result.drivers.target_amount is not None else None, "horizon_months": result.drivers.horizon_months, "data_as_of": result.drivers.data_as_of.isoformat(), "data_age_days": result.drivers.data_age_days}, "scenarios": scenarios}
