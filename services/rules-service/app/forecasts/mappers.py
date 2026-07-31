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
# Deliberate bounded sentinel for an absent optional goal_inputs
# field (Phase 0 Goal model: every goal carries EITHER
# ``horizon_years`` (int years) OR ``target_date`` (ISO date string)
# — never both and never neither).  The wire schema accepts the
# literal string ``"null"`` as a structural placeholder so the
# tuple fields stay in 1-1 correspondence.  Callers MUST handle the
# sentinel case explicitly; it is NOT a missing field and MUST NOT
# be silently coerced by clients.


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

    Contract (Phase 0 Goal model — enforced here):

    * ``target_amount`` is REQUIRED.  ``None`` or missing →
      ``ForecastMapperError("assumption_snapshot_invalid")``.
    * EXACTLY ONE of ``horizon_years`` and ``target_date`` is
      present (a goal always carries a horizon via either an int
      number of years OR an ISO target date — never both, never
      neither).  All cases other than the XOR invariant →
      ``ForecastMapperError("assumption_snapshot_invalid")``.
    * When the absent optional field's value is ``None``, this
      mapper emits the bounded literal sentinel ``"null"`` (see
      ``_NULL_SENTINEL``).  This sentinel is a deliberate wire
      contract placeholder, NOT a missing field; clients MUST
      handle it explicitly.
    * ``horizon_years`` (when present) is a non-boolean ``int``.
    * ``target_date`` (when present) is a ``str``.

    The persisted snapshot may additionally carry
    ``source_representation``, ``conversion``, ``precision_restored``
    metadata that the wire contract drops.
    """

    target_amount = goal_inputs.get("target_amount")
    if target_amount is None:
        raise ForecastMapperError("assumption_snapshot_invalid")
    target_str = _canonical_decimal(target_amount)

    hy_raw = goal_inputs.get("horizon_years")
    td_raw = goal_inputs.get("target_date")
    has_horizon = hy_raw is not None
    has_target = td_raw is not None
    # XOR invariant — exactly one of (horizon_years, target_date).
    if has_horizon == has_target:
        raise ForecastMapperError("assumption_snapshot_invalid")

    if has_horizon:
        if isinstance(hy_raw, bool) or not isinstance(hy_raw, int):
            raise ForecastMapperError("assumption_snapshot_invalid")
        horizon_str = str(hy_raw)
    else:
        horizon_str = _NULL_SENTINEL

    if has_target:
        if not isinstance(td_raw, str):
            raise ForecastMapperError("assumption_snapshot_invalid")
        target_date_str = td_raw
    else:
        target_date_str = _NULL_SENTINEL

    return (
        ("target_amount", target_str),
        ("horizon_years", horizon_str),
        ("target_date", target_date_str),
    )


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

    Bounded accepted shapes (every other shape is rejected):

    * Plain ISO date ``YYYY-MM-DD`` (length 10, ``-`` separators at
      index 4 and 7) — promoted to ``YYYY-MM-DDT00:00:00.000000Z``.
    * Full RFC 3339 Z with the literal ``Z`` suffix and a ``T``
      separator (e.g. ``2026-07-01T12:34:56.789Z``) — passes through
      unchanged.

    Anything else (timezone offsets like ``+00:00`` / ``+02:00``,
    missing ``Z``, missing ``T``, non-strings, garbage strings,
    truncated dates) raises
    :class:`ForecastMapperError` (``"output_snapshot_invalid"``)
    so persistence cannot smuggle in ambiguous or non-UTC dates
    that the schema validator would later reject inconsistently.
    """

    if not isinstance(value, str):
        raise ForecastMapperError("output_snapshot_invalid")
    if len(value) > 64:
        raise ForecastMapperError("output_snapshot_invalid")
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        # Plain YYYY-MM-DD — promote to UTC midnight RFC 3339 Z.
        return f"{value}T00:00:00.000000Z"
    if "T" in value and value.endswith("Z"):
        # Full RFC 3339 Z — pass through.
        return value
    raise ForecastMapperError("output_snapshot_invalid")


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
