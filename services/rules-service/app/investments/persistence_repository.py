"""Trusted repository projections for persisted investment intelligence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InvestmentRecommendationRecord
from .recommendation_contracts import InvestmentRecommendation


class InvestmentRepositoryError(ValueError):
    """Persisted investment data failed integrity validation."""


@dataclass(frozen=True)
class InvestmentRecommendationProjection:
    row: InvestmentRecommendationRecord
    recommendation: InvestmentRecommendation


class InvestmentRepository:
    """Loads only owner-scoped, hash-verified canonical investment objects."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_recommendation(self, *, owner_id: int, recommendation_id: str) -> InvestmentRecommendationProjection | None:
        row = self.session.scalar(
            select(InvestmentRecommendationRecord).where(
                InvestmentRecommendationRecord.owner_id == owner_id,
                InvestmentRecommendationRecord.recommendation_id == recommendation_id,
            )
        )
        if row is None:
            return None
        try:
            payload = json.loads(row.payload_json)
            recommendation = InvestmentRecommendation.model_validate(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvestmentRepositoryError("stored recommendation snapshot is invalid") from exc
        if recommendation.owner_id != row.owner_id or recommendation.recommendation_id != row.recommendation_id:
            raise InvestmentRepositoryError("stored recommendation identity mismatch")
        if recommendation.security_id != row.security_id or recommendation.recommendation_type.value != row.recommendation_type:
            raise InvestmentRepositoryError("stored recommendation projection mismatch")
        if recommendation.status.value != row.status:
            raise InvestmentRepositoryError("stored recommendation lifecycle mismatch")
        if recommendation.recommendation_hash != row.recommendation_hash:
            raise InvestmentRepositoryError("stored recommendation hash mismatch")
        canonical_hash = hashlib.sha256(recommendation.canonical_payload().encode()).hexdigest()
        if canonical_hash != row.recommendation_hash:
            raise InvestmentRepositoryError("stored recommendation canonical hash mismatch")
        if recommendation.committee_finding_id != row.committee_finding_id or recommendation.committee_run_id != row.committee_run_id:
            raise InvestmentRepositoryError("stored committee linkage mismatch")
        if recommendation.portfolio_snapshot_hash != row.portfolio_snapshot_hash:
            raise InvestmentRepositoryError("stored portfolio snapshot mismatch")
        return InvestmentRecommendationProjection(row=row, recommendation=recommendation)


__all__ = ["InvestmentRepository", "InvestmentRepositoryError", "InvestmentRecommendationProjection"]
