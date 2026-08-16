"""Versioned owner-scoped Scenario Lab API.

The route layer never accepts or returns authoritative canonical state, owner
IDs, provenance payloads, hashes supplied by clients, or result snapshots from
clients. All financial data is loaded through the trusted forecast adapter and
existing immutable forecast baseline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import SessionLocal
from app.forecast_provider.finlynq import HttpFinlynqProjectionStateAdapter
from app.models import Goal, Scenario, ScenarioVersion, User
from app.scenarios.contracts import ScenarioCompareRequest, ScenarioInput
from app.scenarios.repository import (
    ScenarioIdempotencyConflict,
    ScenarioNotFound,
    ScenarioRepository,
    ScenarioRepositoryConflict,
)
from app.scenarios.service import GeneratedScenario, ScenarioGenerationUnavailable, ScenarioInputValidationError, ScenarioService

router = APIRouter(tags=["scenarios"])


def _get_db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _user_id(db: Session, user_sub: str) -> int:
    row = db.scalar(select(User).where(User.local_user_sub == user_sub))
    if row is None:
        raise RuntimeError("authenticated user row not configured")
    return int(row.id)


def _error(code: str, message: str, status_code: int, *, loc: tuple[str | int, ...] | None = None) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message}
    if loc is not None:
        body["errors"] = [{"loc": list(loc), "type": "value_error.scenario"}]
    return JSONResponse(status_code=status_code, content=body)


def _parse_body(raw: bytes) -> ScenarioInput | JSONResponse:
    if not raw:
        return _error("scenario_validation_error", "Invalid scenario request.", 422, loc=("body",))
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        return ScenarioInput.model_validate(payload)
    except Exception:
        return _error("scenario_validation_error", "Invalid scenario request.", 422, loc=("body",))


def _parse_compare_body(raw: bytes) -> ScenarioCompareRequest | JSONResponse:
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        return ScenarioCompareRequest.model_validate(payload)
    except Exception:
        return _error("scenario_compare_validation_error", "Invalid scenario comparison request.", 422, loc=("body",))


def _adapter(request: Request):
    forwarded = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not forwarded:
        # Local UI authentication is carried by the already-validated
        # HttpOnly session cookie. Forward that token to Finlynq, never the
        # signing secret or any client-supplied financial state.
        forwarded = request.cookies.get("fc_session", "").strip()
    return HttpFinlynqProjectionStateAdapter(
        base_url=settings.finlynq_base_url,
        authorization=("Bearer " + forwarded) if forwarded else "",
    )


def _etag(scenario_id: str, version_number: int) -> str:
    return f'"{scenario_id}-v{version_number}"'


def _version_payload(row: Scenario, version: ScenarioVersion) -> dict[str, object]:
    try:
        input_snapshot = json.loads(version.input_snapshot_json)
        result_snapshot = json.loads(version.result_snapshot_json)
        comparison_snapshot = json.loads(version.comparison_snapshot_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise RuntimeError("scenario snapshot is invalid")
    return {
        "schema_version": "atlas-scenario-envelope/v1",
        "scenario_id": row.id,
        "version_id": version.id,
        "version_number": int(version.version_number),
        "goal_id": int(row.goal_id),
        "baseline_forecast_id": version.baseline_forecast_id,
        "baseline_version_number": int(version.baseline_version_number),
        "baseline_input_state_hash": version.baseline_input_state_hash,
        "scenario_input_hash": version.scenario_input_hash,
        "model_version": version.model_version,
        "calculation_version": version.calculation_version,
        "currency": version.currency,
        "lifecycle_state": row.lifecycle_state,
        "created_at": version.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if version.created_at else None,
        "input": input_snapshot,
        "result": result_snapshot,
        "comparison": comparison_snapshot,
        "recommendation_reference": version.recommendation_reference,
        "etag": _etag(str(row.id), int(version.version_number)),
    }


def _latest(db: Session, *, user_id: int, scenario_id: str) -> tuple[Scenario, ScenarioVersion] | None:
    row = db.scalar(select(Scenario).where(Scenario.id == scenario_id, Scenario.user_id == user_id))
    if row is None or int(row.latest_version_number) < 1:
        return None
    version = db.scalar(select(ScenarioVersion).where(ScenarioVersion.scenario_id == row.id, ScenarioVersion.version_number == row.latest_version_number))
    return None if version is None else (row, version)


@router.post("/api/v1/goals/{goal_id}/scenarios", response_model=None)
async def generate_scenario(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    goal_id: int = Path(ge=1),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255),
) -> JSONResponse:
    parsed = _parse_body(await request.body())
    if isinstance(parsed, JSONResponse):
        return parsed
    if idempotency_key is None:
        return _error("scenario_validation_error", "Invalid scenario request.", 422, loc=("header", "Idempotency-Key"))
    user_id = _user_id(db, user_sub)
    owned_goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id, Goal.is_archived.is_(False)))
    if owned_goal is None:
        return _error("scenario_not_found", "Scenario target not found.", 404)
    if parsed.scenario_id is not None:
        existing_scenario = db.get(Scenario, parsed.scenario_id)
        if existing_scenario is not None and (existing_scenario.user_id != user_id or existing_scenario.goal_id != goal_id):
            return _error("scenario_not_found", "Scenario target not found.", 404)
    if not settings.atlas_scenario_lab_enabled:
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    try:
        generated: GeneratedScenario = ScenarioService(db, _adapter(request)).generate(
            user_id=user_id,
            user_sub=user_sub,
            goal_id=goal_id,
            scenario_input=parsed,
            idempotency_key=idempotency_key,
            now=datetime.now(timezone.utc),
        )
    except ScenarioInputValidationError as exc:
        # Sanitized user-input failures (dates outside the projection horizon,
        # negative contribution, insufficient liquidity) are validation errors
        # with a precise recovery path, not availability failures.
        return _error("scenario_validation_error", str(exc), 422)
    except ScenarioGenerationUnavailable as exc:
        if str(exc) == "baseline_forecast_required":
            return _error("scenario_baseline_unavailable", "An immutable baseline forecast is required.", 409)
        if str(exc) == "baseline_is_stale":
            return _error("scenario_baseline_conflict", "The baseline forecast is no longer compatible.", 409)
        if str(exc) == "scenario_not_found":
            return _error("scenario_not_found", "Scenario target not found.", 404)
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    except ScenarioNotFound:
        return _error("scenario_not_found", "Scenario target not found.", 404)
    except ScenarioIdempotencyConflict:
        return _error("idempotency_conflict", "Idempotency-Key conflict.", 409)
    except ScenarioRepositoryConflict:
        return _error("scenario_conflict", "Scenario state conflict.", 409)
    payload = _version_payload(generated.persisted.scenario, generated.persisted.version)
    return JSONResponse(
        status_code=201 if generated.persisted.created else 200,
        content=payload,
        headers={"ETag": _etag(generated.persisted.scenario.id, generated.persisted.version.version_number)},
    )


@router.get("/api/v1/goals/{goal_id}/scenarios", response_model=None)
def list_scenarios(
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    goal_id: int = Path(ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, min_length=36, max_length=36),
    include_archived: bool = Query(default=False),
) -> JSONResponse:
    user_id = _user_id(db, user_sub)
    owned_goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id, Goal.is_archived.is_(False)))
    if owned_goal is None:
        return _error("scenario_not_found", "Scenario target not found.", 404)
    if not settings.atlas_scenario_lab_enabled:
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    query = select(Scenario).where(Scenario.user_id == user_id, Scenario.goal_id == goal_id)
    if not include_archived:
        query = query.where(Scenario.lifecycle_state == "active")
    if cursor:
        query = query.where(Scenario.id > cursor)
    rows = list(db.scalars(query.order_by(Scenario.id.asc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        latest = db.scalar(select(ScenarioVersion).where(ScenarioVersion.scenario_id == row.id, ScenarioVersion.version_number == row.latest_version_number))
        if latest is None:
            continue
        comparison = json.loads(latest.comparison_snapshot_json)
        items.append({
            "scenario_id": row.id,
            "goal_id": row.goal_id,
            "version_number": row.latest_version_number,
            "baseline_forecast_id": latest.baseline_forecast_id,
            "baseline_version_number": latest.baseline_version_number,
            "currency": row.currency,
            "lifecycle_state": row.lifecycle_state,
            "created_at": latest.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if latest.created_at else None,
            "ending_net_worth": comparison["ending_net_worth"],
            "difference_from_baseline": comparison["difference_from_baseline"],
            "target_reached": comparison["target_reached"],
        })
    return JSONResponse(status_code=200, content={"schema_version": "atlas-scenario-list/v1", "items": items, "next_cursor": rows[-1].id if has_more and rows else None})


@router.get("/api/v1/scenarios/{scenario_id}/versions/{version_number}", response_model=None)
def read_scenario_version(
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    scenario_id: str = Path(min_length=36, max_length=36),
    version_number: int = Path(ge=1),
) -> JSONResponse:
    user_id = _user_id(db, user_sub)
    row = db.scalar(select(Scenario).where(Scenario.id == scenario_id, Scenario.user_id == user_id))
    version = db.scalar(select(ScenarioVersion).where(ScenarioVersion.scenario_id == scenario_id, ScenarioVersion.version_number == version_number)) if row else None
    if row is None or version is None:
        return _error("scenario_not_found", "Scenario not found.", 404)
    if not settings.atlas_scenario_lab_enabled:
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    payload = _version_payload(row, version)
    return JSONResponse(status_code=200, content=payload, headers={"ETag": payload["etag"]})


@router.get("/api/v1/scenarios/{scenario_id}", response_model=None)
def read_scenario(
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    scenario_id: str = Path(min_length=36, max_length=36),
) -> JSONResponse:
    user_id = _user_id(db, user_sub)
    found = _latest(db, user_id=user_id, scenario_id=scenario_id)
    if found is None:
        return _error("scenario_not_found", "Scenario not found.", 404)
    if not settings.atlas_scenario_lab_enabled:
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    row, version = found
    payload = _version_payload(row, version)
    return JSONResponse(status_code=200, content=payload, headers={"ETag": payload["etag"]})


@router.get("/api/v1/scenarios/{scenario_id}/compare", response_model=None)
def compare_scenario(
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    scenario_id: str = Path(min_length=36, max_length=36),
) -> JSONResponse:
    user_id = _user_id(db, user_sub)
    found = _latest(db, user_id=user_id, scenario_id=scenario_id)
    if found is None:
        return _error("scenario_not_found", "Scenario not found.", 404)
    if not settings.atlas_scenario_lab_enabled:
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    row, version = found
    comparison = json.loads(version.comparison_snapshot_json)
    return JSONResponse(status_code=200, content={"schema_version": "atlas-scenario-comparison-envelope/v1", "scenario_id": row.id, "version_number": version.version_number, "comparison": comparison}, headers={"ETag": _etag(row.id, version.version_number)})


@router.post("/api/v1/scenarios/compare", response_model=None)
async def compare_saved_scenarios(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
) -> JSONResponse:
    parsed = _parse_compare_body(await request.body())
    if isinstance(parsed, JSONResponse):
        return parsed
    user_id = _user_id(db, user_sub)
    found = [_latest(db, user_id=user_id, scenario_id=scenario_id) for scenario_id in parsed.scenario_ids]
    if any(item is None for item in found):
        return _error("scenario_not_found", "Scenario not found.", 404)
    if not settings.atlas_scenario_lab_enabled:
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    typed = [item for item in found if item is not None]
    first_row, first_version = typed[0]
    compatible = all(
        row.goal_id == first_row.goal_id
        and version.baseline_forecast_id == first_version.baseline_forecast_id
        and version.baseline_version_number == first_version.baseline_version_number
        and version.baseline_input_state_hash == first_version.baseline_input_state_hash
        and version.currency == first_version.currency
        and version.model_version == first_version.model_version
        and version.calculation_version == first_version.calculation_version
        for row, version in typed[1:]
    )
    if not compatible:
        return _error("scenario_comparison_incompatible", "Scenarios are not compatible for comparison.", 409)
    return JSONResponse(status_code=200, content={"schema_version": "atlas-scenario-comparison-set/v1", "baseline_forecast_id": first_version.baseline_forecast_id, "baseline_version_number": first_version.baseline_version_number, "scenarios": [{"scenario_id": row.id, "version_number": version.version_number, "comparison": json.loads(version.comparison_snapshot_json)} for row, version in typed]})


@router.post("/api/v1/scenarios/{scenario_id}/archive", response_model=None)
def archive_scenario(
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    scenario_id: str = Path(min_length=36, max_length=36),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255),
) -> JSONResponse:
    if idempotency_key is None:
        return _error("scenario_validation_error", "Invalid scenario request.", 422, loc=("header", "Idempotency-Key"))
    user_id = _user_id(db, user_sub)
    if db.scalar(select(Scenario).where(Scenario.id == scenario_id, Scenario.user_id == user_id)) is None:
        return _error("scenario_not_found", "Scenario not found.", 404)
    if not settings.atlas_scenario_lab_enabled:
        return _error("scenario_generation_unavailable", "Scenario Lab is currently unavailable.", 503)
    try:
        archived = ScenarioRepository(db).archive(user_id=user_id, scenario_id=scenario_id, idempotency_key=idempotency_key)
    except ScenarioNotFound:
        return _error("scenario_not_found", "Scenario not found.", 404)
    except ScenarioIdempotencyConflict:
        return _error("idempotency_conflict", "Idempotency-Key conflict.", 409)
    return JSONResponse(status_code=200, content={"schema_version": "atlas-scenario-archive/v1", "scenario_id": archived.id, "lifecycle_state": archived.lifecycle_state, "archived_at": archived.archived_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if archived.archived_at and archived.archived_at.tzinfo else (archived.archived_at.isoformat() + "Z" if archived.archived_at else None)})
