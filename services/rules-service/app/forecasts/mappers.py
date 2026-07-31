"""Bounded wire-shape mapper from ``PersistedForecastVersion`` rows to
``ForecastVersionResponse`` envelopes.

The repository owns the persisted row objects (SQLAlchemy).  The route
owns the JSON wire surface (``ForecastVersionResponse`` from
``app.forecasts.schemas``).  This module is the single translation
boundary between the two.

It is intentionally route-free and adapter-free: no FastAPI imports,
no DB session, no HTTP plumbing.  ``app.routes.forecasts_generation``
consumes it; tests consume it directly with synthetic fixtures.

Mapper invariants:

* ``ending_balance`` and ``target_gap`` come from the
  ``ForecastVersion`` Decimal columns (already quantized to 0.01
  ROUND_HALF_EVEN by the repository).  They are NEVER sourced from the
  output snapshot because the canonical rounded value is the
  persisted column.
* All four snapshot JSON columns roundtrip through ``json.loads``
  and are validated against the bounded wire schemas.
* ETag is derived from the merged codec (``api_codecs``) — never
  assembled here.
* HATEOAS rel names are bounded literal strings (not echoes of
  request data).
* Any malformed or missing source field raises
  ``ForecastMapperError`` with a sanitized token — NO raw payload
  bytes, NO ORM internals, NO financial values, NO request-derived
  strings in the error message.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Final

from app.forecasts.api_codecs import derive_forecast_etag
from app.forecasts.repository import PersistedForecastVersion
from app.forecasts.schemas import (
    AssumptionSnapshotSchema,
    DriversSnapshotSchema,
    ForecastLink,
    ForecastVersionResponse,
    OutputSnapshotSchema,
    ProvenanceSnapshotSchema,
    ScenarioSnapshotSchema,
    SnapshotMetaSchema,
    TargetDecisionV2Schema,
)


# Bounded rel names — literal constants, NEVER echoes of request data.
REL_SELF: Final[str] = "self"
REL_FORECAST: Final[str] = "forecast"
REL_GOAL: Final[str] = "goal"


_NULL_SENTINEL: Final[str] = "null"


class ForecastMapperError(ValueError):
    """Sanitized internal mapper error.  No raw bytes / field names leaked.

    The error string is a fixed token drawn from a small bounded set;
    it never contains input bytes, financial values, or arbitrary
    client data.  Callers must map this to a 503 envelope at the
    route boundary.
    """


def _as_utc_z(dt: datetime) -> str:
    """Serialize a parsed datetime as RFC 3339 Z (with microseconds)."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_decimal(value: Any) -> str:
    """Coerce *value* into the canonical decimal-string form.

    Accepts a ``Decimal``, an ``int``, or a ``str`` already in
    canonical form.  Raises :class:`ForecastMapperError` (sanitized)
    on any failure.
    """

    from app.forecasts.canonical_state import canonical_decimal_string
    try:
        if isinstance(value, Decimal):
            return canonical_decimal_string(value)
        if isinstance(value, int):
            return canonical_decimal_string(Decimal(value))
        return canonical_decimal_string(str(value))
    except Exception as exc:
        raise ForecastMapperError("snapshot_money_invalid") from exc


def _parse_snapshot_dict(label: str, raw: Any) -> dict[str, Any]:
    """Parse a snapshot JSON column to ``dict``; ``ForecastMapperError`` on any
    byte-level or shape failure."""

    if not isinstance(raw, str):
        raise ForecastMapperError(f"{label}_snapshot_invalid")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ForecastMapperError(f"{label}_snapshot_invalid") from exc
    if not isinstance(parsed, dict):
        raise ForecastMapperError(f"{label}_snapshot_invalid")
    return parsed


def _assumption_goal_pairs(goal_inputs: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Re-shape the persisted ``goal_inputs`` dict into bounded (name, str) tuples.

    The wire schema (``AssumptionSnapshotSchema.goal_inputs``) accepts
    only ``tuple[tuple[str, str], ...]`` with names drawn from
    ``{target_amount, horizon_years, target_date}``; the persisted
    snapshot additionally carries ``source_representation``,
    ``conversion``, ``precision_restored`` metadata that the wire
    contract drops.
    """

    out: list[tuple[str, str]] = []
    target_amount = goal_inputs.get("target_amount")
    if target_amount is None:
        raise ForecastMapperError("assumption_snapshot_invalid")
    out.append(("target_amount", _canonical_decimal(target_amount)))
    hy = goal_inputs.get("horizon_years")
    if hy is None:
        out.append(("horizon_years", _NULL_SENTINEL))
    elif isinstance(hy, bool) or not isinstance(hy, int):
        raise ForecastMapperError("assumption_snapshot_invalid")
    else:
        out.append(("horizon_years", str(hy)))
    td = goal_inputs.get("target_date")
    if td is None:
        out.append(("target_date", _NULL_SENTINEL))
    elif not isinstance(td, str):
        raise ForecastMapperError("assumption_snapshot_invalid")
    else:
        out.append(("target_date", td))
    return tuple(out)


def _build_assumption_snapshot(payload: dict[str, Any]) -> AssumptionSnapshotSchema:
    """Validate + re-shape the persisted assumption dict into the wire model."""

    required = {
        "assumption_schema_version", "assumption_profile", "annual_return_rates",
        "annual_inflation_rate", "contribution_timing", "period",
        "rounding_rule", "money_precision", "goal_inputs",
    }
    if set(payload) != required:
        raise ForecastMapperError("assumption_snapshot_invalid")

    rates_dict = payload.get("annual_return_rates")
    if not isinstance(rates_dict, dict) or set(rates_dict) != {"conservative", "base", "optimistic"}:
        raise ForecastMapperError("assumption_snapshot_invalid")
    rates_pairs: list[tuple[str, str]] = []
    for name in ("conservative", "base", "optimistic"):
        rates_pairs.append((name, _canonical_decimal(rates_dict[name])))

    goal_dict = payload.get("goal_inputs")
    if not isinstance(goal_dict, dict):
        raise ForecastMapperError("assumption_snapshot_invalid")
    goal_pairs = _assumption_goal_pairs(goal_dict)

    for key in ("contribution_timing", "period", "rounding_rule", "money_precision",
                "assumption_profile", "assumption_schema_version"):
        if key not in payload:
            raise ForecastMapperError("assumption_snapshot_invalid")
    return AssumptionSnapshotSchema(
        assumption_schema_version=payload["assumption_schema_version"],
        assumption_profile=str(payload["assumption_profile"]),
        annual_return_rates=tuple(rates_pairs),
        annual_inflation_rate=_canonical_decimal(payload["annual_inflation_rate"]),
        contribution_timing=payload["contribution_timing"],
        period=payload["period"],
        rounding_rule=payload["rounding_rule"],
        money_precision=payload["money_precision"],
        goal_inputs=goal_pairs,
    )


def _coerce_drivers_data_as_of(value: Any) -> str:
    """Coerce a persisted driver ``data_as_of`` into a RFC 3339 Z string.

    The persisted snapshot may carry a plain ISO date (``YYYY-MM-DD``)
    or a full RFC 3339 Z string; the wire schema requires the latter.
    Neither form is bounded to a maximum length over 64 chars.
    """

    if not isinstance(value, str):
        raise ForecastMapperError("output_snapshot_invalid")
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        # Plain YYYY-MM-DD — promote to a UTC midnight RFC 3339 Z string.
        iso_z = f"{value}T00:00:00.000000Z"
        if len(iso_z) > 64:
            raise ForecastMapperError("output_snapshot_invalid")
        return iso_z
    # Otherwise the value must already be RFC 3339 Z (the schema's
    # field validator will reject anything else on construction).
    return value


def _build_output_snapshot(payload: dict[str, Any]) -> OutputSnapshotSchema:
    """Validate + re-shape the persisted output dict into the wire model."""

    required = {"calculation_decimal_schema_version", "target_status", "target_decision", "drivers", "scenarios"}
    if set(payload) != required:
        raise ForecastMapperError("output_snapshot_invalid")

    decision_payload = payload.get("target_decision")
    if not isinstance(decision_payload, dict):
        raise ForecastMapperError("output_snapshot_invalid")
    decision = TargetDecisionV2Schema(**decision_payload)

    drivers_payload = payload.get("drivers")
    if not isinstance(drivers_payload, dict):
        raise ForecastMapperError("output_snapshot_invalid")
    drivers_dict = dict(drivers_payload)
    if "data_as_of" in drivers_dict:
        drivers_dict["data_as_of"] = _coerce_drivers_data_as_of(drivers_dict["data_as_of"])
    drivers = DriversSnapshotSchema(**drivers_dict)

    scenarios_payload = payload.get("scenarios")
    if not isinstance(scenarios_payload, dict):
        raise ForecastMapperError("output_snapshot_invalid")
    if set(scenarios_payload) != {"conservative", "base", "optimistic"}:
        raise ForecastMapperError("output_snapshot_invalid")
    scenarios_pairs = tuple(
        (name, ScenarioSnapshotSchema(**scenarios_payload[name]))
        for name in ("conservative", "base", "optimistic")
    )

    return OutputSnapshotSchema(
        calculation_decimal_schema_version=payload["calculation_decimal_schema_version"],
        target_status=bool(payload["target_status"]),
        target_decision=decision,
        drivers=drivers,
        scenarios=scenarios_pairs,
    )


def _build_provenance_snapshot(payload: dict[str, Any]) -> ProvenanceSnapshotSchema:
    """Validate + re-shape the persisted provenance dict into the wire model."""

    if set(payload) != {"provenance", "freshness"}:
        raise ForecastMapperError("provenance_snapshot_invalid")
    entries = payload.get("provenance")
    freshness = payload.get("freshness")
    if not isinstance(entries, list) or not isinstance(freshness, dict):
        raise ForecastMapperError("provenance_snapshot_invalid")
    return ProvenanceSnapshotSchema(
        provenance=tuple(dict(item) for item in entries if isinstance(item, dict)),
        freshness=dict(freshness),
    )


def _build_links(*, forecast_id: str, version_number: int, goal_id: int, base_url: str) -> tuple[ForecastLink, ...]:
    """Build deterministic HATEOAS links.  Rel names are literal
    constants; base URL is configuration-controlled (not request echo)."""

    base = base_url.rstrip("/")
    return (
        ForecastLink(rel=REL_SELF, href=f"{base}/api/v1/forecasts/{forecast_id}/versions/{version_number}"),
        ForecastLink(rel=REL_FORECAST, href=f"{base}/api/v1/forecasts/{forecast_id}"),
        ForecastLink(rel=REL_GOAL, href=f"{base}/api/goals/{goal_id}"),
    )


def build_forecast_version_response(
    persisted: PersistedForecastVersion,
    *,
    base_url: str,
) -> ForecastVersionResponse:
    """Translate the persisted SQL row + snapshot-JSON columns into the
    bounded wire envelope.  No DB session, no adapter invocation."""

    forecast = persisted.forecast
    version = persisted.version

    # Column-derived money — the canonical source-of-truth per the
    # repository's quantize step.  NEVER sourced from the snapshot.
    ending_balance = _canonical_decimal(version.ending_balance)
    target_gap = _canonical_decimal(version.target_gap)

    assumption_payload = _parse_snapshot_dict("assumption", version.assumption_snapshot_json)
    output_payload = _parse_snapshot_dict("output", version.output_snapshot_json)
    provenance_payload = _parse_snapshot_dict("provenance", version.provenance_snapshot_json)
    input_payload = _parse_snapshot_dict("input", version.input_snapshot_json)

    assumption_snapshot = _build_assumption_snapshot(assumption_payload)
    output_snapshot = _build_output_snapshot(output_payload)
    provenance_snapshot = _build_provenance_snapshot(provenance_payload)

    snapshot_meta = SnapshotMetaSchema(
        snapshot_schema_version=str(version.snapshot_schema_version),
        hash_schema_version=str(version.hash_schema_version),
        model_version=str(version.model_version),
        calculation_version=str(version.calculation_version),
    )

    links = _build_links(
        forecast_id=str(forecast.id),
        version_number=int(version.version_number),
        goal_id=int(forecast.goal_id),
        base_url=base_url,
    )

    etag = derive_forecast_etag(
        forecast_id=str(forecast.id),
        version_number=int(version.version_number),
    )

    return ForecastVersionResponse(
        forecast_id=str(forecast.id),
        version_id=str(version.id),
        version_number=int(version.version_number),
        etag=etag,
        input_state_hash=str(version.input_state_hash),
        idempotency_key_hash=str(version.idempotency_key_hash),
        snapshot=snapshot_meta,
        currency=str(version.currency),
        calculated_at=_as_utc_z(version.calculated_at),
        data_as_of=_as_utc_z(version.data_as_of),
        max_data_age_days=int(version.max_data_age_days),
        data_age_days=int(version.data_age_days),
        created_at=_as_utc_z(version.created_at),
        ending_balance=ending_balance,
        target_gap=target_gap,
        target_status=bool(output_snapshot.target_status),
        target_decision=output_snapshot.target_decision,
        drivers=output_snapshot.drivers,
        scenarios=output_snapshot,
        assumption_snapshot=assumption_snapshot,
        provenance_snapshot=provenance_snapshot,
        input_snapshot=input_payload,
        links=links,
    )
