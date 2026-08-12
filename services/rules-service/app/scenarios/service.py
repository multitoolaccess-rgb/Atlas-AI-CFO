"""Scenario Lab application service; all financial authority remains server-side."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.forecasts.canonical_state import (
    CanonicalProjectionState,
    CanonicalStateValidationError,
    FinlynqProjectionStateAdapter,
    canonical_json,
    hash_input_state,
    load_authoritative_projection_state,
)
from app.forecasts.service import ForecastGenerationService, ForecastGenerationUnavailable
from app.models import Forecast, ForecastVersion, Goal, Scenario
from app.scenarios.contracts import ScenarioInput
from app.scenarios.engine import calculate_scenario
from app.scenarios.repository import (
    PersistedScenario,
    ScenarioNotFound,
    ScenarioRepository,
)


class ScenarioGenerationUnavailable(RuntimeError):
    """Safe internal failure without financial payload details."""


@dataclass(frozen=True)
class GeneratedScenario:
    persisted: PersistedScenario


class ScenarioService:
    """Authorize a goal, bind its immutable baseline, then calculate and persist."""

    def __init__(self, session: Session, adapter: FinlynqProjectionStateAdapter) -> None:
        self._session = session
        self._adapter = adapter

    def _goal(self, *, user_id: int, goal_id: int) -> Goal:
        goal = self._session.scalar(
            select(Goal).where(
                Goal.id == goal_id,
                Goal.user_id == user_id,
                Goal.is_archived.is_(False),
            )
        )
        if goal is None:
            raise ScenarioGenerationUnavailable("scenario_not_found")
        return goal

    def _baseline(self, *, user_id: int, goal_id: int) -> tuple[Forecast, ForecastVersion]:
        forecast = self._session.scalar(
            select(Forecast).where(
                Forecast.user_id == user_id,
                Forecast.goal_id == goal_id,
                Forecast.forecast_kind == "goal_projection",
                Forecast.currency == "USD",
            )
        )
        if forecast is None or int(forecast.latest_version_number) < 1:
            raise ScenarioGenerationUnavailable("baseline_forecast_required")
        version = self._session.scalar(
            select(ForecastVersion).where(
                ForecastVersion.forecast_id == forecast.id,
                ForecastVersion.version_number == forecast.latest_version_number,
            )
        )
        if version is None or version.currency != "USD":
            raise ScenarioGenerationUnavailable("baseline_forecast_required")
        return forecast, version

    @staticmethod
    def _baseline_state_hash(version: ForecastVersion) -> str:
        try:
            payload = json.loads(version.input_snapshot_json)
            state = payload["state"]
            return hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ScenarioGenerationUnavailable("baseline_forecast_required") from exc

    @staticmethod
    def _validate_state(state: CanonicalProjectionState, user_sub: str, goal_id: int) -> None:
        if state.user_id != user_sub or state.goal_id != goal_id or state.currency != "USD":
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable")
        if state.reconciliation_state != "reconciled" or state.missing_data_codes:
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable")
        if state.freshness.observed_age_days > state.freshness.max_data_age_days:
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable")

    def generate(
        self,
        *,
        user_id: int,
        user_sub: str,
        goal_id: int,
        scenario_input: ScenarioInput,
        idempotency_key: str,
        now: datetime,
    ) -> GeneratedScenario:
        if not settings.atlas_scenario_lab_enabled:
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable")
        goal = self._goal(user_id=user_id, goal_id=goal_id)
        forecast, baseline_version = self._baseline(user_id=user_id, goal_id=goal_id)
        try:
            state = load_authoritative_projection_state(
                adapter=self._adapter,
                server_user_id=user_sub,
                server_goal_id=goal_id,
            )
        except CanonicalStateValidationError:
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable") from None
        self._validate_state(state, user_sub, goal_id)
        baseline_canonical_hash = self._baseline_state_hash(baseline_version)
        if hash_input_state(state) != baseline_canonical_hash:
            raise ScenarioGenerationUnavailable("baseline_is_stale")
        try:
            request = ForecastGenerationService._request(goal, state, now.date())
        except ForecastGenerationUnavailable:
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable") from None
        try:
            calculation = calculate_scenario(
                request=request,
                scenario_input=scenario_input,
                baseline_forecast_id=str(forecast.id),
                baseline_version_number=int(baseline_version.version_number),
                baseline_input_state_hash=baseline_canonical_hash,
                baseline_output_snapshot=json.loads(baseline_version.output_snapshot_json),
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable") from None
        persisted = ScenarioRepository(self._session).persist(
            user_id=user_id,
            goal_id=goal_id,
            scenario_id=scenario_input.scenario_id,
            baseline_forecast_id=str(forecast.id),
            baseline_version_number=int(baseline_version.version_number),
            calculation=calculation,
            idempotency_key=idempotency_key,
            calculated_at=now.astimezone(timezone.utc),
        )
        return GeneratedScenario(persisted)

    def archive(self, *, user_id: int, scenario_id: str, idempotency_key: str) -> Scenario:
        if not settings.atlas_scenario_lab_enabled:
            raise ScenarioGenerationUnavailable("scenario_generation_unavailable")
        return ScenarioRepository(self._session).archive(user_id=user_id, scenario_id=scenario_id, idempotency_key=idempotency_key)
