"""Read-only Phase 1 forecast routes (Slice D, ADR-006 §"API contract").

Four bounded GET handlers.  No PUT/PATCH/DELETE forecast or version route is
registered; the rules-service deliberately omits a mutable forecast CRUD
surface in favor of stable version-addressable history.

Routes
------

* ``GET /api/v1/forecasts``                              — cursor-paged list
* ``GET /api/v1/forecasts/{forecast_id}``                 — single forecast detail (304-on-equal-If-None-Match)
* ``GET /api/v1/forecasts/{forecast_id}/versions``       — cursor-paged versions
* ``GET /api/v1/forecasts/{forecast_id}/versions/{n}``    — single version detail (304-on-equal-If-None-Match)

Phase-1 invariants
------------------

* Every handler requires the JWT ``sub`` claim (single-user model).  Missing
  auth -> 401 via the standard FastAPI dependency.
* Every handler checks ``settings.atlas_forecast_read_api_enabled``;
  when off, the response is the canonical ``ReadApiDisabledEnvelope`` (503).
* Every forecast / version lookup filters by resolved ``user_id``; cross-user
  and missing-resource requests produce the SAME ``ForecastNotFoundEnvelope``
  body — there is no way for a client to distinguish them.
* ``If-None-Match`` is parsed against the merged codec and returns 304 with
  the ETag header on exact forecast-id + version-number match.
* ``If-Match`` is REJECTED on read routes (it is a write precondition).
  Sending it produces a sanitized 400 ``ValidationErrorEnvelope``.
* Collection GET endpoints reject BOTH ``If-Match`` and ``If-None-Match``;
  collections cannot return a single ETag (cursor pagination is what we have).
* ``Next_cursor`` round-trips through the merged codec for both lists; tampered
  cursors surface as 400.
* The routes intentionally do not import the canonical-state adapter or the
  projection module.  An import-graph assertion in the route test confirms
  this stays so.

Implementation note: FastAPI on the rules-service venv is ``0.104.1`` which
does not introspect ``Annotated[type, Path(...)]`` reliably.  We use the
older bare-parameter style (``path_arg: type = Path(...)``) which the rest
of the codebase uses.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import SessionLocal
from app.forecasts.api_codecs import (
    CodecError,
    decode_forecast_cursor,
    encode_forecast_cursor,
    format_forecast_etag_header,
    parse_forecast_etag_header,
)
from app.forecasts.repository import ForecastCursor, ForecastRepository
from app.forecasts.route_mapping import (
    InternalDataCorruption,
    forecast_to_response,
    version_to_response,
)
from app.forecasts.schemas import (
    ForecastListResponse,
    ForecastNotFoundEnvelope,
    ForecastResponse,
    ForecastVersionListResponse,
    ForecastVersionResponse,
    GoalNotFoundEnvelope,
    ReadApiDisabledEnvelope,
    ValidationErrorEnvelope,
    ValidationErrorEntry,
)
from app.models import Goal
from app.routes.shared import get_or_create_local_user


LOG = logging.getLogger("atlas.forecast.read")
router = APIRouter(prefix="/api/v1", tags=["forecasts"])


# ----------------------------------------------------------------------
# Dependencies
# ----------------------------------------------------------------------

def _db():
    """Per-request SQLAlchemy session; FastAPI uses the generator protocol."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resolve_user_id(db: Session, sub: str) -> int:
    """Resolve the JWT ``sub`` claim to the local user's integer PK.

    Single-user transitional scheme.  ``get_or_create_local_user`` is
    idempotent and auth-scoped (per Phase 7 of the rules service auth
    hardening), so this never silently creates a second row.
    """
    return get_or_create_local_user(db, sub).id


# ----------------------------------------------------------------------
# Sanitized response helpers (no Pydantic internals leak)
# ----------------------------------------------------------------------

def _read_disabled_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ReadApiDisabledEnvelope().model_dump(),
    )


def _validation_error_response(*, location: str, category: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ValidationErrorEnvelope(
            errors=(ValidationErrorEntry(loc=(location,), type=category),)
        ).model_dump(),
    )


def _forecast_not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ForecastNotFoundEnvelope().model_dump(),
    )


def _goal_not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=GoalNotFoundEnvelope().model_dump(),
    )


def _internal_data_corruption_response() -> JSONResponse:
    """Sanitized 500 envelope — no Pydantic ``loc`` / ``msg`` or stack trace."""
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_data_corruption",
            "message": "Forecast read failed safe-closed.",
        },
    )


def _internal_data_corruption_safe(handler: Callable) -> Callable:
    """Wrap a route handler so :class:`InternalDataCorruption` returns the
    sanitized 500 envelope instead of leaking Pydantic internals.
    """

    @wraps(handler)
    def wrapper(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except InternalDataCorruption as exc:
            LOG.warning(
                "forecast_read_internal_data_corruption path=%s reason=%s",
                handler.__name__,
                type(exc).__name__,
            )
            return _internal_data_corruption_response()

    return wrapper


def _sanitize_etag_header(header_value: Optional[str]) -> tuple[bool, Any]:
    """Return (is_malformed, parsed_or_none).  ``None`` means wildcard ``*``."""
    if not header_value:
        return False, None
    try:
        parsed = parse_forecast_etag_header(header_value)
    except CodecError:
        return True, None
    return False, parsed


# ----------------------------------------------------------------------
# Auth dependency that returns the integer user id (skip ``user_sub`` boilerplate)
# ----------------------------------------------------------------------

def _user_id_dep(db: Session = Depends(_db), sub: str = Depends(require_user)) -> int:
    return _resolve_user_id(db, sub)


# ----------------------------------------------------------------------
# GET /api/v1/forecasts
# ----------------------------------------------------------------------

@router.get(
    "/forecasts",
    response_model=ForecastListResponse,
)
@_internal_data_corruption_safe
def list_forecasts(
    *,
    user_id: int = Depends(_user_id_dep),
    goal_id: Optional[int] = Query(None, ge=1, le=9_223_372_036_854_775_807),
    cursor: Optional[str] = Query(None, max_length=256),
    limit: int = Query(32, ge=1, le=64),
    if_match: Optional[str] = Header(None, alias="If-Match"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    db: Session = Depends(_db),
):
    """Newest-first cursor-paged list of owned forecasts."""
    if not settings.atlas_forecast_read_api_enabled:
        return _read_disabled_response()
    if if_match is not None or if_none_match is not None:
        return _validation_error_response(
            location="If-Match",
            category="if-match-or-if-none-match-not-allowed-on-collection",
        )

    parsed_cursor: Optional[ForecastCursor] = None
    if cursor:
        try:
            parsed_cursor = decode_forecast_cursor(cursor)
        except CodecError:
            return _validation_error_response(location="cursor", category="value_error")

    if goal_id is not None:
        goal = db.scalar(
            select(Goal).where(
                Goal.id == goal_id,
                Goal.user_id == user_id,
                Goal.is_archived.is_(False),
            )
        )
        if goal is None:
            return _goal_not_found_response()

    repo = ForecastRepository(db)
    pairs, next_cursor = repo.list_forecasts_paginated(
        user_id=user_id,
        goal_id=goal_id,
        cursor=parsed_cursor,
        limit=limit,
    )
    items = tuple(
        forecast_to_response(forecast=fc, latest_version=lv)
        for fc, lv in pairs
        if lv is not None
    )
    next_cursor_str: Optional[str] = None
    if next_cursor is not None:
        next_cursor_str = encode_forecast_cursor(
            forecast_id=next_cursor.forecast_id,
            created_at=next_cursor.created_at,
            version_number=next_cursor.version_number,
        )
    LOG.info(
        "forecast_list user_id=%s goal_id=%s limit=%d returned=%d has_next=%s",
        user_id,
        goal_id if goal_id is not None else "-",
        limit,
        len(items),
        "yes" if next_cursor_str is not None else "no",
    )
    return ForecastListResponse(items=items, next_cursor=next_cursor_str)


# ----------------------------------------------------------------------
# GET /api/v1/forecasts/{forecast_id}
# ----------------------------------------------------------------------

@router.get(
    "/forecasts/{forecast_id}",
    response_model=ForecastResponse,
)
@_internal_data_corruption_safe
def get_forecast(
    *,
    user_id: int = Depends(_user_id_dep),
    forecast_id: str = Path(..., min_length=36, max_length=36),
    if_match: Optional[str] = Header(None, alias="If-Match"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    db: Session = Depends(_db),
):
    """Single forecast detail.  Returns 304 when ``If-None-Match`` matches."""
    if not settings.atlas_forecast_read_api_enabled:
        return _read_disabled_response()
    if if_match is not None:
        return _validation_error_response(
            location="If-Match",
            category="If-Match is a write precondition; not accepted on read routes",
        )
    malformed_if_none, parsed_if_none = _sanitize_etag_header(if_none_match)
    if malformed_if_none:
        return _validation_error_response(
            location="If-None-Match", category="value_error"
        )
    repo = ForecastRepository(db)
    pair = repo.get_forecast_for_user(user_id=user_id, forecast_id=forecast_id)
    if pair is None:
        return _forecast_not_found_response()
    forecast, latest = pair
    if latest is None:
        return _internal_data_corruption_response()
    etag_quoted = format_forecast_etag_header(
        forecast_id=forecast.id, version_number=latest.version_number
    )
    if parsed_if_none is not None:
        if (
            parsed_if_none.forecast_id == forecast.id
            and parsed_if_none.version_number == latest.version_number
        ):
            return Response(
                status_code=304,
                headers={"ETag": etag_quoted},
            )
    response = forecast_to_response(forecast=forecast, latest_version=latest)
    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=200,
        headers={"ETag": etag_quoted},
    )


# ----------------------------------------------------------------------
# GET /api/v1/forecasts/{forecast_id}/versions
# ----------------------------------------------------------------------

@router.get(
    "/forecasts/{forecast_id}/versions",
    response_model=ForecastVersionListResponse,
)
@_internal_data_corruption_safe
def list_forecast_versions(
    *,
    user_id: int = Depends(_user_id_dep),
    forecast_id: str = Path(..., min_length=36, max_length=36),
    cursor: Optional[str] = Query(None, max_length=256),
    limit: int = Query(32, ge=1, le=64),
    if_match: Optional[str] = Header(None, alias="If-Match"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    db: Session = Depends(_db),
):
    if not settings.atlas_forecast_read_api_enabled:
        return _read_disabled_response()
    if if_match is not None or if_none_match is not None:
        return _validation_error_response(
            location="If-Match",
            category="if-match-or-if-none-match-not-allowed-on-version-collection",
        )
    parsed_cursor: Optional[ForecastCursor] = None
    if cursor:
        try:
            parsed_cursor = decode_forecast_cursor(cursor)
        except CodecError:
            return _validation_error_response(location="cursor", category="value_error")

    repo = ForecastRepository(db)
    pair = repo.list_forecast_versions_paginated(
        user_id=user_id,
        forecast_id=forecast_id,
        cursor=parsed_cursor,
        limit=limit,
    )
    if pair is None:
        return _forecast_not_found_response()
    versions, next_cursor = pair
    items = tuple(
        version_to_response(forecast_id=forecast_id, version=v) for v in versions
    )
    next_cursor_str: Optional[str] = None
    if next_cursor is not None:
        next_cursor_str = encode_forecast_cursor(
            forecast_id=next_cursor.forecast_id,
            created_at=next_cursor.created_at,
            version_number=next_cursor.version_number,
        )
    LOG.info(
        "forecast_versions_list user_id=%s forecast_id=%s limit=%d returned=%d has_next=%s",
        user_id,
        forecast_id,
        limit,
        len(items),
        "yes" if next_cursor_str is not None else "no",
    )
    return ForecastVersionListResponse(items=items, next_cursor=next_cursor_str)


# ----------------------------------------------------------------------
# GET /api/v1/forecasts/{forecast_id}/versions/{version_number}
# ----------------------------------------------------------------------

@router.get(
    "/forecasts/{forecast_id}/versions/{version_number}",
    response_model=ForecastVersionResponse,
)
@_internal_data_corruption_safe
def get_forecast_version(
    *,
    user_id: int = Depends(_user_id_dep),
    forecast_id: str = Path(..., min_length=36, max_length=36),
    version_number: int = Path(..., ge=1, le=9_999_999_999),
    if_match: Optional[str] = Header(None, alias="If-Match"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    db: Session = Depends(_db),
):
    if not settings.atlas_forecast_read_api_enabled:
        return _read_disabled_response()
    if if_match is not None:
        return _validation_error_response(
            location="If-Match",
            category="If-Match is a write precondition; not accepted on read routes",
        )
    malformed_if_none, parsed_if_none = _sanitize_etag_header(if_none_match)
    if malformed_if_none:
        return _validation_error_response(
            location="If-None-Match", category="value_error"
        )

    repo = ForecastRepository(db)
    pair = repo.get_forecast_version_for_user(
        user_id=user_id,
        forecast_id=forecast_id,
        version_number=version_number,
    )
    if pair is None:
        return _forecast_not_found_response()
    forecast, version = pair
    etag_quoted = format_forecast_etag_header(
        forecast_id=forecast.id, version_number=version.version_number
    )
    if parsed_if_none is not None:
        if (
            parsed_if_none.forecast_id == forecast.id
            and parsed_if_none.version_number == version.version_number
        ):
            return Response(
                status_code=304,
                headers={"ETag": etag_quoted},
            )
    response = version_to_response(forecast_id=forecast.id, version=version)
    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=200,
        headers={"ETag": etag_quoted},
    )


# ----------------------------------------------------------------------
# Adapter-bypass belt-and-braces (defence-in-depth)
# ----------------------------------------------------------------------
# Importing this router intentionally avoids any path that would pull in the
# canonical-state adapter or the projection.  The route-test asserts via
# ``inspect`` that ``app.routes.forecasts`` does NOT reference
# ``app.forecasts.canonical_state`` or ``app.calculations.projection`` in
# its module globals.  Keeping this comment as the explicit contract so a
# future refactor that widens the import list fails the assertion.
