"""Read-only ORM-to-schema mapping for the Phase 1 versioned read API.

This module is intentionally narrow:

- Translates ``Forecast`` + ``ForecastVersion`` ORM rows into the
  Slice C ``ForecastResponse`` / ``ForecastVersionResponse`` Pydantic
  models WITHOUT calling the canonical-state adapter or the projection
  module.  Both endpoints remain pure read paths.
- Re-validates every persisted snapshot via the Slice C sub-models, so
  a future model-shape drift cannot silently bypass schema constraints
  on the wire.
- Raises :class:`InternalDataCorruption` if a persisted snapshot
  fails the strict Slice C schema — the route layer handles this as a
  sanitized 500 envelope (no Pydantic location or message reaches the
  client).
- Produces the deterministic ETag used by both detail endpoints
  (``bare uuid-v-n`` form via the merged codec so ``If-None-Match``
  parses identically on the next read).

This module **MUST NOT** import the canonical-state adapter, the
projection module, or any HTTP client.  The ``import app.routes.forecasts``
graph is covered by an explicit graph-sanity test in the route suite.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from decimal import Decimal

from app.forecasts.api_codecs import derive_forecast_etag
from app.forecasts.canonical_state import canonical_decimal_string
from app.forecasts.schemas import (
    AssumptionSnapshotSchema,
    ForecastLink,
    ForecastResponse,
    ForecastVersionResponse,
    OutputSnapshotSchema,
    ProvenanceSnapshotSchema,
    SnapshotMetaSchema,
)
from app.models import Forecast, ForecastVersion


class InternalDataCorruption(RuntimeError):
    """A persisted snapshot cannot be reconstructed into the Slice C schema.

    The route layer translates this into a sanitized 500 envelope; the
    raw Pydantic ``ValidationError`` text + ``loc`` must NEVER reach the
    client (``hide_input_in_errors=True`` on the schema is the second
    line of defence; this exception is the first).
    """


def _utc_z(dt: datetime | None) -> str:
    """Serialize a DateTime ORM column into a UTC RFC 3339 Z suffix string.

    SQLite timestamps are naive; treat them as UTC (the application only
    ever writes timezone-aware values, so a naive value embeds UTC by
    construction).  PostgreSQL via SQLAlchemy returns timezone-aware
    values that we ceil to microseconds and re-serialize with the ``Z``
    suffix that the Slice C schemas require.
    """
    if dt is None:
        raise InternalDataCorruption("persisted timestamp is null")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (
        dt.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_snapshot(raw: str | None) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw:
        raise InternalDataCorruption("empty persisted snapshot")
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise InternalDataCorruption("persisted snapshot is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise InternalDataCorruption("persisted snapshot is not an object")
    return parsed


def _validate_snapshot(pyd_class: type, raw: dict[str, Any]) -> Any:
    try:
        return pyd_class.model_validate(raw)
    except Exception as exc:
        raise InternalDataCorruption("persisted snapshot schema mismatch") from exc


def _canonical_money(value: Any) -> str:
    """Convert a persisted ``NUMERIC(38, 2)`` Decimal back to its canonical
    unrounded string form expected by the Slice C response schemas.

    The persisted value already lost sub-cent precision at write time
    (``ROUND_HALF_EVEN`` at ``0.01``), so the canonical form has zero
    fractional digits or two — never an exotic exponent.
    """
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, str):
        decimal_value = Decimal(value)
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    else:
        raise InternalDataCorruption("persisted money is not a Decimal")
    return canonical_decimal_string(decimal_value)


def _forecast_links(forecast_id: str) -> tuple[ForecastLink, ...]:
    href_self = f"/api/v1/forecasts/{forecast_id}"
    href_versions = f"/api/v1/forecasts/{forecast_id}/versions"
    return (
        ForecastLink(rel="self", href=href_self),
        ForecastLink(rel="versions", href=href_versions),
    )


def _version_links(forecast_id: str, version_number: int) -> tuple[ForecastLink, ...]:
    href_self = f"/api/v1/forecasts/{forecast_id}/versions/{version_number}"
    href_parent = f"/api/v1/forecasts/{forecast_id}"
    return (
        ForecastLink(rel="self", href=href_self),
        ForecastLink(rel="forecast", href=href_parent),
    )


def forecast_to_response(
    *, forecast: Forecast, latest_version: ForecastVersion
) -> ForecastResponse:
    """Translate one owned ``Forecast`` row into a ``ForecastResponse``.

    ``latest_version`` is REQUIRED (the ``active`` lifecycle row must
    point at one already-persisted version).  The route layer never
    invokes this for forecasts without an established latest version
    regardless of how the migration evolved.
    """
    etag_bare = derive_forecast_etag(
        forecast_id=forecast.id,
        version_number=latest_version.version_number,
    )
    return ForecastResponse(
        forecast_id=forecast.id,
        goal_id=forecast.goal_id,
        forecast_kind=forecast.forecast_kind,  # type: ignore[arg-type]  # Pydantic Literal
        currency=forecast.currency,  # type: ignore[arg-type]  # Pydantic Literal
        lifecycle_state=forecast.lifecycle_state,  # type: ignore[arg-type]  # Pydantic Literal
        latest_version_number=latest_version.version_number,
        etag=etag_bare,
        latest_version_id=latest_version.id,
        created_at=_utc_z(forecast.created_at),
        updated_at=_utc_z(forecast.updated_at),
        links=_forecast_links(forecast.id),
    )


def version_to_response(
    *,
    forecast_id: str,
    version: ForecastVersion,
) -> ForecastVersionResponse:
    """Translate one owned ``ForecastVersion`` row into a ``ForecastVersionResponse``.

    All four snapshot JSON columns are re-validated against the Slice C
    Pydantic sub-models so a future schema drift fails closed instead
    of silently passing through to the wire.
    """
    raw_assumption = _parse_snapshot(version.assumption_snapshot_json)
    raw_output = _parse_snapshot(version.output_snapshot_json)
    raw_provenance = _parse_snapshot(version.provenance_snapshot_json)
    raw_input = _parse_snapshot(version.input_snapshot_json)
    assumption = _validate_snapshot(AssumptionSnapshotSchema, raw_assumption)
    output = _validate_snapshot(OutputSnapshotSchema, raw_output)
    provenance = _validate_snapshot(ProvenanceSnapshotSchema, raw_provenance)
    etag_bare = derive_forecast_etag(
        forecast_id=forecast_id,
        version_number=version.version_number,
    )
    return ForecastVersionResponse(
        forecast_id=forecast_id,
        version_id=version.id,
        version_number=version.version_number,
        etag=etag_bare,
        input_state_hash=version.input_state_hash,
        idempotency_key_hash=version.idempotency_key_hash,
        snapshot=SnapshotMetaSchema(
            snapshot_schema_version=version.snapshot_schema_version,
            hash_schema_version=version.hash_schema_version,
            model_version=version.model_version,
            calculation_version=version.calculation_version,
        ),
        currency=version.currency,  # type: ignore[arg-type]  # Pydantic Literal
        calculated_at=_utc_z(version.calculated_at),
        data_as_of=_utc_z(version.data_as_of),
        max_data_age_days=version.max_data_age_days,
        data_age_days=version.data_age_days,
        created_at=_utc_z(version.created_at),
        ending_balance=_canonical_money(version.ending_balance),
        target_gap=_canonical_money(version.target_gap),
        target_status=output.target_status,
        target_decision=output.target_decision,
        drivers=output.drivers,
        scenarios=output,
        assumption_snapshot=assumption,
        provenance_snapshot=provenance,
        input_snapshot=raw_input,
        links=_version_links(forecast_id=forecast_id, version_number=version.version_number),
    )
