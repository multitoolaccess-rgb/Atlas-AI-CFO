"""Default-off, owner-scoped Phase 4 decision-history API."""
from __future__ import annotations

import json
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.forecasts.decision_history_service import DecisionHistoryConflictError, DecisionHistoryNotFoundError, DecisionHistoryService, DecisionHistoryValidationError
from app.models import DecisionAuditEvent, OutcomeEvaluation, User
from app.routes.recommendations_derived import _get_db, _resolve_db_user_id

router = APIRouter(tags=["decision-history"], prefix="/api/v1")


def _disabled() -> JSONResponse:
    return JSONResponse(status_code=503, content={"code": "decision_history_unavailable", "message": "Decision history API is currently disabled."})


def _missing() -> JSONResponse:
    return JSONResponse(status_code=404, content={"code": "decision_history_not_found", "message": "Decision history not found."})


def _invalid() -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": [{"loc": ["body"], "type": "value_error.decision_history"}]})


async def _body(request: Request) -> dict | None:
    try:
        data = json.loads((await request.body()).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


@router.post("/goals/{goal_id}/decision-history", response_model=None, status_code=201)
async def record_history(request: Request, user_sub: Annotated[str, Depends(require_user)], db: Annotated[Session, Depends(_get_db)], goal_id: int = Path(gt=0), idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=255)) -> JSONResponse:
    if not settings.atlas_decision_history_api_enabled:
        return _disabled()
    payload = await _body(request)
    required = {"recommendation_id", "decision_journal_entry_id", "alternatives", "rationale"}
    allowed = required | {"supersedes_history_entry_id"}
    if payload is None or set(payload) - allowed or not required.issubset(payload) or idempotency_key is None:
        return _invalid()
    user_id = _resolve_db_user_id(db, user_sub)
    try:
        result = DecisionHistoryService(db).record(user_id=user_id, goal_id=goal_id, recommendation_id=payload["recommendation_id"], decision_journal_entry_id=payload["decision_journal_entry_id"], alternatives=payload["alternatives"], rationale=payload["rationale"], raw_idempotency_key=idempotency_key, supersedes_history_entry_id=payload.get("supersedes_history_entry_id"))
    except DecisionHistoryNotFoundError:
        return _missing()
    except DecisionHistoryConflictError:
        return JSONResponse(status_code=409, content={"code": "decision_history_conflict"})
    except (DecisionHistoryValidationError, TypeError):
        return _invalid()
    entry = result.entry
    return JSONResponse(status_code=201, content={"schema_version": "atlas-decision-history-envelope/v1", "history_id": entry.id, "decision_action": entry.decision_action, "recorded_at": entry.recorded_at.isoformat(), "replayed": result.replayed})


@router.get("/goals/{goal_id}/decision-history", response_model=None)
async def get_history(user_sub: Annotated[str, Depends(require_user)], db: Annotated[Session, Depends(_get_db)], goal_id: int = Path(gt=0)) -> JSONResponse:
    if not settings.atlas_decision_history_api_enabled:
        return _disabled()
    user_id = _resolve_db_user_id(db, user_sub)
    try:
        entries = DecisionHistoryService(db).list_for_goal(user_id=user_id, goal_id=goal_id)
    except DecisionHistoryNotFoundError:
        return _missing()
    history_ids = [entry.id for entry in entries]
    audits = {event.history_entry_id: event for event in db.scalars(select(DecisionAuditEvent).where(DecisionAuditEvent.user_id == user_id, DecisionAuditEvent.history_entry_id.in_(history_ids))) } if history_ids else {}
    decision_ids = [entry.decision_journal_entry_id for entry in entries]
    lifecycles: dict[str, list[str]] = {}
    if decision_ids:
        for outcome in db.scalars(select(OutcomeEvaluation).where(OutcomeEvaluation.user_id == user_id, OutcomeEvaluation.goal_id == goal_id, OutcomeEvaluation.decision_journal_entry_id.in_(decision_ids)).order_by(OutcomeEvaluation.recorded_at.asc())):
            lifecycles.setdefault(outcome.decision_journal_entry_id, []).append(outcome.lifecycle)
    rows = []
    for entry in entries:
        audit = audits.get(entry.id)
        rows.append({"history_id": entry.id, "recommendation_id": entry.recommendation_id, "decision_id": entry.decision_journal_entry_id, "decision_action": entry.decision_action, "alternatives": json.loads(entry.alternatives_json), "rationale": entry.rationale, "supersedes_history_id": entry.supersedes_history_entry_id, "recorded_at": entry.recorded_at.isoformat(), "audit": None if audit is None else {"event_action": audit.event_action, "actor_scope": audit.actor_scope, "policy_result": audit.policy_result, "occurred_at": audit.occurred_at.isoformat()}, "outcome_lifecycles": lifecycles.get(entry.decision_journal_entry_id, [])})
    return JSONResponse(status_code=200, content={"schema_version": "atlas-decision-history-envelope/v1", "history": rows})
