"""Authenticated, sanitized local readiness endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.readiness import ReadinessResponse, build_readiness

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/readiness", response_model=ReadinessResponse)
def get_readiness(
    user_sub: Annotated[str, Depends(require_user)],
    db: Session = Depends(get_db),
) -> ReadinessResponse:
    """Return only operational readiness metadata for the authenticated user."""
    return build_readiness(db, user_sub)
