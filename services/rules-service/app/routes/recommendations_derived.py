"""Phase 2 Slice 1 commit-4 routes.

Bounded authenticated routes that expose the deterministic
recommendation DERIVATION read and the append-only DECISION
write. Re-uses the Phase 1 read-API gate (``Settings.atlas_
forecast_read_api_enabled``) per the approved plan §8 ("no new flag
introduced"). NO client-side override; NO mutable forecast CRUD;
NO mutable journal CRUD; NO autonomous execution.

This is the only entry that mutates the immutable Phase 2
recommendation + decision-journal ledgers; the Phase 1 forecast
generation + read routes are untouched.

Errors and logs never expose: financial values, full Idempotency-
Key (only its SHA-256 hash), source-state payloads, configuration
values, the user sub, the goal id, the recommendation id, the
journal entry id, or any ORM attribute.
"""
from __future__ import annotations

import json as _json
from typing import Annotated, Final, Optional

from fastapi import APIRouter, Depends, Header, Path, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import SessionLocal
from app.forecasts.api_codecs import format_decision_etag_header
from app.forecasts.canonical_state import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    validate_idempotency_key,
)
from app.forecasts.decision_journal_service import (
    DecisionConflictError,
    DecisionJournalService,
    GoalNotFoundError as JournalGoalNotFoundError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyRequiredError,
    RecommendationNotFoundError as JournalRecommendationNotFoundError,
)
from app.forecasts.recommendation_repository import (
    DerivationFailure,
    ForecastVersionCurrencyInvalid,
    ForecastVersionNotFoundError,
    GoalNotFoundError as RepoGoalNotFoundError,
    RecommendationRepository,
)
from app.forecasts.recommendation_schemas import (
    DecisionConflictEnvelope,
    DecisionJournalSubmitRequest,
    RecommendationNotFoundEnvelope,
)
from app.forecasts.recommendations import (
    build_journal_entry_envelope,
    build_recommendation_envelope,
)
from app.forecasts.schemas import ValidationErrorEntry, ValidationErrorEnvelope
from app.models import Forecast, ForecastVersion, Recommendation, User


router = APIRouter(tags=["recommendations"], prefix="/api/v1")

# Phase 2 deterministic kind default.  Branch logic to other kinds
# (``increase_contribution``, ``rebalance_allocation``, ``extend_horizon``)
# can layer in a follow-up slice without breaking the wire contract
# because the deterministic canonical inputs include the kind itself
# and idempotent replay collapses onto the same row.
_DEFAULT_KIND: Final[str] = "hold"
_DEFAULT_RULE_VERSION: Final[str] = "v1.0"
_DEFAULT_DERIVATION_SCHEMA_VERSION: Final[str] = "atlas-recommendation/v1"


# ----------------------------------------------------------------------
# DB dependency (mirrors forecasts_generation.py)
# ----------------------------------------------------------------------

def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resolve_db_user_id(db: Session, user_sub: str) -> int:
    """Translate the JWT ``sub`` claim to a stable integer ``users.id``.

    Single-user model: the JWT subject is ``settings.local_user``;
    the corresponding ``users`` row is created on first encounter so
    cross-table integer FKs are always satisfiable for the projection
    pipeline.
    """
    user = db.scalar(select(User).where(User.local_user_sub == user_sub))
    if user is None:
        user = User(
            local_user_sub=user_sub,
            email=f"{user_sub}@local",
            hashed_password="x",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return int(user.id)


# ----------------------------------------------------------------------
# Bounded sanitized JSON response helpers
# ----------------------------------------------------------------------

def _disabled_response() -> JSONResponse:
    """503 envelope: re-uses the Phase 1 ``ReadApiDisabledEnvelope``
    shape so the UI state-tree for ``atlas_forecast_read_api_enabled``
    remains uniform across forecast reads AND recommendation/journal.
    """
    envelope = {
        "code": "forecast_read_api_unavailable",
        "message": "Forecast read API is currently disabled.",
    }
    return JSONResponse(status_code=503, content=envelope)


def _recommendation_not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=RecommendationNotFoundEnvelope().model_dump(),
    )


def _decision_conflict_response(*, current_etag: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=DecisionConflictEnvelope(current_etag=current_etag).model_dump(),
    )


def _validation_error_response(*, loc: tuple[str | int, ...], type_: str) -> JSONResponse:
    entry = ValidationErrorEntry(loc=loc, type=type_)
    return JSONResponse(
        status_code=422,
        content=ValidationErrorEnvelope(errors=[entry]).model_dump(),
    )


# ----------------------------------------------------------------------
# Route 1: GET /api/v1/forecasts/{forecast_id}/recommendation
# ----------------------------------------------------------------------

@router.get(
    "/forecasts/{forecast_id}/recommendation",
    status_code=status.HTTP_200_OK,
    response_model=None,
)
async def get_recommendation_for_forecast(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    forecast_id: str = Path(min_length=1, max_length=36),
) -> JSONResponse:
    """Return the deterministic ``DeterministicRecommendationEnvelope``
    for the latest forecast-version under ``forecast_id``.

    Idempotent-replay: identical canonical inputs collapse onto the
    same recommendation row, so subsequent GETs return the same
    envelope without creating a new row.
    """
    if not settings.atlas_forecast_read_api_enabled:
        return _disabled_response()

    user_id = _resolve_db_user_id(db, user_sub)

    forecast = db.get(Forecast, forecast_id)
    if forecast is None or int(forecast.user_id) != user_id:
        # Same envelope for missing AND cross-user for indistinguishability.
        return _recommendation_not_found_response()

    latest_version = db.scalar(
        select(ForecastVersion)
        .where(ForecastVersion.forecast_id == forecast_id)
        .order_by(ForecastVersion.version_number.desc())
        .limit(1)
    )
    if latest_version is None:
        return _recommendation_not_found_response()

    repo = RecommendationRepository(db)
    try:
        result = repo.persist(
            user_id=user_id,
            goal_id=int(forecast.goal_id),
            forecast_version_id=str(latest_version.id),
            recommendation_kind=_DEFAULT_KIND,
            rule_version=_DEFAULT_RULE_VERSION,
            derivation_schema_version=_DEFAULT_DERIVATION_SCHEMA_VERSION,
        )
    except (RepoGoalNotFoundError, ForecastVersionNotFoundError):
        return _recommendation_not_found_response()
    except ForecastVersionCurrencyInvalid:
        return _validation_error_response(
            loc=("path", "forecast_id"), type_="value_error.currency"
        )
    except DerivationFailure:
        return _validation_error_response(
            loc=("path", "forecast_id"), type_="value_error.derivation"
        )

    envelope = build_recommendation_envelope(
        recommendation=result.recommendation,
        forecast_id=forecast_id,
        forecast_version_model_version=str(latest_version.model_version),
        forecast_version_calculation_version=str(latest_version.calculation_version),
        forecast_version_input_state_hash=str(latest_version.input_state_hash),
        forecast_version_data_as_of=latest_version.data_as_of,
        forecast_version_number=int(latest_version.version_number),
    )
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(),
        headers={
            "ETag": format_decision_etag_header(
                source_id=result.recommendation.id, version=1
            ),
        },
    )


# ----------------------------------------------------------------------
# Route 2: POST /api/v1/recommendations/{recommendation_id}/decisions
# ----------------------------------------------------------------------

@router.post(
    "/recommendations/{recommendation_id}/decisions",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
)
async def post_decision_journal_entry(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    recommendation_id: str = Path(min_length=1, max_length=36),
    # Pattern D (classic style) — REQUIRED to simultaneously avoid:
    #   (a) FastAPI 0.104.1 FieldInfo.in_ leak when Annotated[X, Header(...)] = None
    #   (b) Pydantic 2.x AssertionError when Annotated[X, Header(..., default=None)] = None
    idempotency_key_value: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
    ),
) -> JSONResponse:
    """Append one decision-journal row for an owned recommendation.

    Idempotent-replay: identical (raw Idempotency-Key + canonical
    payload) collapses onto the same row, so a client retry sees an
    identical 201 envelope (``replayed=True``) without a second row.

    Cross-row conflict: same Idempotency-Key + different payload
    returns 409 ``DecisionConflictEnvelope.code=decision_version_conflict``
    carrying only the bare server-derived current ``decision_etag``.
    """
    if not settings.atlas_forecast_read_api_enabled:
        return _disabled_response()

    if idempotency_key_value is None:
        return _validation_error_response(
            loc=("header", "Idempotency-Key"), type_="value_error.missing"
        )
    try:
        validate_idempotency_key(idempotency_key_value)
    except Exception:
        return _validation_error_response(
            loc=("header", "Idempotency-Key"), type_="value_error.idempotency_key"
        )

    raw_body = await request.body()
    if not raw_body:
        return _validation_error_response(
            loc=("body",), type_="value_error.required"
        )
    try:
        parsed_body = _json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _validation_error_response(
            loc=("body",), type_="value_error.jsondecode"
        )
    if not isinstance(parsed_body, dict):
        return _validation_error_response(
            loc=("body",), type_="value_error.dict_expected"
        )
    try:
        submit = DecisionJournalSubmitRequest.model_validate(parsed_body)
    except Exception:
        return _validation_error_response(
            loc=("body",), type_="value_error"
        )

    user_id = _resolve_db_user_id(db, user_sub)

    recommendation_row = db.get(Recommendation, recommendation_id)
    if recommendation_row is None or int(recommendation_row.user_id) != user_id:
        # Same envelope for missing AND cross-user for indistinguishability.
        return _recommendation_not_found_response()

    journal_service = DecisionJournalService(db)
    try:
        journal_result = journal_service.record(
            user_id=user_id,
            goal_id=int(recommendation_row.goal_id),
            recommendation_id=recommendation_id,
            decision_action=submit.action,
            raw_idempotency_key=idempotency_key_value,
            schema_version="atlas-decision-journal-entry/v1",
        )
    except (JournalGoalNotFoundError, JournalRecommendationNotFoundError):
        return _recommendation_not_found_response()
    except DecisionConflictError as exc:
        return _decision_conflict_response(current_etag=str(exc.current_etag))
    except (IdempotencyKeyRequiredError, IdempotencyKeyInvalidError):
        return _validation_error_response(
            loc=("header", "Idempotency-Key"), type_="value_error.idempotency_key"
        )

    envelope = build_journal_entry_envelope(journal_entry=journal_result.entry)
    return JSONResponse(
        status_code=201,
        content=envelope.model_dump(),
        headers={
            "Location": f"/api/v1/decisions/{journal_result.entry.id}",
            "ETag": format_decision_etag_header(
                source_id=journal_result.entry.id, version=1
            ),
        },
    )
