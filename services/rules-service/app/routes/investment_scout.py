"""UI-10 bounded provider-backed Scout API.

Only canonical security selectors resolved through owner-authorized Atlas
records are accepted. The route never accepts source URLs, financial facts,
provider credentials, or model-authored citations.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.investments.scout import (
    ScoutResearchError,
    ScoutResearchRequest,
    ScoutResearchResult,
    ScoutRunSummary,
    list_scout_runs,
    load_scout_run,
    persist_scout_result,
    research_current_security,
)
from app.routes.shared import get_or_create_local_user

router = APIRouter(prefix="/api/v1/investments/scout", tags=["investment-scout"])


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Provider-backed investment Scout research is currently unavailable.",
        headers={"X-Error-Code": "investment_scout_unavailable"},
    )


@router.post("/research", response_model=ScoutResearchResult)
def research(
    request: ScoutResearchRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(require_user),
) -> ScoutResearchResult:
    """Run bounded current-context research and persist its immutable result."""
    if not settings.atlas_investment_scout_external_provider_enabled:
        raise _unavailable()
    owner = get_or_create_local_user(db, current_user)
    try:
        result = research_current_security(db=db, owner_id=owner.id, request=request)
        persisted, _ = persist_scout_result(db, result)
        return persisted
    except ScoutResearchError as exc:
        message = str(exc)
        if message in {
            "provider-backed Scout research is disabled",
            "approved research providers are not configured",
        }:
            raise _unavailable() from exc
        raise HTTPException(status_code=404, detail="Investment Scout research context is unavailable.", headers={"X-Error-Code": "investment_scout_context_unavailable"}) from exc
    except Exception as exc:  # noqa: BLE001 - sanitized provider boundary
        db.rollback()
        raise HTTPException(status_code=503, detail="Investment Scout research is temporarily unavailable.", headers={"X-Error-Code": "investment_scout_research_unavailable"}) from exc


@router.get("/runs", response_model=list[ScoutRunSummary])
def runs(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: str = Depends(require_user),
) -> list[ScoutRunSummary]:
    if not settings.atlas_investment_scout_external_provider_enabled:
        raise _unavailable()
    owner = get_or_create_local_user(db, current_user)
    try:
        return list_scout_runs(db, owner_id=owner.id, limit=limit)
    except ScoutResearchError as exc:
        raise HTTPException(status_code=503, detail="Stored Scout research is unavailable.", headers={"X-Error-Code": "investment_scout_storage_unavailable"}) from exc


@router.get("/runs/{run_id}", response_model=ScoutResearchResult)
def run(
    run_id: str = Path(min_length=1, max_length=160),
    db: Session = Depends(get_db),
    current_user: str = Depends(require_user),
) -> ScoutResearchResult:
    if not settings.atlas_investment_scout_external_provider_enabled:
        raise _unavailable()
    owner = get_or_create_local_user(db, current_user)
    try:
        result = load_scout_run(db, owner_id=owner.id, run_id=run_id)
    except ScoutResearchError as exc:
        raise HTTPException(status_code=404, detail="Investment Scout run is unavailable.", headers={"X-Error-Code": "investment_scout_run_unavailable"}) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Investment Scout run is unavailable.", headers={"X-Error-Code": "investment_scout_run_unavailable"})
    return result


__all__ = ["router"]
