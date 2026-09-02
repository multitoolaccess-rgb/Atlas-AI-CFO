from __future__ import annotations
from typing import Annotated
import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Account, Holding, User
from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import require_user
from app.config import settings
from app.discovery_schemas import DiscoveryComparisonRequest, DiscoveryComparisonResponse, DiscoveryListResponse, DiscoveryCandidateResponse
from app.investments.discovery import DiscoveryCandidate, DiscoveryQuery, DiscoveryUniverse, build_comparison, build_discovery_projection, candidate_from_symbol
from datetime import UTC, datetime

_DISCOVERY_NOW = datetime(2026, 1, 1, tzinfo=UTC)

router = APIRouter(prefix="/api/v1/investments", tags=["investment-discovery"])


_SP500_PATH = Path(__file__).resolve().parents[1] / "market_intelligence" / "data" / "sp500_symbols.json"


def _source_candidates(owner_sub: str, universe: DiscoveryUniverse, db: Session) -> list[DiscoveryCandidate]:
    """Project only approved current-only universe membership.

    Portfolio membership is resolved through the authenticated owner's accounts;
    S&P 500 membership is the existing bounded factual symbol file. Neither
    source supplies a score or recommendation semantics.
    """
    now = _DISCOVERY_NOW
    if universe == DiscoveryUniverse.SP500:
        symbols = json.loads(_SP500_PATH.read_text(encoding="utf-8"))
        return [candidate_from_symbol(str(symbol), universe=universe, as_of=now) for symbol in sorted(set(symbols))]
    account_ids = [row[0] for row in db.query(Account.id).filter(Account.user_id == _owner_id(owner_sub, db)).all()]
    if not account_ids:
        return []
    symbols = sorted({h.symbol.strip().upper() for h in db.query(Holding).filter(Holding.account_id.in_(account_ids)).all() if h.symbol and h.symbol.strip()})
    return [candidate_from_symbol(symbol, universe=universe, as_of=now) for symbol in symbols]


def _owner_id(owner_sub: str, db: Session) -> int:
    """Resolve the authenticated subject through the server user table."""
    user = db.query(User).filter(User.local_user_sub == owner_sub).first()
    return user.id if user is not None else -1


def _candidate_response(candidate: DiscoveryCandidate) -> DiscoveryCandidateResponse:
    return DiscoveryCandidateResponse(candidate_id=candidate.stable_id(), universe=DiscoveryUniverse.SP500 if ":sp500:" in candidate.security.security_id else DiscoveryUniverse.PORTFOLIO, security=candidate.security.model_dump(mode="json"), status=candidate.status, reason=candidate.reason, source=candidate.source, as_of=candidate.as_of, freshness=candidate.freshness.value, methodology_version=candidate.methodology_version, metrics=candidate.metrics, metric_states={key: value.value for key, value in candidate.metric_states.items()}, recommendation_id=candidate.recommendation_id)


def _enabled() -> None:
    if not (settings.atlas_investment_persistence_enabled or settings.atlas_investment_read_enabled):
        raise HTTPException(503, "Investment discovery is currently unavailable.", headers={"X-Error-Code": "investment_discovery_unavailable"})


@router.get("/discovery", response_model=DiscoveryListResponse)
def list_discovery(user_sub: Annotated[str, Depends(require_user)], query: str | None = Query(None, max_length=80), status: str | None = Query(None, max_length=20), universe: DiscoveryUniverse = Query(DiscoveryUniverse.PORTFOLIO), limit: int = Query(50, ge=1, le=100), as_of: datetime | None = Query(None), db: Session = Depends(get_db)) -> DiscoveryListResponse:
    _enabled()
    try:
        projection = build_discovery_projection(_source_candidates(user_sub, universe, db), DiscoveryQuery(universe=universe, query=query, status=status, limit=limit, as_of=as_of), now=lambda: _DISCOVERY_NOW)
    except ValueError as exc:
        raise HTTPException(422, str(exc), headers={"X-Error-Code": "invalid_discovery_query"}) from exc
    return DiscoveryListResponse(schema_version=projection.schema_version, as_of=projection.as_of, methodology_version=projection.methodology_version, candidates=[_candidate_response(item) for item in projection.candidates], omitted_count=projection.omitted_count, universe=universe)


@router.get("/discovery/{candidate_id}", response_model=DiscoveryCandidateResponse)
def get_discovery(candidate_id: str, user_sub: Annotated[str, Depends(require_user)], universe: DiscoveryUniverse = Query(DiscoveryUniverse.PORTFOLIO), db: Session = Depends(get_db)) -> DiscoveryCandidateResponse:
    _enabled()
    for candidate in _source_candidates(user_sub, universe, db):
        if candidate.stable_id() == candidate_id:
            return _candidate_response(candidate)
    raise HTTPException(404, "Investment discovery candidate not found", headers={"X-Error-Code": "investment_discovery_not_found"})


@router.post("/discovery/compare", response_model=DiscoveryComparisonResponse)
def compare_discovery(command: DiscoveryComparisonRequest, user_sub: Annotated[str, Depends(require_user)], universe: DiscoveryUniverse = Query(DiscoveryUniverse.PORTFOLIO), db: Session = Depends(get_db)) -> DiscoveryComparisonResponse:
    _enabled()
    candidates = {candidate.stable_id(): candidate for candidate in _source_candidates(user_sub, universe, db)}
    selected = [candidates.get(candidate_id) for candidate_id in command.candidate_ids]
    if any(item is None for item in selected):
        raise HTTPException(404, "One or more discovery candidates were not found", headers={"X-Error-Code": "investment_discovery_not_found"})
    try:
        result = build_comparison([item for item in selected if item is not None], command.metric_names)
    except ValueError as exc:
        raise HTTPException(422, str(exc), headers={"X-Error-Code": "invalid_discovery_comparison"}) from exc
    return DiscoveryComparisonResponse(schema_version=result.schema_version, candidate_ids=list(result.candidate_ids), metrics=[metric.model_dump(mode="json") for metric in result.metrics], comparable=result.comparable, limitations=list(result.limitations))
