"""Trusted INV-PERSIST-02 domain-to-persistence application service."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session

from .committee_contracts import CommitteeFinding, CommitteeRun, EvidencePacket
from .outcome_tracking import HumanDecisionRecord, RecommendationOutcome, TrackedRecommendation
from .recommendation_contracts import InvestmentRecommendation
from app.models import (
    InvestmentCommitteeFinding,
    InvestmentCommitteeRun,
    InvestmentDecisionRecord,
    InvestmentEvidencePacket,
    InvestmentRecommendationEvidenceLink,
    InvestmentCommitteeEvidenceLink,
    InvestmentRecommendationRecord,
    InvestmentOutcomeRecord,
)


class InvestmentPersistenceError(ValueError):
    """A canonical investment object failed an application invariant."""


class InvestmentPersistenceService:
    """Persists only validated, immutable domain snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _json(model: Any) -> str:
        return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise InvestmentPersistenceError("timestamp must be timezone-aware")
        return value.astimezone(UTC)

    def persist_evidence_packet(self, packet: EvidencePacket) -> InvestmentEvidencePacket:
        existing = self.session.scalar(select(InvestmentEvidencePacket).where(InvestmentEvidencePacket.owner_id == packet.owner_id, InvestmentEvidencePacket.packet_id == packet.packet_id))
        if existing:
            if existing.packet_hash != packet.packet_hash or existing.payload_json != self._json(packet):
                raise InvestmentPersistenceError("evidence packet identity conflict")
            return existing
        row = InvestmentEvidencePacket(owner_id=packet.owner_id, packet_id=packet.packet_id, security_id=packet.subject_security_id, analysis_as_of=self._utc(packet.analysis_as_of), packet_hash=packet.packet_hash, payload_json=self._json(packet), created_at=datetime.now(UTC))
        self.session.add(row)
        self.session.flush()
        return row

    def _link_recommendation_evidence(self, recommendation_record_id: int, packet_record_id: int, owner_id: int) -> None:
        self.session.add(InvestmentRecommendationEvidenceLink(
            recommendation_record_id=recommendation_record_id,
            evidence_packet_id=packet_record_id,
            owner_id=owner_id,
        ))

    def _link_committee_evidence(self, finding_record_id: int, packet_record_id: int, owner_id: int) -> None:
        self.session.add(InvestmentCommitteeEvidenceLink(
            finding_record_id=finding_record_id,
            evidence_packet_id=packet_record_id,
            owner_id=owner_id,
        ))

    def persist_committee_run(self, run: CommitteeRun, *, evidence_packet: EvidencePacket | None = None) -> InvestmentCommitteeRun:
        if run.owner_id != (evidence_packet.owner_id if evidence_packet else run.owner_id):
            raise InvestmentPersistenceError("committee/evidence owner mismatch")
        if run.subject_security_id != (evidence_packet.subject_security_id if evidence_packet else run.subject_security_id):
            raise InvestmentPersistenceError("committee/evidence security mismatch")
        if evidence_packet and run.context_hash != evidence_packet.packet_hash and evidence_packet.packet_hash not in run.context_hash:
            raise InvestmentPersistenceError("committee evidence linkage mismatch")
        existing = self.session.scalar(select(InvestmentCommitteeRun).where(InvestmentCommitteeRun.owner_id == run.owner_id, InvestmentCommitteeRun.run_id == run.run_id))
        if existing:
            if existing.run_hash != run.run_hash or existing.payload_json != self._json(run):
                raise InvestmentPersistenceError("committee run identity conflict")
            return existing
        row = InvestmentCommitteeRun(owner_id=run.owner_id, owner_scope=str(run.owner_id), run_id=run.run_id, security_id=run.subject_security_id, analysis_as_of=self._utc(run.analysis_as_of), created_at=self._utc(run.created_at), methodology_version=run.methodology_version, evidence_packet_id=evidence_packet.packet_id if evidence_packet else None, context_hash=run.context_hash, run_hash=run.run_hash, status=run.status.value, payload_json=self._json(run))
        self.session.add(row)
        self.session.flush()
        return row

    def persist_committee_finding(self, finding: CommitteeFinding, *, run: CommitteeRun, evidence_packet: EvidencePacket) -> InvestmentCommitteeFinding:
        if finding.owner_id if hasattr(finding, "owner_id") else False:
            raise InvestmentPersistenceError("unsupported committee finding owner field")
        if finding.run_id != run.run_id or finding.subject_security_id != run.subject_security_id:
            raise InvestmentPersistenceError("committee finding linkage mismatch")
        if finding.analysis_as_of > run.analysis_as_of:
            raise InvestmentPersistenceError("finding cannot be after committee run")
        packet_ids = {item.evidence_id for item in evidence_packet.items}
        if not set(finding.supporting_evidence + finding.contradicting_evidence) <= packet_ids:
            raise InvestmentPersistenceError("finding references evidence outside packet")
        run_row = self.persist_committee_run(run, evidence_packet=evidence_packet)
        existing = self.session.scalar(select(InvestmentCommitteeFinding).where(InvestmentCommitteeFinding.owner_id == run.owner_id, InvestmentCommitteeFinding.finding_id == finding.finding_id))
        if existing:
            if existing.finding_hash != finding.finding_hash or existing.payload_json != self._json(finding):
                raise InvestmentPersistenceError("committee finding identity conflict")
            return existing
        row = InvestmentCommitteeFinding(owner_id=run.owner_id, run_record_id=run_row.id, finding_id=finding.finding_id, security_id=finding.subject_security_id, analysis_as_of=self._utc(finding.analysis_as_of), methodology_version=finding.methodology_version, finding_hash=finding.finding_hash, payload_json=self._json(finding), created_at=datetime.now(UTC))
        self.session.add(row)
        self.session.flush()
        packet_row = self.session.scalar(select(InvestmentEvidencePacket).where(InvestmentEvidencePacket.owner_id == run.owner_id, InvestmentEvidencePacket.packet_id == evidence_packet.packet_id))
        if packet_row is None:
            raise InvestmentPersistenceError("committee evidence packet is not persisted")
        self._link_committee_evidence(row.id, packet_row.id, run.owner_id)
        return row

    def persist_recommendation(self, recommendation: InvestmentRecommendation, *, committee_finding: CommitteeFinding, run: CommitteeRun, evidence_packet: EvidencePacket) -> InvestmentRecommendationRecord:
        if recommendation.owner_id != run.owner_id or recommendation.committee_run_id != run.run_id or recommendation.committee_finding_id != committee_finding.finding_id:
            raise InvestmentPersistenceError("recommendation linkage mismatch")
        if recommendation.analysis_as_of > recommendation.recommendation_as_of:
            raise InvestmentPersistenceError("recommendation temporal order is invalid")
        self.persist_evidence_packet(evidence_packet)
        self.persist_committee_finding(committee_finding, run=run, evidence_packet=evidence_packet)
        existing = self.session.scalar(select(InvestmentRecommendationRecord).where(InvestmentRecommendationRecord.owner_id == recommendation.owner_id, InvestmentRecommendationRecord.recommendation_id == recommendation.recommendation_id))
        if existing:
            if existing.recommendation_hash != recommendation.recommendation_hash or existing.payload_json != self._json(recommendation):
                raise InvestmentPersistenceError("recommendation identity conflict")
            return existing
        row = InvestmentRecommendationRecord(owner_id=recommendation.owner_id, recommendation_id=recommendation.recommendation_id, security_id=recommendation.security_id, recommendation_type=recommendation.recommendation_type.value, status=recommendation.status.value, recommendation_as_of=self._utc(recommendation.recommendation_as_of), review_after=self._utc(recommendation.review_after), expires_at=self._utc(recommendation.expires_at) if recommendation.expires_at else None, recommendation_hash=recommendation.recommendation_hash, committee_finding_id=recommendation.committee_finding_id, committee_run_id=recommendation.committee_run_id, portfolio_snapshot_hash=recommendation.portfolio_snapshot_hash, created_at=self._utc(recommendation.created_at), payload_json=self._json(recommendation))
        self.session.add(row)
        self.session.flush()
        packet_row = self.session.scalar(select(InvestmentEvidencePacket).where(InvestmentEvidencePacket.owner_id == recommendation.owner_id, InvestmentEvidencePacket.packet_id == evidence_packet.packet_id))
        if packet_row is None:
            raise InvestmentPersistenceError("recommendation evidence packet is not persisted")
        self._link_recommendation_evidence(row.id, packet_row.id, recommendation.owner_id)
        return row

    def record_decision(self, decision: HumanDecisionRecord, *, recommendation: InvestmentRecommendation, idempotency_key_hash: str) -> InvestmentDecisionRecord:
        if decision.owner_id != recommendation.owner_id or decision.recommendation_id != recommendation.recommendation_id or decision.recommendation_hash != recommendation.recommendation_hash:
            raise InvestmentPersistenceError("decision recommendation linkage mismatch")
        recommendation_row = self.session.scalar(select(InvestmentRecommendationRecord).where(InvestmentRecommendationRecord.owner_id == decision.owner_id, InvestmentRecommendationRecord.recommendation_id == decision.recommendation_id))
        if recommendation_row is None:
            raise InvestmentPersistenceError("recommendation is not persisted")
        if recommendation_row.recommendation_hash != recommendation.recommendation_hash:
            raise InvestmentPersistenceError("recommendation hash is stale")
        if recommendation.status.value != "active":
            raise InvestmentPersistenceError("recommendation is not eligible for decisions")
        existing = self.session.scalar(select(InvestmentDecisionRecord).where(InvestmentDecisionRecord.owner_id == decision.owner_id, InvestmentDecisionRecord.idempotency_key_hash == idempotency_key_hash))
        if existing:
            if (existing.recommendation_id != decision.recommendation_id or existing.recommendation_hash != decision.recommendation_hash or existing.decision_type != decision.decision.value or existing.rationale != decision.rationale):
                raise InvestmentPersistenceError("idempotency key conflict")
            return existing
        row = InvestmentDecisionRecord(owner_id=decision.owner_id, recommendation_record_id=recommendation_row.id, decision_id=decision.decision_id, recommendation_id=decision.recommendation_id, recommendation_hash=decision.recommendation_hash, decision_type=decision.decision.value, decision_timestamp=self._utc(decision.decided_at), rationale=decision.rationale, actor_scope=str(decision.owner_id), idempotency_key_hash=idempotency_key_hash)
        self.session.add(row)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            existing = self.session.scalar(select(InvestmentDecisionRecord).where(InvestmentDecisionRecord.owner_id == decision.owner_id, InvestmentDecisionRecord.idempotency_key_hash == idempotency_key_hash))
            if existing and (existing.recommendation_id == decision.recommendation_id and existing.recommendation_hash == decision.recommendation_hash and existing.decision_type == decision.decision.value and existing.rationale == decision.rationale):
                return existing
            raise InvestmentPersistenceError("idempotency key conflict") from exc
        return row

    def record_outcome(self, outcome: RecommendationOutcome, *, tracking: TrackedRecommendation) -> InvestmentOutcomeRecord:
        if outcome.owner_id != tracking.owner_id or outcome.recommendation_id != tracking.recommendation_id or outcome.recommendation_hash != tracking.recommendation_hash or outcome.security_id != tracking.security_id:
            raise InvestmentPersistenceError("outcome linkage mismatch")
        if outcome.tracking_id != tracking.tracking_id:
            raise InvestmentPersistenceError("outcome tracking linkage mismatch")
        recommendation_row = self.session.scalar(select(InvestmentRecommendationRecord).where(InvestmentRecommendationRecord.owner_id == outcome.owner_id, InvestmentRecommendationRecord.recommendation_id == outcome.recommendation_id))
        if recommendation_row is None:
            raise InvestmentPersistenceError("recommendation is not persisted")
        if recommendation_row.recommendation_hash != outcome.recommendation_hash or recommendation_row.security_id != outcome.security_id:
            raise InvestmentPersistenceError("outcome recommendation snapshot mismatch")
        if outcome.evaluation_as_of < recommendation_row.recommendation_as_of:
            raise InvestmentPersistenceError("outcome evaluation precedes recommendation")
        if outcome.decision_id and outcome.evaluation_as_of < recommendation_row.recommendation_as_of:
            raise InvestmentPersistenceError("decision outcome evaluation is temporally invalid")
        decision_id = getattr(outcome, "decision_id", None)
        if decision_id:
            decision = self.session.scalar(select(InvestmentDecisionRecord).where(InvestmentDecisionRecord.owner_id == outcome.owner_id, InvestmentDecisionRecord.decision_id == decision_id, InvestmentDecisionRecord.recommendation_record_id == recommendation_row.id))
            if decision is None:
                raise InvestmentPersistenceError("outcome decision linkage is invalid")
        existing = self.session.scalar(select(InvestmentOutcomeRecord).where(InvestmentOutcomeRecord.owner_id == outcome.owner_id, InvestmentOutcomeRecord.outcome_id == outcome.outcome_id))
        if existing:
            if existing.outcome_hash != outcome.outcome_hash or existing.payload_json != self._json(outcome):
                raise InvestmentPersistenceError("outcome identity conflict")
            return existing
        row = InvestmentOutcomeRecord(owner_id=outcome.owner_id, recommendation_record_id=recommendation_row.id, outcome_id=outcome.outcome_id, recommendation_id=outcome.recommendation_id, recommendation_hash=outcome.recommendation_hash, decision_id=decision_id, evaluation_as_of=self._utc(outcome.evaluation_as_of), outcome_hash=outcome.outcome_hash, payload_json=self._json(outcome))
        self.session.add(row)
        self.session.flush()
        return row


__all__ = ["InvestmentPersistenceError", "InvestmentPersistenceService"]
