"""Trusted repository projections for persisted investment intelligence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InvestmentCommitteeEvidenceLink,
    InvestmentCommitteeFinding,
    InvestmentCommitteeRun,
    InvestmentDecisionRecord,
    InvestmentEvidencePacket,
    InvestmentOutcomeRecord,
    InvestmentRecommendationEvidenceLink,
    InvestmentRecommendationRecord,
)
from .recommendation_contracts import InvestmentRecommendation
from .committee_contracts import CommitteeFinding, CommitteeRun, EvidencePacket
from .outcome_tracking import HumanDecisionRecord, RecommendationOutcome


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

    def get_committee_run(self, *, owner_id: int, run_id: str) -> InvestmentCommitteeRun | None:
        return self.session.scalar(select(InvestmentCommitteeRun).where(InvestmentCommitteeRun.owner_id == owner_id, InvestmentCommitteeRun.run_id == run_id))

    def get_committee_run_domain(self, *, owner_id: int, run_id: str) -> CommitteeRun | None:
        row = self.get_committee_run(owner_id=owner_id, run_id=run_id)
        if row is None:
            return None
        try:
            value = CommitteeRun.model_validate(json.loads(row.payload_json))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvestmentRepositoryError("stored committee run snapshot is invalid") from exc
        if value.owner_id != owner_id or value.run_id != row.run_id or value.run_hash != row.run_hash:
            raise InvestmentRepositoryError("stored committee run integrity mismatch")
        return value

    def get_committee_finding(self, *, owner_id: int, finding_id: str) -> InvestmentCommitteeFinding | None:
        return self.session.scalar(select(InvestmentCommitteeFinding).where(InvestmentCommitteeFinding.owner_id == owner_id, InvestmentCommitteeFinding.finding_id == finding_id))

    def get_committee_finding_domain(self, *, owner_id: int, finding_id: str) -> CommitteeFinding | None:
        row = self.get_committee_finding(owner_id=owner_id, finding_id=finding_id)
        if row is None:
            return None
        try:
            value = CommitteeFinding.model_validate(json.loads(row.payload_json))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvestmentRepositoryError("stored committee finding snapshot is invalid") from exc
        if value.finding_id != row.finding_id or value.finding_hash != row.finding_hash or value.subject_security_id != row.security_id:
            raise InvestmentRepositoryError("stored committee finding integrity mismatch")
        return value

    def get_evidence_packet(self, *, owner_id: int, recommendation_record_id: int | None = None, finding_record_id: int | None = None) -> InvestmentEvidencePacket | None:
        if recommendation_record_id is not None:
            return self.session.scalar(select(InvestmentEvidencePacket).join(InvestmentRecommendationEvidenceLink, InvestmentRecommendationEvidenceLink.evidence_packet_id == InvestmentEvidencePacket.id).where(InvestmentRecommendationEvidenceLink.recommendation_record_id == recommendation_record_id, InvestmentRecommendationEvidenceLink.owner_id == owner_id, InvestmentEvidencePacket.owner_id == owner_id))
        if finding_record_id is not None:
            return self.session.scalar(select(InvestmentEvidencePacket).join(InvestmentCommitteeEvidenceLink, InvestmentCommitteeEvidenceLink.evidence_packet_id == InvestmentEvidencePacket.id).where(InvestmentCommitteeEvidenceLink.finding_record_id == finding_record_id, InvestmentCommitteeEvidenceLink.owner_id == owner_id, InvestmentEvidencePacket.owner_id == owner_id))
        return None

    def get_decision(self, *, owner_id: int, decision_id: str) -> InvestmentDecisionRecord | None:
        return self.session.scalar(select(InvestmentDecisionRecord).where(InvestmentDecisionRecord.owner_id == owner_id, InvestmentDecisionRecord.decision_id == decision_id))

    def get_outcome(self, *, owner_id: int, outcome_id: str) -> InvestmentOutcomeRecord | None:
        return self.session.scalar(select(InvestmentOutcomeRecord).where(InvestmentOutcomeRecord.owner_id == owner_id, InvestmentOutcomeRecord.outcome_id == outcome_id))

    def get_decisions(self, *, owner_id: int, recommendation_record_id: int) -> list[InvestmentDecisionRecord]:
        return list(self.session.scalars(select(InvestmentDecisionRecord).where(InvestmentDecisionRecord.owner_id == owner_id, InvestmentDecisionRecord.recommendation_record_id == recommendation_record_id).order_by(InvestmentDecisionRecord.decision_timestamp.asc(), InvestmentDecisionRecord.id.asc())))

    def get_outcomes(self, *, owner_id: int, recommendation_record_id: int) -> list[InvestmentOutcomeRecord]:
        return list(self.session.scalars(select(InvestmentOutcomeRecord).where(InvestmentOutcomeRecord.owner_id == owner_id, InvestmentOutcomeRecord.recommendation_record_id == recommendation_record_id).order_by(InvestmentOutcomeRecord.evaluation_as_of.asc(), InvestmentOutcomeRecord.id.asc())))

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
