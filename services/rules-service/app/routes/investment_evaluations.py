"""INV-12 owner-scoped evaluation read API (design gate §17).

Read-only: list, detail, and deterministic replay re-verification. The
internal write boundary is enforced by construction — there is no route that
accepts evaluation/observation/snapshot writes, no scheduler, and no browser
write path. Client ``owner_id``-style fields cannot be injected because these
endpoints take no analytical JSON body; owner scope always comes from auth.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.investment_schemas import (
    InvestmentEvaluationListResponse,
    InvestmentEvaluationResponse,
    InvestmentEvaluationReplayResponse,
)
from app.investments.evaluation_contracts import HORIZONS
from app.investments.evaluation_service import EvaluationService, EvaluationServiceError
from app.investments.persistence_repository import InvestmentRepositoryError
from app.models import User

router = APIRouter(prefix="/api/v1/investments/evaluations", tags=["investments"])


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Investment evaluation is currently unavailable.",
        headers={"X-Error-Code": "investment_evaluations_unavailable"},
    )


def _owner_id(db: Session, user_sub: str) -> int:
    user = db.scalar(select(User).where(User.local_user_sub == user_sub))
    if user is None:
        raise HTTPException(401, "authenticated user row not configured")
    return int(user.id)


def _guard() -> None:
    if not (settings.atlas_investment_read_enabled or settings.atlas_investment_persistence_enabled):
        raise _unavailable()


@router.get("", response_model=InvestmentEvaluationListResponse)
def list_evaluations(
    user_sub: Annotated[str, Depends(require_user)],
    db: Session = Depends(get_db),
    recommendation_id: str | None = Query(None, min_length=1, max_length=160),
    horizon: str | None = Query(None, max_length=8),
    limit: int = Query(50, ge=1, le=100),
) -> InvestmentEvaluationListResponse:
    _guard()
    owner = _owner_id(db, user_sub)
    if horizon is not None and horizon not in HORIZONS:
        raise HTTPException(422, "Invalid evaluation horizon", headers={"X-Error-Code": "invalid_horizon"})
    try:
        artifacts = EvaluationService(db).list_evaluations(owner_id=owner, recommendation_id=recommendation_id, horizon=horizon, limit=limit)
    except InvestmentRepositoryError as exc:
        raise HTTPException(409, "Stored evaluation artifact integrity check failed", headers={"X-Error-Code": "investment_evaluation_invalid"}) from exc
    return InvestmentEvaluationListResponse(
        schema_version="atlas-investment-evaluation-list/v1",
        items=[artifact.model_dump(mode="json", exclude={"owner_id"}) for artifact in artifacts],
    )


@router.get("/{evaluation_id}", response_model=InvestmentEvaluationResponse)
def get_evaluation(
    user_sub: Annotated[str, Depends(require_user)],
    db: Session = Depends(get_db),
    evaluation_id: str = Path(min_length=1, max_length=160),
) -> InvestmentEvaluationResponse:
    _guard()
    owner = _owner_id(db, user_sub)
    try:
        artifact = EvaluationService(db).get_evaluation(owner_id=owner, evaluation_id=evaluation_id)
    except InvestmentRepositoryError as exc:
        raise HTTPException(409, "Stored evaluation artifact integrity check failed", headers={"X-Error-Code": "investment_evaluation_invalid"}) from exc
    if artifact is None:
        raise HTTPException(404, "Investment evaluation not found", headers={"X-Error-Code": "investment_evaluation_not_found"})
    return InvestmentEvaluationResponse(schema_version="atlas-investment-evaluation/v1", evaluation=artifact.model_dump(mode="json", exclude={"owner_id"}))


@router.get("/{evaluation_id}/replay", response_model=InvestmentEvaluationReplayResponse)
def replay_evaluation(
    user_sub: Annotated[str, Depends(require_user)],
    db: Session = Depends(get_db),
    evaluation_id: str = Path(min_length=1, max_length=160),
) -> InvestmentEvaluationReplayResponse:
    _guard()
    owner = _owner_id(db, user_sub)
    service = EvaluationService(db)
    try:
        result = service.replay(owner_id=owner, evaluation_id=evaluation_id, at=datetime.now(UTC))
    except EvaluationServiceError:
        raise HTTPException(404, "Investment evaluation not found", headers={"X-Error-Code": "investment_evaluation_not_found"}) from None
    return InvestmentEvaluationReplayResponse(
        schema_version="atlas-investment-evaluation-replay/v1",
        evaluation_id=result.evaluation_id,
        replay_state=result.replay_state.value,
        verified=result.verified,
        evaluation_hash=result.evaluation_hash,
        input_hash=result.input_hash,
        replayed_at=result.replayed_at,
    )
