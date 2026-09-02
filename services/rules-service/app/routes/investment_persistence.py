"""Owner-scoped, typed investment persistence API."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.investment_schemas import (
    InvestmentCommitteeFindingResponse, InvestmentDecisionEnvelope,
    InvestmentDecisionListResponse, InvestmentDecisionRequest, InvestmentDecisionResponse,
    InvestmentEvidenceResponse, InvestmentEvidenceItemResponse, InvestmentOutcomeListResponse,
    InvestmentRecommendationListResponse, InvestmentRecommendationResponse,
)
from app.investments.outcome_tracking import HumanDecision, HumanDecisionRecord
from app.investments.persistence_repository import InvestmentRepository, InvestmentRepositoryError
from app.investments.persistence_service import InvestmentPersistenceError, InvestmentPersistenceService
from app.models import InvestmentDecisionRecord, InvestmentRecommendationRecord, User

router = APIRouter(prefix="/api/v1/investments", tags=["investments"])


def _guard() -> None:
    if not settings.atlas_investment_persistence_enabled:
        raise HTTPException(503, "Investment persistence API is currently unavailable.", headers={"X-Error-Code": "investment_persistence_unavailable"})


def _owner_id(db: Session, sub: str) -> int:
    user = db.scalar(select(User).where(User.local_user_sub == sub))
    if user is None:
        raise HTTPException(401, "authenticated user row not configured")
    return int(user.id)


def _projection(db: Session, owner: int, recommendation_id: str):
    try:
        projection = InvestmentRepository(db).get_recommendation(owner_id=owner, recommendation_id=recommendation_id)
    except InvestmentRepositoryError as exc:
        raise HTTPException(409, "Investment recommendation integrity check failed", headers={"X-Error-Code": "investment_snapshot_invalid"}) from exc
    if projection is None:
        raise HTTPException(404, "Investment recommendation not found", headers={"X-Error-Code": "investment_recommendation_not_found"})
    return projection


def _recommendation_payload(projection) -> dict:
    recommendation = projection.recommendation
    return recommendation.model_dump(mode="json")


def _decision(row: InvestmentDecisionRecord) -> InvestmentDecisionResponse:
    return InvestmentDecisionResponse.model_validate({"decision_id": row.decision_id, "recommendation_id": row.recommendation_id,
        "decision_type": row.decision_type, "decision_timestamp": row.decision_timestamp,
        "rationale": row.rationale, "recommendation_hash": row.recommendation_hash, "created_at": row.created_at})


@router.get("/recommendations", response_model=InvestmentRecommendationListResponse)
def list_recommendations(user_sub: Annotated[str, Depends(require_user)], db: Session = Depends(get_db), security_id: str | None = Query(None, max_length=128), lifecycle: str | None = Query(None, max_length=32), limit: int = Query(50, ge=1, le=100)) -> InvestmentRecommendationListResponse:
    _guard(); owner = _owner_id(db, user_sub)
    if lifecycle is not None and lifecycle not in {"active", "superseded", "expired", "withdrawn"}:
        raise HTTPException(422, "Invalid investment recommendation lifecycle", headers={"X-Error-Code": "invalid_lifecycle"})
    query = select(InvestmentRecommendationRecord).where(InvestmentRecommendationRecord.owner_id == owner)
    if security_id: query = query.where(InvestmentRecommendationRecord.security_id == security_id)
    if lifecycle: query = query.where(InvestmentRecommendationRecord.status == lifecycle)
    rows = list(db.scalars(query.order_by(InvestmentRecommendationRecord.recommendation_as_of.desc(), InvestmentRecommendationRecord.id.desc()).limit(limit)))
    projections = [InvestmentRepository(db).get_recommendation(owner_id=owner, recommendation_id=row.recommendation_id) for row in rows]
    if any(projection is None for projection in projections):
        raise HTTPException(500, "Stored recommendation snapshot is unavailable", headers={"X-Error-Code": "investment_snapshot_invalid"})
    return InvestmentRecommendationListResponse(schema_version="atlas-investment-recommendation-list/v1", items=[_recommendation_payload(projection) for projection in projections])


@router.get("/recommendations/{recommendation_id}", response_model=InvestmentRecommendationResponse)
def get_recommendation(user_sub: Annotated[str, Depends(require_user)], db: Session = Depends(get_db), recommendation_id: str = Path(min_length=1, max_length=160)) -> InvestmentRecommendationResponse:
    _guard(); owner = _owner_id(db, user_sub)
    projection = _projection(db, owner, recommendation_id)
    return InvestmentRecommendationResponse(schema_version="atlas-investment-recommendation/v1", recommendation=_recommendation_payload(projection))


@router.get("/committee/findings/{finding_id}", response_model=InvestmentCommitteeFindingResponse)
def get_finding(user_sub: Annotated[str, Depends(require_user)], db: Session = Depends(get_db), finding_id: str = Path(min_length=1, max_length=160)) -> InvestmentCommitteeFindingResponse:
    _guard(); owner = _owner_id(db, user_sub)
    try:
        row = InvestmentRepository(db).get_committee_finding(owner_id=owner, finding_id=finding_id)
        finding = InvestmentRepository(db).get_committee_finding_domain(owner_id=owner, finding_id=finding_id)
    except InvestmentRepositoryError as exc:
        raise HTTPException(409, "Investment recommendation integrity check failed", headers={"X-Error-Code": "investment_snapshot_invalid"}) from exc
    if row is None or finding is None:
        raise HTTPException(404, "Investment committee finding not found", headers={"X-Error-Code": "investment_finding_not_found"})
    return InvestmentCommitteeFindingResponse(schema_version="atlas-investment-committee-finding/v1", finding=finding.model_dump(mode="json"), finding_hash=row.finding_hash, as_of=row.analysis_as_of)


@router.get("/recommendations/{recommendation_id}/evidence", response_model=InvestmentEvidenceResponse)
def get_evidence(user_sub: Annotated[str, Depends(require_user)], db: Session = Depends(get_db), recommendation_id: str = Path(min_length=1, max_length=160)) -> InvestmentEvidenceResponse:
    _guard(); owner = _owner_id(db, user_sub)
    projection = _projection(db, owner, recommendation_id)
    recommendation = projection.row
    packet = InvestmentRepository(db).get_evidence_packet(owner_id=owner, recommendation_record_id=recommendation.id)
    if packet is None: raise HTTPException(404, "Investment evidence not found", headers={"X-Error-Code": "investment_evidence_not_found"})
    data = json.loads(packet.payload_json)
    try:
        items = [InvestmentEvidenceItemResponse.model_validate(item) for item in data.get("items", [])]
    except (TypeError, ValueError) as exc:
        raise HTTPException(500, "Stored evidence packet is invalid", headers={"X-Error-Code": "investment_evidence_invalid"}) from exc
    return InvestmentEvidenceResponse(schema_version="atlas-investment-evidence-packet/v1", packet_id=packet.packet_id, packet_hash=packet.packet_hash, owner_id=packet.owner_id, subject_security_id=packet.security_id, analysis_as_of=packet.analysis_as_of, items=items)


@router.get("/recommendations/{recommendation_id}/decisions", response_model=InvestmentDecisionListResponse)
def list_decisions(user_sub: Annotated[str, Depends(require_user)], db: Session = Depends(get_db), recommendation_id: str = Path(min_length=1, max_length=160)) -> InvestmentDecisionListResponse:
    _guard(); owner = _owner_id(db, user_sub)
    recommendation = _projection(db, owner, recommendation_id).row
    rows = InvestmentRepository(db).get_decisions(owner_id=owner, recommendation_record_id=recommendation.id)
    return InvestmentDecisionListResponse(schema_version="atlas-investment-decision-list/v1", items=[_decision(row) for row in rows])


@router.post("/recommendations/{recommendation_id}/decisions", response_model=InvestmentDecisionEnvelope, status_code=201)
def create_decision(command: InvestmentDecisionRequest, user_sub: Annotated[str, Depends(require_user)], db: Session = Depends(get_db), recommendation_id: str = Path(min_length=1, max_length=160), idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=255), if_match: str | None = Header(None, alias="If-Match", max_length=256)) -> InvestmentDecisionEnvelope:
    _guard()
    if not idempotency_key or not if_match: raise HTTPException(428, "Idempotency-Key and If-Match are required", headers={"X-Error-Code": "precondition_required"})
    owner = _owner_id(db, user_sub)
    projection = _projection(db, owner, recommendation_id)
    record = projection.row
    if if_match not in {record.recommendation_hash, f'"{record.recommendation_hash}"'}: raise HTTPException(409, "Recommendation version is stale", headers={"X-Error-Code": "stale_recommendation"})
    try:
        recommendation = projection.recommendation
        decision = HumanDecisionRecord(decision_id="investment-decision:" + hashlib.sha256(f"{owner}|{recommendation_id}|{record.recommendation_hash}|{idempotency_key}".encode()).hexdigest(), tracking_id="persisted:" + recommendation_id, recommendation_id=recommendation_id, recommendation_hash=record.recommendation_hash, owner_id=owner, decision=HumanDecision(command.decision_type), decided_at=datetime.now(UTC), rationale=command.rationale)
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        existing = db.scalar(select(InvestmentDecisionRecord).where(InvestmentDecisionRecord.owner_id == owner, InvestmentDecisionRecord.idempotency_key_hash == key_hash))
        row = InvestmentPersistenceService(db).record_decision(decision, recommendation=recommendation, idempotency_key_hash=key_hash)
        db.commit()
    except InvestmentPersistenceError as exc:
        db.rollback()
        code = "investment_decision_conflict"
        message = str(exc)
        if "not eligible" in message:
            code = "investment_recommendation_not_eligible"
        raise HTTPException(409, message, headers={"X-Error-Code": code}) from exc
    return InvestmentDecisionEnvelope(schema_version="atlas-investment-decision/v1", decision=_decision(row), replayed=existing is not None)


@router.get("/recommendations/{recommendation_id}/outcomes", response_model=InvestmentOutcomeListResponse)
def list_outcomes(user_sub: Annotated[str, Depends(require_user)], db: Session = Depends(get_db), recommendation_id: str = Path(min_length=1, max_length=160)) -> InvestmentOutcomeListResponse:
    _guard(); owner = _owner_id(db, user_sub)
    recommendation = _projection(db, owner, recommendation_id).row
    rows = InvestmentRepository(db).get_outcomes(owner_id=owner, recommendation_record_id=recommendation.id)
    return InvestmentOutcomeListResponse(schema_version="atlas-investment-outcome-list/v1", items=[InvestmentOutcomeResponse.model_validate({**json.loads(row.payload_json), "outcome_id": row.outcome_id, "outcome_hash": row.outcome_hash, "decision_id": row.decision_id}) for row in rows])
