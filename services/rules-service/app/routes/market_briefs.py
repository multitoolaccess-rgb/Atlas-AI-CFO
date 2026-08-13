"""Default-off owner-scoped deterministic Market Intelligence brief routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.market_intelligence.brief_repository import MarketBriefRepository
from app.market_intelligence.briefing import DeterministicTemplateProvider, MarketBrief
from app.market_intelligence.contracts import MarketBriefReasonCode, StrictModel
from app.market_intelligence.composition import MarketBriefCompositionError, TrustedMarketBriefComposer
from app.models.market_brief import MarketBrief as StoredBrief
from app.routes.recommendations_derived import _get_db, _resolve_db_user_id

router = APIRouter(tags=["market-briefs"], prefix="/api/v1/market-briefs")
_composer: TrustedMarketBriefComposer | None = None


class GenerateMarketBriefControl(StrictModel):
    """The public generate payload deliberately contains no financial facts."""
    report_window: str = "latest"


_REASON_MESSAGES: dict[MarketBriefReasonCode, tuple[str, str]] = {
    MarketBriefReasonCode.PROVIDER_CONFIGURATION_MISSING: (
        "Market data is not configured on the server.",
        "Ask the local operator to configure the approved server-side provider, then retry.",
    ),
    MarketBriefReasonCode.PROVIDER_TRANSPORT_FAILURE: (
        "The market-data provider could not be reached.",
        "Check the provider connection and retry; no market data was saved.",
    ),
    MarketBriefReasonCode.PROVIDER_AUTHENTICATION_FAILED: (
        "The market-data provider rejected its server-side credentials.",
        "Ask the local operator to verify the provider configuration, then retry.",
    ),
    MarketBriefReasonCode.PROVIDER_RATE_LIMITED: (
        "The market-data provider is temporarily rate limiting requests.",
        "Wait briefly and retry; no market data was saved.",
    ),
    MarketBriefReasonCode.UNSUPPORTED_SYMBOL: (
        "One or more holdings are not supported by the approved provider.",
        "Review the omitted holdings and retry after the portfolio is addressable.",
    ),
    MarketBriefReasonCode.LIVE_QUOTE_STALE: (
        "Live market quotes are outside the allowed freshness window.",
        "Retry during market hours or use the accepted prior-close mode outside the session.",
    ),
    MarketBriefReasonCode.PRIOR_CLOSE_TOO_OLD: (
        "The available prior close is outside the allowed trading-session window.",
        "Refresh provider data before generating another brief.",
    ),
    MarketBriefReasonCode.INVALID_QUOTE: (
        "The provider returned an invalid or incomplete quote.",
        "Ask the local operator to verify the provider response and retry.",
    ),
    MarketBriefReasonCode.AMBIGUOUS_CURRENCY: (
        "The portfolio currency could not be established safely.",
        "Resolve the portfolio currency ambiguity before generating a brief.",
    ),
    MarketBriefReasonCode.INSUFFICIENT_PORTFOLIO_COVERAGE: (
        "Too little of the eligible portfolio has trustworthy market coverage.",
        "Resolve omitted holdings before generating a complete portfolio brief.",
    ),
    MarketBriefReasonCode.NO_MARKET_ADDRESSABLE_HOLDINGS: (
        "No trustworthy market-addressable holdings remain.",
        "Add or correct an eligible holding before generating a brief.",
    ),
    MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE: (
        "Market briefing is currently unavailable.",
        "Retry after the local operator resolves the reported readiness issue.",
    ),
}


def configure_market_brief_composer(composer: TrustedMarketBriefComposer | None) -> None:
    global _composer
    _composer = composer


def _error_response(
    reason_code: MarketBriefReasonCode,
    *,
    status_code: int = 503,
    omitted_symbols: tuple[str, ...] = (),
) -> JSONResponse:
    message, recovery = _REASON_MESSAGES[reason_code]
    content: dict[str, object] = {
        "code": "market_brief_generation_unavailable",
        "reason_code": reason_code.value,
        "message": message,
        "recovery": recovery,
    }
    if omitted_symbols:
        content["omitted_symbols"] = list(omitted_symbols)
    return JSONResponse(status_code=status_code, content=content)


def _read_unavailable() -> JSONResponse:
    return _error_response(MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE)


@router.post("/generate", response_model=None)
async def generate_market_brief(
    request: Request,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
) -> JSONResponse:
    """Assemble all financial facts from authenticated server-side state."""
    if not settings.atlas_market_brief_generation_enabled or not settings.atlas_market_brief_external_provider_enabled or _composer is None:
        return _error_response(MarketBriefReasonCode.PROVIDER_CONFIGURATION_MISSING)
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    try:
        control = GenerateMarketBriefControl.model_validate(raw)
    except ValidationError:
        return JSONResponse(status_code=422, content={"code": "invalid_market_brief_control"})
    if not 1 <= len(control.report_window) <= 64:
        return JSONResponse(status_code=422, content={"code": "invalid_market_brief_control"})
    user_id = _resolve_db_user_id(db, user_sub)
    try:
        brief = DeterministicTemplateProvider().generate(_composer.assemble(db, owner_id=user_id, report_window=control.report_window))
    except MarketBriefCompositionError as error:
        return _error_response(error.reason_code, omitted_symbols=error.omitted_symbols)
    row, replayed = MarketBriefRepository(db).get_or_create(brief)
    return JSONResponse(status_code=200 if replayed else 201, content={"brief_id": row.id, "replayed": replayed, "brief": brief.model_dump(mode="json")})


@router.get("/{brief_id}", response_model=None)
async def get_market_brief(
    brief_id: str,
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
) -> JSONResponse:
    if not settings.atlas_market_brief_read_api_enabled:
        return _read_unavailable()
    if not brief_id or len(brief_id) > 36:
        return JSONResponse(status_code=404, content={"code": "market_brief_not_found"})
    row = MarketBriefRepository(db).get_owned(user_id=_resolve_db_user_id(db, user_sub), brief_id=brief_id)
    if row is None:
        return JSONResponse(status_code=404, content={"code": "market_brief_not_found"})
    try:
        brief = MarketBrief.model_validate_json(row.payload_json)
    except ValidationError:
        return JSONResponse(status_code=404, content={"code": "market_brief_not_found"})
    return JSONResponse(content={"brief_id": row.id, "brief": brief.model_dump(mode="json")})


@router.get("", response_model=None)
async def list_market_briefs(
    user_sub: Annotated[str, Depends(require_user)],
    db: Annotated[Session, Depends(_get_db)],
    limit: int = 20,
) -> JSONResponse:
    if not settings.atlas_market_brief_read_api_enabled:
        return _read_unavailable()
    limit = min(max(limit, 1), 50)
    user_id = _resolve_db_user_id(db, user_sub)
    rows = db.scalars(
        select(StoredBrief)
        .where(StoredBrief.user_id == user_id)
        .order_by(StoredBrief.generated_at.desc(), StoredBrief.id.desc())
        .limit(limit)
    ).all()
    briefs: list[dict[str, object]] = []
    for row in rows:
        item: dict[str, object] = {"brief_id": row.id, "generated_at": row.generated_at.isoformat(), "report_window": row.report_window}
        try:
            brief = MarketBrief.model_validate_json(row.payload_json)
            item.update({
                "market_data_basis": brief.market_data_basis.value,
                "provider_status": brief.provider_readiness.status,
                "coverage": brief.coverage.model_dump(mode="json") if brief.coverage else None,
            })
        except ValidationError:
            item.update({"market_data_basis": "unknown", "provider_status": "unavailable", "coverage": None})
        briefs.append(item)
    return JSONResponse(content={"briefs": briefs})
