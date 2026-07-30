"""Transactional persistence for immutable forecast versions.

This module is intentionally internal: routes and trusted adapters are added in
later Phase 1 slices. It never logs or stores a raw idempotency key.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.forecasts.api_codecs import ForecastCursor
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

    def _existing_result(
        self,
        *,
        user_id: int,
        goal_id: int,
        key_hash: str,
        snapshots: ForecastSnapshots,
        model_version: str,
        calculation_version: str,
    ) -> PersistedForecastVersion | None:
        """Find a committed winner after a database uniqueness race.

        This is deliberately a read-only recovery path.  It never retries an
        insert, so a conflicting request cannot create a second mutable or
        duplicate version.
        """

        forecast = self._session.scalar(
            self._identity_query(user_id=user_id, goal_id=goal_id)
        )
        if forecast is None:
            return None

        existing_key = self._session.scalar(
            select(ForecastVersion).where(
                ForecastVersion.forecast_id == forecast.id,
                ForecastVersion.idempotency_key_hash == key_hash,
            )
        )
        if existing_key is not None:
            if existing_key.input_state_hash != snapshots.input_state_hash:
                raise IdempotencyConflict("idempotency key conflicts with canonical state")
            return PersistedForecastVersion(
                forecast, existing_key, False, snapshots.input_snapshot_json
            )

        existing_state = self._session.scalar(
            select(ForecastVersion).where(
                ForecastVersion.forecast_id == forecast.id,
                ForecastVersion.input_state_hash == snapshots.input_state_hash,
                ForecastVersion.model_version == model_version,
                ForecastVersion.calculation_version == calculation_version,
            )
        )
        if existing_state is not None:
            return PersistedForecastVersion(
                forecast, existing_state, False, snapshots.input_snapshot_json
            )
        return None

    def _recover_database_winner(
        self,
        *,
        user_id: int,
        goal_id: int,
        key_hash: str,
        snapshots: ForecastSnapshots,
        model_version: str,
        calculation_version: str,
        retry_sqlite: bool,
    ) -> PersistedForecastVersion | None:
        """Boundedly re-read a committed winner after a uniqueness or lock race."""

        attempts = 20 if retry_sqlite else 1
        deadline = time.monotonic() + 1.0
        for attempt in range(attempts):
            try:
                recovered = self._existing_result(
                    user_id=user_id,
                    goal_id=goal_id,
                    key_hash=key_hash,
                    snapshots=snapshots,
                    model_version=model_version,
                    calculation_version=calculation_version,
                )
            except OperationalError:
                self._session.rollback()
                recovered = None
            if recovered is not None:
                self._session.commit()
                return recovered
            self._session.rollback()
            if not retry_sqlite or attempt + 1 == attempts or time.monotonic() >= deadline:
                return None
            time.sleep(0.05)
        return None

    def _persist_once(
        self,
        *,
        user_id: int,
        goal_id: int,
        key_hash: str,
        snapshots: ForecastSnapshots,
        state: CanonicalProjectionState,
        model_version: str,
        calculation_version: str,
        calculated_at: datetime,
        ending_balance: Decimal,
        target_gap: Decimal,
        expected_latest_version: int | None,
    ) -> PersistedForecastVersion:
        """Execute one short database attempt; caller owns commit or rollback."""

        forecast = self._session.scalar(
            self._identity_query(user_id=user_id, goal_id=goal_id)
        )
        if forecast is None:
            forecast = Forecast(id=_uuid(), user_id=user_id, goal_id=goal_id)
            self._session.add(forecast)
            self._session.flush()

        if (
            expected_latest_version is not None
            and forecast.latest_version_number != expected_latest_version
        ):
            raise StaleForecastVersion("forecast latest version is stale")

        existing = self._existing_result(
            user_id=user_id,
            goal_id=goal_id,
            key_hash=key_hash,
            snapshots=snapshots,
            model_version=model_version,
            calculation_version=calculation_version,
        )
        if existing is not None:
            return existing

        version_number = forecast.latest_version_number + 1
        version = ForecastVersion(
            id=_uuid(),
            forecast_id=forecast.id,
            version_number=version_number,
            input_state_hash=snapshots.input_state_hash,
            idempotency_key_hash=key_hash,
            snapshot_schema_version=state.schema_version,
            hash_schema_version=state.canonicalization.hash_schema_version,
            model_version=model_version,
            calculation_version=calculation_version,
            currency=state.currency,
            calculated_at=calculated_at,
            data_as_of=datetime.fromisoformat(
                state.as_of_timestamp.replace("Z", "+00:00")
            ),
            max_data_age_days=state.freshness.max_data_age_days,
            data_age_days=state.freshness.observed_age_days,
            input_snapshot_json=snapshots.input_snapshot_json,
            assumption_snapshot_json=snapshots.assumption_snapshot_json,
            output_snapshot_json=snapshots.output_snapshot_json,
            provenance_snapshot_json=snapshots.provenance_snapshot_json,
            ending_balance=_money(ending_balance),
            target_gap=_money(target_gap),
        )
        self._session.add(version)
        forecast.latest_version_number = version_number
        self._session.flush()
        return PersistedForecastVersion(
            forecast, version, True, snapshots.input_snapshot_json
        )

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
            result = self._persist_once(
                user_id=user_id,
                goal_id=goal_id,
                key_hash=key_hash,
                snapshots=snapshots,
                state=state,
                model_version=model_version,
                calculation_version=calculation_version,
                calculated_at=calculated_at,
                ending_balance=ending_balance,
                target_gap=target_gap,
                expected_latest_version=expected_latest_version,
            )
            # This repository owns the short persistence transaction.  A
            # savepoint alone is insufficient because dependency teardown may
            # otherwise roll the outer transaction back.
            self._session.commit()
            return result
        except (IdempotencyConflict, StaleForecastVersion, ValueError):
            self._session.rollback()
            raise
        except (IntegrityError, OperationalError) as exc:
            # A unique/locking race is resolved only by observing the committed
            # winner.  SQLite has no row locks; PostgreSQL gets the lock in the
            # identity query above.  Both retain database uniqueness as the
            # final concurrency backstop.
            self._session.rollback()
            try:
                recovered = self._recover_database_winner(
                    user_id=user_id,
                    goal_id=goal_id,
                    key_hash=key_hash,
                    snapshots=snapshots,
                    model_version=model_version,
                    calculation_version=calculation_version,
                    retry_sqlite=(
                        self._session.bind is not None
                        and self._session.bind.dialect.name == "sqlite"
                    ),
                )
                if recovered is not None:
                    return recovered
            except IdempotencyConflict:
                self._session.rollback()
                raise
            self._session.rollback()
            raise ForecastRepositoryConflict("forecast persistence conflict") from exc

    # ------------------------------------------------------------
    # Read methods (Slice D) — owned by user; ordered by stable
    # (created_at DESC, id DESC) for forecasts and (version_number
    # DESC, id DESC) for versions.  None is returned for missing
    # or cross-user resources so the route renders an indistinguishable
    # 404 envelope without exposing ownership.
    # ------------------------------------------------------------

    def get_forecast_for_user(
        self, *, user_id: int, forecast_id: str
    ) -> tuple[Forecast, ForecastVersion | None] | None:
        """Return (forecast, latest_version) if owned; else None."""
        forecast = self._session.scalar(
            select(Forecast).where(
                Forecast.id == forecast_id,
                Forecast.user_id == user_id,
            )
        )
        if forecast is None:
            return None
        latest = self._session.scalar(
            select(ForecastVersion)
            .where(ForecastVersion.forecast_id == forecast.id)
            .order_by(
                ForecastVersion.version_number.desc(),
                ForecastVersion.id.desc(),
            )
            .limit(1)
        )
        return forecast, latest

    def get_forecast_version_for_user(
        self,
        *,
        user_id: int,
        forecast_id: str,
        version_number: int,
    ) -> tuple[Forecast, ForecastVersion] | None:
        """Return (forecast, version) if owned; else None."""
        forecast = self._session.scalar(
            select(Forecast).where(
                Forecast.id == forecast_id,
                Forecast.user_id == user_id,
            ).limit(1)
        )
        if forecast is None:
            return None
        version = self._session.scalar(
            select(ForecastVersion).where(
                ForecastVersion.forecast_id == forecast.id,
                ForecastVersion.version_number == version_number,
            ).limit(1)
        )
        if version is None:
            return None
        return forecast, version

    def list_forecasts_paginated(
        self,
        *,
        user_id: int,
        goal_id: int | None,
        cursor: ForecastCursor | None,
        limit: int,
    ) -> tuple[list[tuple[Forecast, ForecastVersion | None]], ForecastCursor | None]:
        """Newest-first listing using (created_at DESC, id DESC).

        Fetches ``limit + 1`` rows; if the extra row arrives, the
        page has more and a cursor pointing at the last returned
        forecast is built.  The ``+1`` is bounded (max limit 64 per
        the response schema), so the over-fetch is bounded.
        """
        from sqlalchemy import and_, or_, tuple_

        bound = max(1, min(64, limit)) + 1
        stmt = select(Forecast).where(Forecast.user_id == user_id)
        if goal_id is not None:
            stmt = stmt.where(Forecast.goal_id == goal_id)
        if cursor is not None:
            # Strict tuple comparison: a row is included iff
            # ``(created_at, id)`` is lexicographically strictly less
            # than ``(cursor.created_at, cursor.id)``.  Using a single
            # ``ROW`` comparison (rather than the OR-cascade of
            # ``created_at < OR (created_at = AND id <)``) keeps the
            # boundary row deterministically excluded across both
            # Postgres (typed datetime) and SQLite (text-collated datetime)
            # without depending on timestamp precision alignment
            # between cursor serialization and DB persistence.
            stmt = stmt.where(
                tuple_(Forecast.created_at, Forecast.id)
                < tuple_(cursor.created_at, cursor.forecast_id)
            )
        forecasts = list(
            self._session.scalars(
                stmt.order_by(
                    Forecast.created_at.desc(),
                    Forecast.id.desc(),
                ).limit(bound)
            ).all()
        )
        has_more = len(forecasts) > bound - 1
        forecasts = forecasts[: bound - 1]
        pairs: list[tuple[Forecast, ForecastVersion | None]] = []
        for fc in forecasts:
            latest = self._session.scalar(
                select(ForecastVersion)
                .where(ForecastVersion.forecast_id == fc.id)
                .order_by(
                    ForecastVersion.version_number.desc(),
                    ForecastVersion.id.desc(),
                )
                .limit(1)
            )
            pairs.append((fc, latest))
        next_cursor: ForecastCursor | None = None
        if has_more and forecasts:
            last = forecasts[-1]
            # ``Forecast.created_at`` arrives from SQLite as a naive
            # ``datetime`` because the dialect stores it as text and
            # strips the tzinfo.  Calling ``.astimezone(timezone.utc)``
            # on a *naive* datetime would silently treat the value as
            # local time and shift it by the system offset (positive
            # hours into the future relative to the stored row), causing
            # the subsequent page-2 ``< cursor.created_at`` filter to
            # re-include the boundary row.  ``.replace(tzinfo=...)`` on
            # the naive case labels the value as already-UTC instead of
            # shifting it; the already-aware case still uses
            # ``.astimezone(utc)`` so timezone-normalized comparisons on
            # Postgres remain correct.
            utc_created_at = (
                last.created_at.replace(tzinfo=timezone.utc)
                if last.created_at.tzinfo is None
                else last.created_at.astimezone(timezone.utc)
            )
            next_cursor = ForecastCursor(
                forecast_id=last.id,
                created_at=utc_created_at,
                version_number=last.latest_version_number,
            )
        return pairs, next_cursor

    def list_forecast_versions_paginated(
        self,
        *,
        user_id: int,
        forecast_id: str,
        cursor: ForecastCursor | None,
        limit: int,
    ) -> tuple[list[ForecastVersion], ForecastCursor | None] | None:
        """Newest-first (version_number DESC, id DESC).

        Returns ``None`` when the user does not own the forecast
        (route layer translates to indistinguishable 404).
        """
        from sqlalchemy import and_, or_, tuple_

        forecast = self._session.scalar(
            select(Forecast).where(
                Forecast.id == forecast_id,
                Forecast.user_id == user_id,
            ).limit(1)
        )
        if forecast is None:
            return None
        bound = max(1, min(64, limit)) + 1
        stmt = (
            select(ForecastVersion)
            .where(
                ForecastVersion.forecast_id == forecast_id,
            )
        )
        # ``(forecast_id, version_number)`` is UNIQUE in the schema, so a
        # secondary tie-breaker is not needed for deterministic pagination:
        # ``version_number < cursor.version_number`` already excludes every
        # already-shown row.  The cursor's ``created_at`` field is preserved
        # for the merged codec round-trip but not used as a comparator.
        if cursor is not None:
            stmt = stmt.where(
                ForecastVersion.version_number < cursor.version_number,
            )
        versions = list(
            self._session.scalars(
                stmt.order_by(
                    ForecastVersion.version_number.desc(),
                ).limit(bound)
            ).all()
        )
        has_more = len(versions) > bound - 1
        versions = versions[: bound - 1]
        next_cursor: ForecastCursor | None = None
        if has_more and versions:
            last = versions[-1]
            # Same tzinfo-on-naive handling as ``list_forecasts_paginated``
            # -- see the parent method's comment for the SQLite text-store
            # rationale.  Without the conditional, a future-shifted
            # ``created_at`` would re-include the boundary version row
            # on the next page.
            utc_created_at = (
                last.created_at.replace(tzinfo=timezone.utc)
                if last.created_at.tzinfo is None
                else last.created_at.astimezone(timezone.utc)
            )
            next_cursor = ForecastCursor(
                forecast_id=last.forecast_id,
                created_at=utc_created_at,
                version_number=last.version_number,
            )
        return versions, next_cursor

