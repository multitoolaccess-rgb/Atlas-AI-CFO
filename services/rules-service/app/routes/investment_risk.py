"""UI-11 owner-scoped portfolio baseline and hypothetical preview API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.routes.shared import get_or_create_local_user
from app.investments.risk_scenarios import (
    InvestmentRiskService,
    PortfolioBaselineResponse,
    RiskBoundaryError,
    RiskConflict,
    RiskNotFound,
    RiskScenarioRequest,
    RiskScenarioResponse,
)

router = APIRouter(prefix="/api/v1/investments/portfolio-risk", tags=["investment-risk"])


def _enabled() -> None:
    # UI-11 uses the existing server-owned investment read gate. No client
    # request can enable this route.
    from app.config import settings
    if not (settings.atlas_investment_read_enabled or settings.atlas_investment_persistence_enabled):
        raise HTTPException(status_code=503, detail="Investment risk is currently unavailable.", headers={"X-Error-Code": "investment_risk_unavailable"})


def _owner_id(db: Session, user_sub: str) -> int:
    return int(get_or_create_local_user(db, user_sub).id)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Investment risk resource not found", headers={"X-Error-Code": "investment_risk_not_found"})


@router.get("/baseline", response_model=PortfolioBaselineResponse)
def read_portfolio_baseline(
    user_sub: Annotated[str, Depends(require_user)],
    db: Session = Depends(get_db),
) -> PortfolioBaselineResponse:
    """Return the authenticated owner's current-only typed portfolio baseline."""
    _enabled()
    try:
        baseline = InvestmentRiskService(db).get_portfolio_baseline(owner_id=_owner_id(db, user_sub))
        return PortfolioBaselineResponse(**baseline.model_dump(exclude={"owner_id"}))
    except (RiskBoundaryError, ValueError):
        raise _not_found() from None


@router.post("/scenarios/preview", response_model=RiskScenarioResponse)
def preview_portfolio_scenario(
    request: RiskScenarioRequest,
    user_sub: Annotated[str, Depends(require_user)],
    db: Session = Depends(get_db),
) -> RiskScenarioResponse:
    """Preview one bounded position-value delta without mutating portfolio state."""
    _enabled()
    try:
        scenario = InvestmentRiskService(db).preview_investment_risk_scenario(
            owner_id=_owner_id(db, user_sub), request=request,
        )
        return RiskScenarioResponse(**scenario.model_dump(exclude={"owner_id"}))
    except RiskNotFound:
        raise _not_found() from None
    except RiskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers={"X-Error-Code": "investment_risk_conflict"}) from None
    except RiskBoundaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc), headers={"X-Error-Code": "invalid_investment_risk_scenario"}) from None


__all__ = ["router"]
