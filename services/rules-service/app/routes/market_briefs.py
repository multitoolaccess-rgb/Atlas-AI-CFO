"""Default-off owner-scoped deterministic Market Intelligence brief routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.market_intelligence.brief_repository import MarketBriefRepository
from app.market_intelligence.briefing import DeterministicTemplateProvider, MarketBrief
from app.market_intelligence.composition import TrustedMarketBriefComposer
from app.routes.recommendations_derived import _get_db, _resolve_db_user_id

router = APIRouter(tags=["market-briefs"], prefix="/api/v1/market-briefs")
_composer: TrustedMarketBriefComposer | None = None


def configure_market_brief_composer(composer: TrustedMarketBriefComposer | None) -> None:
    global _composer
    _composer = composer


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=503, content={"code": "market_brief_unavailable", "message": "Market briefing is currently disabled."})


@router.post("/generate", response_model=None)
async def generate_market_brief(request: Request, user_sub: Annotated[str, Depends(require_user)], db: Annotated[Session, Depends(_get_db)]) -> JSONResponse:
    """Fail closed until a trusted server-side portfolio assembler exists.

    Deliberately declaring no request body means client-supplied positions,
    sources, owner IDs, hashes, and provider records are neither parsed nor
    persisted.  The internal deterministic provider remains available for a
    later server-only composition path.
    """
    if not settings.atlas_market_brief_generation_enabled or not settings.atlas_market_brief_external_provider_enabled or _composer is None:
        return _unavailable()
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    report_window = raw.get("report_window", "latest") if isinstance(raw, dict) else "latest"
    if not isinstance(report_window, str) or not 1 <= len(report_window) <= 64:
        return _unavailable()
    user_id = _resolve_db_user_id(db, user_sub)
    brief = DeterministicTemplateProvider().generate(_composer.assemble(db, owner_id=user_id, report_window=report_window))
    row, replayed = MarketBriefRepository(db).get_or_create(brief)
    return JSONResponse(status_code=200 if replayed else 201, content={"brief_id": row.id, "replayed": replayed, "brief": brief.model_dump(mode="json")})


@router.get("/{brief_id}", response_model=None)
async def get_market_brief(brief_id: str, user_sub: Annotated[str, Depends(require_user)], db: Annotated[Session, Depends(_get_db)]) -> JSONResponse:
    if not settings.atlas_market_brief_read_api_enabled:
        return _unavailable()
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
async def list_market_briefs(user_sub: Annotated[str, Depends(require_user)], db: Annotated[Session, Depends(_get_db)], limit: int = 20) -> JSONResponse:
    if not settings.atlas_market_brief_read_api_enabled:
        return _unavailable()
    limit = min(max(limit, 1), 50)
    from sqlalchemy import select
    from app.models.market_brief import MarketBrief as StoredBrief
    user_id = _resolve_db_user_id(db, user_sub)
    rows = db.scalars(select(StoredBrief).where(StoredBrief.user_id == user_id).order_by(StoredBrief.generated_at.desc(), StoredBrief.id.desc()).limit(limit)).all()
    return JSONResponse(content={"briefs": [{"brief_id": row.id, "generated_at": row.generated_at.isoformat(), "report_window": row.report_window} for row in rows]})
