"""INV-PERSIST-01 durable investment intelligence records.

These tables are intentionally separate from the legacy goal/forecast
recommendation substrate. They store validated, server-owned snapshots of the
INV-08/09/11 contracts and contain no execution fields.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class InvestmentCommitteeRun(Base):
    __tablename__ = "investment_committee_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "run_id", name="uq_investment_committee_runs_owner_run"),
        CheckConstraint("length(run_id) BETWEEN 1 AND 128", name="ck_investment_committee_runs_run_id"),
        CheckConstraint("length(run_hash) = 64 AND run_hash = lower(run_hash)", name="ck_investment_committee_runs_hash"),
        CheckConstraint("length(owner_scope) BETWEEN 1 AND 128", name="ck_investment_committee_runs_owner_scope"),
    )
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    owner_scope = Column(String(128), nullable=False)
    run_id = Column(String(128), nullable=False)
    security_id = Column(String(128), nullable=False, index=True)
    analysis_as_of = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    methodology_version = Column(String(64), nullable=False)
    evidence_packet_id = Column(String(128), nullable=True)
    context_hash = Column(String(64), nullable=False)
    run_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    payload_json = Column(Text, nullable=False)


class InvestmentCommitteeFinding(Base):
    __tablename__ = "investment_committee_findings"
    __table_args__ = (
        UniqueConstraint("owner_id", "finding_id", name="uq_investment_committee_findings_owner_finding"),
        CheckConstraint("length(finding_id) BETWEEN 1 AND 160", name="ck_investment_committee_findings_finding_id"),
        CheckConstraint("length(finding_hash) = 64 AND finding_hash = lower(finding_hash)", name="ck_investment_committee_findings_hash"),
    )
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    run_record_id = Column(Integer, ForeignKey("investment_committee_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    finding_id = Column(String(160), nullable=False)
    security_id = Column(String(128), nullable=False, index=True)
    analysis_as_of = Column(DateTime(timezone=True), nullable=False)
    methodology_version = Column(String(64), nullable=False)
    finding_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class InvestmentEvidencePacket(Base):
    __tablename__ = "investment_evidence_packets"
    __table_args__ = (
        UniqueConstraint("owner_id", "packet_id", name="uq_investment_evidence_packets_owner_packet"),
        CheckConstraint("length(packet_hash) = 64 AND packet_hash = lower(packet_hash)", name="ck_investment_evidence_packets_hash"),
    )
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    packet_id = Column(String(128), nullable=False)
    security_id = Column(String(128), nullable=False, index=True)
    analysis_as_of = Column(DateTime(timezone=True), nullable=False)
    packet_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class InvestmentRecommendationEvidenceLink(Base):
    __tablename__ = "investment_recommendation_evidence_links"
    __table_args__ = (UniqueConstraint("recommendation_record_id", "evidence_packet_id", name="uq_investment_recommendation_evidence"),)
    recommendation_record_id = Column(Integer, ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), primary_key=True)
    evidence_packet_id = Column(Integer, ForeignKey("investment_evidence_packets.id", ondelete="RESTRICT"), primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)


class InvestmentCommitteeEvidenceLink(Base):
    __tablename__ = "investment_committee_evidence_links"
    __table_args__ = (UniqueConstraint("finding_record_id", "evidence_packet_id", name="uq_investment_committee_evidence"),)
    finding_record_id = Column(Integer, ForeignKey("investment_committee_findings.id", ondelete="RESTRICT"), primary_key=True)
    evidence_packet_id = Column(Integer, ForeignKey("investment_evidence_packets.id", ondelete="RESTRICT"), primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)


class InvestmentRecommendationRecord(Base):
    __tablename__ = "investment_recommendation_records"
    __table_args__ = (
        UniqueConstraint("owner_id", "recommendation_id", name="uq_investment_recommendations_owner_id"),
        CheckConstraint("recommendation_id LIKE 'investment-recommendation:%'", name="ck_investment_recommendations_id"),
        CheckConstraint("recommendation_type IN ('BUY', 'ADD', 'HOLD', 'REDUCE', 'SELL', 'WATCH')", name="ck_investment_recommendations_action"),
        CheckConstraint("status IN ('active', 'superseded', 'expired', 'withdrawn')", name="ck_investment_recommendations_status"),
        CheckConstraint("length(recommendation_hash) = 64 AND recommendation_hash = lower(recommendation_hash)", name="ck_investment_recommendations_hash"),
    )
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_id = Column(String(160), nullable=False)
    security_id = Column(String(128), nullable=False, index=True)
    recommendation_type = Column(String(16), nullable=False)
    status = Column(String(32), nullable=False)
    recommendation_as_of = Column(DateTime(timezone=True), nullable=False)
    review_after = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    recommendation_hash = Column(String(64), nullable=False)
    committee_finding_id = Column(String(160), nullable=False)
    committee_run_id = Column(String(128), nullable=False)
    portfolio_snapshot_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    payload_json = Column(Text, nullable=False)


class InvestmentOutcomeRecord(Base):
    __tablename__ = "investment_outcome_records"
    __table_args__ = (
        UniqueConstraint("owner_id", "outcome_id", name="uq_investment_outcomes_owner_outcome"),
        CheckConstraint("length(outcome_id) BETWEEN 1 AND 160", name="ck_investment_outcomes_id"),
        CheckConstraint("length(outcome_hash) = 64 AND outcome_hash = lower(outcome_hash)", name="ck_investment_outcomes_hash"),
    )
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_record_id = Column(Integer, ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), nullable=False, index=True)
    outcome_id = Column(String(160), nullable=False)
    recommendation_id = Column(String(160), nullable=False, index=True)
    recommendation_hash = Column(String(64), nullable=False)
    decision_id = Column(String(160), nullable=True, index=True)
    evaluation_as_of = Column(DateTime(timezone=True), nullable=False)
    outcome_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InvestmentDecisionRecord(Base):
    __tablename__ = "investment_decision_records"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key_hash", name="uq_investment_decisions_owner_idempotency"),
        CheckConstraint("decision_type IN ('accept', 'reject', 'defer', 'modify', 'no_action')", name="ck_investment_decisions_type"),
        CheckConstraint("length(decision_id) BETWEEN 1 AND 160", name="ck_investment_decisions_id"),
        CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_investment_decisions_idempotency"),
    )
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_record_id = Column(Integer, ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision_id = Column(String(160), nullable=False, unique=True)
    recommendation_id = Column(String(160), nullable=False, index=True)
    recommendation_hash = Column(String(64), nullable=False)
    decision_type = Column(String(16), nullable=False)
    decision_timestamp = Column(DateTime(timezone=True), nullable=False)
    rationale = Column(String(2000), nullable=True)
    actor_scope = Column(String(128), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
