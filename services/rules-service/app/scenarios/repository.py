"""Transactional Scenario Lab persistence; plaintext idempotency keys never persist."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from uuid import UUID
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.forecasts.canonical_state import canonical_json, validate_idempotency_key
from app.models import Scenario, ScenarioVersion
from app.scenarios.contracts import SCENARIO_MODEL_VERSION, SCENARIO_SCHEMA_VERSION
from app.scenarios.engine import SCENARIO_CALCULATION_VERSION, ScenarioCalculation


class ScenarioRepositoryConflict(RuntimeError):
    """Stable internal persistence conflict."""


class ScenarioIdempotencyConflict(ScenarioRepositoryConflict):
    """Same idempotency key was reused for a different scenario input."""


class ScenarioNotFound(ScenarioRepositoryConflict):
    """Scenario is not owned by the authenticated caller."""


@dataclass(frozen=True)
class PersistedScenario:
    scenario: Scenario
    version: ScenarioVersion
    created: bool


def _uuid() -> str:
    return str(uuid.uuid4())


_SCENARIO_NAMESPACE = UUID("4f37a6b8-68ab-4f4b-bc6f-2e58ef0d3e5c")


def _deterministic_scenario_id(*, user_id: int, goal_id: int, scenario_input_hash: str) -> str:
    return str(uuid.uuid5(_SCENARIO_NAMESPACE, f"{user_id}:{goal_id}:{scenario_input_hash}"))


def _key_hash(value: str) -> str:
    return hashlib.sha256(validate_idempotency_key(value).encode("ascii")).hexdigest()


def _bounded_snapshot(value: Mapping[str, Any]) -> str:
    """Serialize only generated bounded JSON and reject sensitive payload keys."""

    forbidden_fragments = (
        "raw", "secret", "token", "password", "credential", "access_key",
        "authorization", "statement", "transaction_history", "api_key", "upload",
    )
    def visit(item: Any, depth: int = 0) -> None:
        if depth > 12:
            raise ValueError("scenario snapshot exceeds bounded depth")
        if isinstance(item, Mapping):
            if len(item) > 64:
                raise ValueError("scenario snapshot exceeds bounded fields")
            for key, child in item.items():
                if not isinstance(key, str) or any(fragment in key.lower() for fragment in forbidden_fragments):
                    raise ValueError("scenario snapshot contains a prohibited field")
                visit(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            if len(item) > 64:
                raise ValueError("scenario snapshot exceeds bounded collection")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str) and len(item) > 512:
            raise ValueError("scenario snapshot contains an unbounded string")
        elif isinstance(item, float):
            raise ValueError("scenario snapshots cannot contain binary floating point")
    visit(value)
    return canonical_json(value)


class ScenarioRepository:
    """Own the scenario identity pointer and append-only version transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _identity_query(self, *, user_id: int, scenario_id: str | None = None):
        query = select(Scenario).where(Scenario.user_id == user_id)
        if scenario_id is not None:
            query = query.where(Scenario.id == scenario_id)
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        return query

    def _find_existing(
        self,
        *,
        user_id: int,
        goal_id: int,
        scenario_id: str | None,
        idempotency_hash: str,
        scenario_input_hash: str,
    ) -> PersistedScenario | None:
        scenario = self._session.scalar(self._identity_query(user_id=user_id, scenario_id=scenario_id)) if scenario_id else None
        if scenario_id is not None and scenario is None and self._session.get(Scenario, scenario_id) is not None:
            raise ScenarioNotFound("scenario is not owned by caller")
        if scenario is not None and scenario.goal_id != goal_id:
            raise ScenarioNotFound("scenario goal mismatch")
        if scenario is not None:
            by_key = self._session.scalar(select(ScenarioVersion).where(ScenarioVersion.scenario_id == scenario.id, ScenarioVersion.idempotency_key_hash == idempotency_hash))
            if by_key is not None:
                if by_key.scenario_input_hash != scenario_input_hash:
                    raise ScenarioIdempotencyConflict("scenario idempotency key conflict")
                return PersistedScenario(scenario, by_key, False)
            by_state = self._session.scalar(select(ScenarioVersion).where(ScenarioVersion.scenario_id == scenario.id, ScenarioVersion.scenario_input_hash == scenario_input_hash, ScenarioVersion.model_version == SCENARIO_MODEL_VERSION, ScenarioVersion.calculation_version == SCENARIO_CALCULATION_VERSION))
            if by_state is not None:
                return PersistedScenario(scenario, by_state, False)
            return None
        # A new request without a scenario_id converges to an existing
        # identical saved scenario instead of creating duplicate identities.
        # Check the key first so a divergent replay cannot evade conflict by
        # selecting a new identity.
        key_query = (
            select(ScenarioVersion)
            .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
            .where(Scenario.user_id == user_id, Scenario.goal_id == goal_id, ScenarioVersion.idempotency_key_hash == idempotency_hash)
        )
        keyed = self._session.scalar(key_query)
        if keyed is not None:
            if keyed.scenario_input_hash != scenario_input_hash:
                raise ScenarioIdempotencyConflict("scenario idempotency key conflict")
            owner = self._session.get(Scenario, keyed.scenario_id)
            return PersistedScenario(owner, keyed, False)
        query = (
            select(ScenarioVersion)
            .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
            .where(
                Scenario.user_id == user_id,
                Scenario.goal_id == goal_id,
                ScenarioVersion.scenario_input_hash == scenario_input_hash,
                ScenarioVersion.model_version == SCENARIO_MODEL_VERSION,
                ScenarioVersion.calculation_version == SCENARIO_CALCULATION_VERSION,
            )
        )
        version = self._session.scalar(query)
        if version is None:
            return None
        scenario = self._session.get(Scenario, version.scenario_id)
        return PersistedScenario(scenario, version, False)

    def _persist_once(
        self,
        *,
        user_id: int,
        goal_id: int,
        scenario_id: str | None,
        baseline_forecast_id: str,
        baseline_version_number: int,
        calculation: ScenarioCalculation,
        idempotency_hash: str,
        calculated_at: datetime,
    ) -> PersistedScenario:
        scenario = self._session.scalar(self._identity_query(user_id=user_id, scenario_id=scenario_id)) if scenario_id else None
        if scenario_id is not None and scenario is None and self._session.get(Scenario, scenario_id) is not None:
            raise ScenarioNotFound("scenario is not owned by caller")
        if scenario is not None and scenario.goal_id != goal_id:
            raise ScenarioNotFound("scenario goal mismatch")
        if scenario is None:
            identity_id = scenario_id or _deterministic_scenario_id(
                user_id=user_id, goal_id=goal_id, scenario_input_hash=calculation.scenario_input_hash
            )
            scenario = Scenario(
                id=identity_id,
                user_id=user_id,
                goal_id=goal_id,
                baseline_forecast_id=baseline_forecast_id,
                currency="USD",
            )
            self._session.add(scenario)
            self._session.flush()
        elif scenario.baseline_forecast_id != baseline_forecast_id:
            raise ScenarioRepositoryConflict("scenario baseline is incompatible")

        existing = self._find_existing(
            user_id=user_id,
            goal_id=goal_id,
            scenario_id=scenario.id,
            idempotency_hash=idempotency_hash,
            scenario_input_hash=calculation.scenario_input_hash,
        )
        if existing is not None:
            return existing
        if scenario.lifecycle_state == "archived":
            raise ScenarioRepositoryConflict("archived scenarios cannot receive new versions")
        version_number = int(scenario.latest_version_number) + 1
        version = ScenarioVersion(
            id=_uuid(),
            scenario_id=scenario.id,
            version_number=version_number,
            baseline_forecast_id=baseline_forecast_id,
            baseline_version_number=baseline_version_number,
            baseline_input_state_hash=calculation.baseline_input_state_hash,
            scenario_input_hash=calculation.scenario_input_hash,
            idempotency_key_hash=idempotency_hash,
            schema_version=SCENARIO_SCHEMA_VERSION,
            model_version=SCENARIO_MODEL_VERSION,
            calculation_version=SCENARIO_CALCULATION_VERSION,
            currency="USD",
            calculated_at=calculated_at,
            source_data_as_of=datetime.combine(calculation.source_data_as_of, datetime.min.time(), tzinfo=calculated_at.tzinfo),
            max_data_age_days=calculation.max_data_age_days,
            data_age_days=calculation.data_age_days,
            input_snapshot_json=_bounded_snapshot(calculation.input_snapshot),
            result_snapshot_json=_bounded_snapshot(calculation.result_snapshot),
            comparison_snapshot_json=_bounded_snapshot(calculation.comparison_snapshot),
        )
        self._session.add(version)
        scenario.latest_version_number = version_number
        self._session.flush()
        return PersistedScenario(scenario, version, True)

    def persist(
        self,
        *,
        user_id: int,
        goal_id: int,
        scenario_id: str | None,
        baseline_forecast_id: str,
        baseline_version_number: int,
        calculation: ScenarioCalculation,
        idempotency_key: str,
        calculated_at: datetime,
    ) -> PersistedScenario:
        if not calculated_at.tzinfo or calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware")
        idempotency_hash = _key_hash(idempotency_key)
        try:
            if scenario_id is None:
                existing = self._find_existing(
                    user_id=user_id,
                    goal_id=goal_id,
                    scenario_id=None,
                    idempotency_hash=idempotency_hash,
                    scenario_input_hash=calculation.scenario_input_hash,
                )
                if existing is not None:
                    self._session.commit()
                    return existing
            result = self._persist_once(
                user_id=user_id,
                goal_id=goal_id,
                scenario_id=scenario_id,
                baseline_forecast_id=baseline_forecast_id,
                baseline_version_number=baseline_version_number,
                calculation=calculation,
                idempotency_hash=idempotency_hash,
                calculated_at=calculated_at,
            )
            self._session.commit()
            return result
        except (ScenarioIdempotencyConflict, ScenarioNotFound, ScenarioRepositoryConflict, ValueError):
            self._session.rollback()
            raise
        except (IntegrityError, OperationalError) as exc:
            self._session.rollback()
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                try:
                    recovered = self._find_existing(
                        user_id=user_id,
                        goal_id=goal_id,
                        scenario_id=scenario_id,
                        idempotency_hash=idempotency_hash,
                        scenario_input_hash=calculation.scenario_input_hash,
                    )
                except OperationalError:
                    self._session.rollback()
                    recovered = None
                if recovered is not None:
                    self._session.commit()
                    return recovered
                self._session.rollback()
                if self._session.bind is None or self._session.bind.dialect.name != "sqlite":
                    break
                time.sleep(0.05)
            raise ScenarioRepositoryConflict("scenario persistence conflict") from exc

    def archive(self, *, user_id: int, scenario_id: str, idempotency_key: str) -> Scenario:
        scenario = self._session.scalar(self._identity_query(user_id=user_id, scenario_id=scenario_id))
        if scenario is None:
            raise ScenarioNotFound("scenario not found")
        key_hash = _key_hash(idempotency_key)
        if scenario.lifecycle_state == "archived":
            if scenario.archive_idempotency_key_hash not in (None, key_hash):
                raise ScenarioIdempotencyConflict("archive idempotency key conflict")
            if scenario.archive_idempotency_key_hash is None:
                scenario.archive_idempotency_key_hash = key_hash
                self._session.commit()
            return scenario
        scenario.lifecycle_state = "archived"
        scenario.archived_at = datetime.now(timezone.utc)
        scenario.archive_idempotency_key_hash = key_hash
        self._session.commit()
        return scenario
