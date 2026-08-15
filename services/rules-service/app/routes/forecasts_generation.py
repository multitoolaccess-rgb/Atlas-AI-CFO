"""Authenticated forecast generation POST route.

Bounded slice that posts one forecast version for an owned goal or
replays an idempotent existing one.  Slice D-post is the only entry
that mutates the immutable forecast ledger; the four Slice D versioned
read endpoints and Slice A/B/C are untouched.

The route enforces, in order:

1. Authenticated user scope (``Depends(require_user)`` returns sub).
2. ``Idempotency-Key`` header presence + bounded ASCII validation
   (the canonical 1-255 visible-ASCII rule from
   ``app.forecasts.canonical_state.validate_idempotency_key``).
3. Conditional-header semantics (``If-None-Match: *`` mandatory on
   initial creation; ``If-Match`` for observed forecasts) with the
   full 9-case status matrix.
4. Goal ownership BEFORE any adapter invocation — cross-user and
   missing goals return the SAME indistinguishable 404
   ``GoalNotFoundEnvelope`` (non-disclosing).
5. Persistence-gate check (settings flag) — disabled returns 503
   ``ForecastGenerationDisabledEnvelope``.
6. Adapter + service invocation.  Service returns
   ``GeneratedForecast(persisted, created)``.
7. 201 (new creation) / 200 (idempotent replay), ``Location``,
   quoted ``ETag``, deterministic HATEOAS links.

Logging and errors never expose: financial values, full idempotency
key (only its SHA-256 hash), source state payloads, configuration
values, the user sub, the goal id, or any internal ORM attribute.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Final, Optional  # Annotated is still used by the Depends-style type hints on user_sub / db

from fastapi import APIRouter, Depends, Header, Path, Request, status  # Body + HTTPException removed (unused)
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import SessionLocal
from app.forecasts.api_codecs import (
    derive_forecast_etag,
    format_forecast_etag_header,
    parse_forecast_etag_header,
)
from app.forecasts.canonical_state import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    validate_idempotency_key,
)  # FinlynqProjectionStateAdapter removed (unused)
from app.forecasts.mappers import build_forecast_version_response
from app.forecasts.repository import (
    IdempotencyConflict,
    PersistedForecastVersion,
    StaleForecastVersion,
)  # ForecastRepository removed (unused)
from app.forecasts.schemas import (
    ERROR_CODE_BAD_REQUEST,
    BadRequestEnvelope,
    ForecastGenerationDisabledEnvelope,
    ForecastNotFoundEnvelope,
    ForecastVersionConflictEnvelope,
    GenerationRequestEnvelope,
    GoalNotFoundEnvelope,
    IdempotencyConflictEnvelope,
    PreconditionFailedEnvelope,
    ReadApiDisabledEnvelope,
    ValidationErrorEntry,
    ValidationErrorEnvelope,
)
from app.forecasts.service import (
    ForecastGenerationService,
    ForecastGenerationUnavailable,
)
from app.forecast_provider.finlynq import HttpFinlynqProjectionStateAdapter
from app.models import Forecast, ForecastVersion, Goal, User


router = APIRouter(tags=["forecasts"])


_MAX_LOCATION_LEN: Final[int] = 512


# ----------------------------------------------------------------------
# Sanitized envelope builders
# ----------------------------------------------------------------------


def _validation_error(
    *,
    loc: tuple[str | int, ...],
    type_: str,
    status_code: int = 422,
    extra_entries: tuple[ValidationErrorEntry, ...] = (),
) -> JSONResponse:
    """Build a sanitized ValidationErrorEnvelope-shaped 422 response."""

    entries: list[ValidationErrorEntry] = [ValidationErrorEntry(loc=loc, type=type_)]
    entries.extend(extra_entries)
    return JSONResponse(
        status_code=status_code,
        content=ValidationErrorEnvelope(errors=tuple(entries)).model_dump(),
    )


def _bad_request(loc: tuple[str | int, ...], type_: str) -> JSONResponse:
    """400 envelope for malformed conditional headers."""

    entries = (ValidationErrorEntry(loc=loc, type=type_),)
    return JSONResponse(
        status_code=400,
        content=BadRequestEnvelope(
            code=ERROR_CODE_BAD_REQUEST,
            errors=entries,
        ).model_dump(),
    )


def _goal_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=GoalNotFoundEnvelope().model_dump(),
    )


def _precondition_failed() -> JSONResponse:
    return JSONResponse(
        status_code=412,
        content=PreconditionFailedEnvelope().model_dump(),
    )


def _version_conflict(*, current_etag: str, latest_version_number: int) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ForecastVersionConflictEnvelope(
            current_etag=current_etag,
            latest_version_number=latest_version_number,
        ).model_dump(),
    )


def _idempotency_conflict() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=IdempotencyConflictEnvelope().model_dump(),
    )


def _generation_disabled() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ForecastGenerationDisabledEnvelope().model_dump(),
    )


# ----------------------------------------------------------------------
# Dependencies
# ----------------------------------------------------------------------


def _get_db() -> Session:
    """Yield a per-request SQLAlchemy session.

    Same pattern as the existing Slice D read-route module —
    the session is closed on request teardown regardless of
    whether the response succeeded or raised.
    """

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _resolve_user_sub_to_id(db: Session, user_sub: str) -> int:
    """Map ``user_sub`` (JWT claim) to ``users.id`` row id.

    Raises ``RuntimeError`` (mapped to 500 by the existing global
    exception handler) when the configuration is broken — never
    silently masks the missing row as a 404 / 503 / 409.
    """

    row = db.scalar(select(User).where(User.local_user_sub == user_sub))
    if row is None:
        raise RuntimeError("authenticated user row not configured")
    return int(row.id)


def _load_owned_goal(db: Session, *, goal_id: int, user_id: int) -> Optional[Goal]:
    """Return the owned + unarchived goal, or ``None`` (cross-user + missing are indistinguishable)."""

    return db.scalar(
        select(Goal).where(
            Goal.id == int(goal_id),
            Goal.user_id == int(user_id),
            Goal.is_archived.is_(False),
        )
    )


def _existing_forecast_for_user_goal(db: Session, *, user_id: int, goal_id: int) -> Optional[Forecast]:
    """Return the invariant forecast row for a (user, goal) tuple, or ``None`` if absent."""

    return db.scalar(
        select(Forecast).where(
            Forecast.user_id == int(user_id),
            Forecast.goal_id == int(goal_id),
        )
    )


# ----------------------------------------------------------------------
# Authenticated immutable forecast reads
# ----------------------------------------------------------------------


def _forecast_read_disabled() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ReadApiDisabledEnvelope().model_dump(),
    )


def _forecast_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ForecastNotFoundEnvelope().model_dump(),
    )


def _read_forecast_version(
    request: Request,
    db: Session,
    *,
    user_sub: str,
    forecast_id: str,
    version_number: int | None,
) -> JSONResponse:
    """Read one owner-scoped immutable version through the canonical mapper."""
    if not settings.atlas_forecast_read_api_enabled:
        return _forecast_read_disabled()

    user_id = _resolve_user_sub_to_id(db, user_sub)
    forecast = db.scalar(
        select(Forecast).where(
            Forecast.id == forecast_id,
            Forecast.user_id == user_id,
            Forecast.forecast_kind == "goal_projection",
            Forecast.currency == "USD",
        )
    )
    if forecast is None:
        return _forecast_not_found()

    version_query = select(ForecastVersion).where(ForecastVersion.forecast_id == forecast.id)
    if version_number is not None:
        version_query = version_query.where(ForecastVersion.version_number == version_number)
    else:
        version_query = version_query.order_by(ForecastVersion.version_number.desc()).limit(1)
    version = db.scalar(version_query)
    if version is None:
        return _forecast_not_found()

    envelope = build_forecast_version_response(
        PersistedForecastVersion(
            forecast=forecast,
            version=version,
            created=False,
            input_snapshot_json=version.input_snapshot_json,
        ),
        base_url=str(request.base_url).rstrip("/"),
    )
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(),
        headers={"ETag": format_forecast_etag_header(
            forecast_id=str(forecast.id),
            version_number=int(version.version_number),
        )},
    )


@router.get("/api/v1/forecasts/{forecast_id}", response_model=None)
async def read_latest_forecast(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    forecast_id: str = Path(min_length=1, max_length=36),
) -> JSONResponse:
    return _read_forecast_version(
        request, db, user_sub=user_sub, forecast_id=forecast_id, version_number=None,
    )


@router.get("/api/v1/forecasts/{forecast_id}/versions/{version_number}", response_model=None)
async def read_forecast_version(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    forecast_id: str = Path(min_length=1, max_length=36),
    version_number: int = Path(ge=1),
) -> JSONResponse:
    return _read_forecast_version(
        request, db, user_sub=user_sub, forecast_id=forecast_id, version_number=version_number,
    )


# ----------------------------------------------------------------------
# POST /api/v1/goals/{goal_id}/forecasts
# ----------------------------------------------------------------------


@router.post(
    "/api/v1/goals/{goal_id}/forecasts",
    status_code=status.HTTP_201_CREATED,
    response_model=None,  # JSONResponse returned; envelope is validated in the handler
    responses={
        200: {"model": None, "description": "Idempotent replay or matched conditional create."},
        201: {"model": None, "description": "Successfully generated a new immutable forecast version."},
        400: {"model": BadRequestEnvelope},
        404: {"model": GoalNotFoundEnvelope},
        409: {"model": ForecastVersionConflictEnvelope},
        412: {"model": PreconditionFailedEnvelope},
        422: {"model": ValidationErrorEnvelope},
        503: {"model": ForecastGenerationDisabledEnvelope},
    },
)
async def generate_forecast_for_goal(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    goal_id: int = Path(ge=1),
    # Pattern D (classic style) — REQUIRED to simultaneously avoid:
    #   (a) FastAPI 0.104.1 FieldInfo.in_ leak when Annotated[X, Header(...)] = None
    #   (b) Pydantic 2.x AssertionError when Annotated[X, Header(..., default=None)] = None
    # Both Annotated-style options fail in this fastapi+pydantic combo. The classic
    # style bypasses Annotated/X metadata entirely; FastAPI gets a taint-free
    # ``fastapi.params.Header`` instance with the native ``.in_`` attribute, and
    # pydantic's metadata-default constraint never engages (no Annotated wrapper).
    idempotency_key_value: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=MAX_IDEMPOTENCY_KEY_LENGTH),
    if_match_value: Optional[str] = Header(default=None, alias="If-Match", max_length=96),
    if_none_match_value: Optional[str] = Header(default=None, alias="If-None-Match", max_length=96),
) -> JSONResponse:
    """Generate or replay an immutable forecast version for one owned goal.

    See module docstring for the ordered invariants.
    """

    # ---------- Step 0: Hand-validate the optional JSON body ----------
    # The body is intentionally hand-validated (NOT a typed FastAPI
    # parameter) so we keep tight control over the empty-body /
    # unknown-field contract: ``extra="forbid"`` rejects unknown fields
    # but a missing body or an empty ``{}`` is accepted.
    raw_body = await request.body()
    if raw_body:
        try:
            import json as _json
            parsed_body = _json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _validation_error(
                loc=("body",),
                type_="value_error.jsondecode",
            )
        if not isinstance(parsed_body, dict):
            return _validation_error(
                loc=("body",),
                type_="value_error.dict_expected",
            )
        try:
            GenerationRequestEnvelope.model_validate(parsed_body)
        except Exception:
            return _validation_error(
                loc=("body",),
                type_="value_error.extra_forbidden",
            )

    # ---------- Step 1: Idempotency-Key validation (sanitized 422 envelope) ----------
    if idempotency_key_value is None:
        return _validation_error(
            loc=("header", "Idempotency-Key"),
            type_="value_error.missing",
        )
    try:
        idempotency_key = validate_idempotency_key(idempotency_key_value)
    except Exception:
        return _validation_error(
            loc=("header", "Idempotency-Key"),
            type_="value_error.invalid",
        )

    # ---------- Step 2: Conditional-header sanity (Case G) ----------
    if if_match_value is not None and if_none_match_value is not None:
        return _bad_request(
            loc=("header", "If-Match"),
            type_="both_conditional_headers_provided",
        )

    # ---------- Step 3: Parse conditional headers ----------
    if_match_etag = None  # ForecastETag | None
    if_none_match_wildcard = False

    if if_none_match_value is not None:
        try:
            parsed_none = parse_forecast_etag_header(if_none_match_value)
        except Exception:
            return _validation_error(
                loc=("header", "If-None-Match"),
                type_="value_error.invalid",
            )
        if parsed_none is not None:
            # Explicit ETag in If-None-Match is forbidden; only ``*`` satisfies the initial-create contract.
            return _bad_request(
                loc=("header", "If-None-Match"),
                type_="wildcard_required",
            )
        if_none_match_wildcard = True

    if if_match_value is not None:
        try:
            parsed_match = parse_forecast_etag_header(if_match_value)
        except Exception:
            return _validation_error(
                loc=("header", "If-Match"),
                type_="value_error.invalid",
            )
        if parsed_match is None:
            # Wildcard ``*`` is forbidden on ``If-Match`` per RFC 7232 semantics for forecast creation.
            return _validation_error(
                loc=("header", "If-Match"),
                type_="wildcard_not_allowed",
            )
        if_match_etag = parsed_match

    # ---------- Step 4: User sub -> User row id (BEFORE goal ownership) ----------
    user_id_int = _resolve_user_sub_to_id(db, user_sub)

    # ---------- Step 5: Goal ownership (BEFORE persistence gate; non-disclosing 404) ----------
    goal = _load_owned_goal(db, goal_id=goal_id, user_id=user_id_int)
    if goal is None:
        return _goal_not_found()

    # ---------- Step 6: Persistence gate ----------
    if not settings.atlas_forecast_persistence_enabled:
        return _generation_disabled()

    # ---------- Step 7: Conditional-header preflight over the existing row ----------
    expected_latest_version: Optional[int]
    if if_match_etag is not None:
        # If-Match references a forecast we own; verify it exists AND its
        # current latest_version_number matches ``if_match_etag.version_number``
        # at the repository layer (``expected_latest_version``).
        target = db.scalar(select(Forecast).where(Forecast.id == if_match_etag.forecast_id))
        if target is None or int(target.user_id) != user_id_int:
            # Stale or cross-user — non-disclosing 412.
            return _precondition_failed()
        expected_latest_version = int(if_match_etag.version_number)
    elif if_none_match_wildcard:
        existing = _existing_forecast_for_user_goal(db, user_id=user_id_int, goal_id=goal_id)
        if existing is not None:
            return _precondition_failed()
        expected_latest_version = 0
    else:
        expected_latest_version = None

    # ---------- Step 8: Adapter + service invocation ----------
    # Forward ONLY the user's verified JWT (already validated by
    # ``require_user``). The previous ``or settings.jwt_secret``
    # fallback was unsafe — it would have leaked the server signing
    # secret upstream to Finlynq if the client used cookie-only auth.
    forwarded_auth = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    adapter = HttpFinlynqProjectionStateAdapter(
        base_url=settings.finlynq_base_url,
        authorization=("Bearer " + forwarded_auth) if forwarded_auth else "",
    )

    try:
        generated = ForecastGenerationService(db, adapter).generate(
            user_id=user_id_int,
            user_sub=str(user_sub),
            goal_id=int(goal_id),
            idempotency_key=idempotency_key,
            now=datetime.now(timezone.utc),
            expected_latest_version=expected_latest_version,
        )
    except StaleForecastVersion:
        cur = _existing_forecast_for_user_goal(db, user_id=user_id_int, goal_id=goal_id)
        if cur is None:
            return _precondition_failed()
        cur_etag = derive_forecast_etag(
            forecast_id=str(cur.id),
            version_number=int(cur.latest_version_number),
        )
        return _version_conflict(
            current_etag=cur_etag,
            latest_version_number=int(cur.latest_version_number),
        )
    except IdempotencyConflict:
        return _idempotency_conflict()
    except ForecastGenerationUnavailable:
        return _generation_disabled()

    # ---------- Step 9: Build response ----------
    persisted = generated.persisted
    base_url = str(request.base_url).rstrip("/")
    envelope = build_forecast_version_response(persisted, base_url=base_url)
    forecast_id = str(persisted.forecast.id)
    version_number = int(persisted.version.version_number)
    location = f"{base_url}/api/v1/forecasts/{forecast_id}/versions/{version_number}"
    if len(location) > _MAX_LOCATION_LEN:
        location = f"http://localhost/api/v1/forecasts/{forecast_id}/versions/{version_number}"
    etag_header = format_forecast_etag_header(forecast_id=forecast_id, version_number=version_number)

    response_status = 201 if persisted.created else 200
    return JSONResponse(
        status_code=response_status,
        content=envelope.model_dump(),
        headers={"Location": location, "ETag": etag_header},
    )
