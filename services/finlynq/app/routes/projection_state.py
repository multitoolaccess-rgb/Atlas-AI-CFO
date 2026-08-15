"""Sanctioned authenticated B0 provider boundary; not a generic state API."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.projection_state.provider import ProjectionStateUnavailable, build_projection_state


router = APIRouter(prefix="/projection-state", tags=["projection-state"])


@router.get("/goals/{goal_id}")
def get_goal_projection_state(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(require_user),
) -> dict:
    try:
        return build_projection_state(db, user_sub=current_user, goal_id=goal_id)
    except ProjectionStateUnavailable as exc:
        if str(exc) == "projection_state_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="projection state unavailable") from None
        safe_codes = {
            "currency_unknown", "currency_mixed", "currency_conflict", "currency_stale",
            "currency_unsupported", "currency_revoked", "currency_evidence_incomplete",
        }
        detail = str(exc) if str(exc) in safe_codes else "projection state unavailable"
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from None
