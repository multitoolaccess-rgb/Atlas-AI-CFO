"""Transactional persistence for immutable forecast versions.

This module is intentionally internal: routes and trusted adapters are added in
later Phase 1 slices. It never logs or stores a raw idempotency key.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.forecasts.canonical_state import (
    CanonicalProjectionState,
    validate_idempotency_key,
)
from app.forecasts.snapshots import ForecastSnapshots, build_forecast_snapshots
from app.models import Forecast, ForecastVersion


class ForecastRepositoryConflict(RuntimeError):
    """Stable internal conflict base class without sensitive request details."""


class IdempotencyConflict(ForecastRepositoryConflict):
    """A key was reused for materially different canonical state."""


class StaleForecastVersion(ForecastRepositoryConflict):
    """Caller expected a different latest immutable version."""


@dataclass(frozen=True)
class PersistedForecastVersion:
    forecast: Forecast
    version: ForecastVersion
    created: bool
    input_snapshot_json: str


def _uuid() -> str:
    return str(uuid.uuid4())


def _key_hash(value: str) -> str:
    return hashlib.sha256(validate_idempotency_key(value).encode("ascii")).hexdigest()


def _money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("persisted money must be a finite Decimal")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class ForecastRepository:
    """Own a short transaction that creates or reuses immutable versions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _identity_query(self, *, user_id: int, goal_id: int):
        query = select(Forecast).where(
            Forecast.user_id == user_id,
            Forecast.goal_id == goal_id,
            Forecast.forecast_kind == "goal_projection",
            Forecast.currency == "USD",
        )
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        return query

    def persist(
        self,
        *,
        user_id: int,
        goal_id: int,
        state: CanonicalProjectionState,
        idempotency_key: str,
        model_version: str,
        calculation_version: str,
        calculated_at: datetime,
        assumption_snapshot: Mapping[str, Any],
        output_snapshot: Mapping[str, Any],
        ending_balance: Decimal,
        target_gap: Decimal,
        expected_latest_version: int | None = None,
    ) -> PersistedForecastVersion:
        """Persist once, replay safely, or raise a bounded conflict.

        The service layer is responsible for authentication, goal authorization,
        adapter invocation, and calculation. This repository only accepts the
        already-bound canonical state and transactional persistence inputs.
        """

        if state.goal_id != goal_id:
            raise ValueError("canonical state goal does not match repository scope")
        key_hash = _key_hash(idempotency_key)
        snapshots = build_forecast_snapshots(
            state=state,
            assumption_snapshot=assumption_snapshot,
            output_snapshot=output_snapshot,
        )
        if not calculated_at.tzinfo or calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware")

        try:
            with self._session.begin_nested():
                forecast = self._session.scalar(
                    self._identity_query(user_id=user_id, goal_id=goal_id)
                )
                if forecast is None:
                    forecast = Forecast(id=_uuid(), user_id=user_id, goal_id=goal_id)
                    self._session.add(forecast)
                    self._session.flush()

                existing_key = self._session.scalar(
                    select(ForecastVersion).where(
                        ForecastVersion.forecast_id == forecast.id,
                        ForecastVersion.idempotency_key_hash == key_hash,
                    )
                )
                if existing_key is not None:
                    if existing_key.input_state_hash != snapshots.input_state_hash:
                        raise IdempotencyConflict("idempotency key conflicts with canonical state")
                    return PersistedForecastVersion(forecast, existing_key, False, snapshots.input_snapshot_json)

                if expected_latest_version is not None and forecast.latest_version_number != expected_latest_version:
                    raise StaleForecastVersion("forecast latest version is stale")

                existing_state = self._session.scalar(
                    select(ForecastVersion).where(
                        ForecastVersion.forecast_id == forecast.id,
                        ForecastVersion.input_state_hash == snapshots.input_state_hash,
                        ForecastVersion.model_version == model_version,
                        ForecastVersion.calculation_version == calculation_version,
                    )
                )
                if existing_state is not None:
                    return PersistedForecastVersion(forecast, existing_state, False, snapshots.input_snapshot_json)

                version_number = forecast.latest_version_number + 1
                version = ForecastVersion(
                    id=_uuid(), forecast_id=forecast.id, version_number=version_number,
                    input_state_hash=snapshots.input_state_hash, idempotency_key_hash=key_hash,
                    snapshot_schema_version=state.schema_version,
                    hash_schema_version=state.canonicalization.hash_schema_version,
                    model_version=model_version, calculation_version=calculation_version,
                    currency=state.currency, calculated_at=calculated_at,
                    data_as_of=datetime.fromisoformat(
                        state.as_of_timestamp.replace("Z", "+00:00")
                    ), max_data_age_days=state.freshness.max_data_age_days,
                    data_age_days=state.freshness.observed_age_days,
                    input_snapshot_json=snapshots.input_snapshot_json,
                    assumption_snapshot_json=snapshots.assumption_snapshot_json,
                    output_snapshot_json=snapshots.output_snapshot_json,
                    provenance_snapshot_json=snapshots.provenance_snapshot_json,
                    ending_balance=_money(ending_balance), target_gap=_money(target_gap),
                )
                self._session.add(version)
                forecast.latest_version_number = version_number
                self._session.flush()
                return PersistedForecastVersion(forecast, version, True, snapshots.input_snapshot_json)
        except IntegrityError as exc:
            raise ForecastRepositoryConflict("forecast persistence conflict") from exc
