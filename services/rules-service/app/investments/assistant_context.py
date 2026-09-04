"""UI-10 typed, server-owned investment assistant context boundary."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .contracts import InvestmentStrictModel
from .persistence_repository import InvestmentRepository, InvestmentRepositoryError


class AssistantContextState(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class AssistantSectionKind(StrEnum):
    FACT = "fact"
    CALCULATION = "calculation"
    INTERPRETATION = "interpretation"
    ASSUMPTION = "assumption"
    LIMITATION = "limitation"
    REFUSAL = "refusal"


class UntrustedText(InvestmentStrictModel):
    """External/provider text is data, never executable instructions."""

    text: str = Field(max_length=1200)
    trust: Literal["untrusted_data"] = "untrusted_data"

    @field_validator("text")
    @classmethod
    def normalize(cls, value: str) -> str:
        return " ".join(value.replace("\x00", " ").split())


class AssistantRecommendationProjection(InvestmentStrictModel):
    """Minimal recommendation context; internal model metadata is excluded."""

    recommendation_id: str = Field(min_length=1, max_length=160)
    security_id: str = Field(min_length=1, max_length=128)
    recommendation_type: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=32)
    recommendation_as_of: datetime
    analysis_as_of: datetime
    thesis: str = Field(min_length=1, max_length=1600)
    rationale: str = Field(min_length=1, max_length=1600)
    key_risks: tuple[str, ...] = Field(default=(), max_length=16)
    invalidation_conditions: tuple[str, ...] = Field(default=(), max_length=16)


class AssistantCommitteeProjection(InvestmentStrictModel):
    """Minimal committee context; raw run/model metadata is excluded."""

    finding_id: str = Field(min_length=1, max_length=160)
    subject_security_id: str = Field(min_length=1, max_length=128)
    committee_view: str = Field(min_length=1, max_length=64)
    thesis: str = Field(min_length=1, max_length=1600)
    key_risks: tuple[str, ...] = Field(default=(), max_length=16)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)
    invalidation_conditions: tuple[str, ...] = Field(default=(), max_length=16)
    analysis_as_of: datetime


class InvestmentAssistantSelector(InvestmentStrictModel):
    """One client selector; canonical facts are always server-resolved."""

    recommendation_id: str | None = Field(default=None, max_length=160)
    committee_finding_id: str | None = Field(default=None, max_length=160)
    discovery_candidate_id: str | None = Field(default=None, max_length=200)
    security_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def bounded_selector(self) -> "InvestmentAssistantSelector":
        selected = tuple(value for value in (
            self.recommendation_id,
            self.committee_finding_id,
            self.discovery_candidate_id,
            self.security_id,
        ) if value)
        if len(selected) != 1:
            raise ValueError("exactly one investment context selector is required")
        return self


class AssistantEvidenceProjection(InvestmentStrictModel):
    """Minimal evidence reference exposed to the assistant and browser."""

    packet_id: str = Field(min_length=1, max_length=128)
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    trust: Literal["atlas_validated"] = "atlas_validated"


class InvestmentAssistantContext(InvestmentStrictModel):
    schema_version: Literal["InvestmentAssistantContext/v1"] = "InvestmentAssistantContext/v1"
    context_id: str = Field(min_length=1, max_length=160)
    # Authorization scope is retained for internal service checks but excluded
    # from the public response projection; it is never a browser-supplied fact.
    owner_id: int = Field(gt=0, exclude=True)
    state: AssistantContextState
    resolved_at: datetime
    context_as_of: datetime | None = None
    source_hashes: tuple[str, ...] = Field(default=(), max_length=40)
    recommendation: AssistantRecommendationProjection | None = None
    committee: AssistantCommitteeProjection | None = None
    evidence: tuple[AssistantEvidenceProjection, ...] = Field(default=(), max_length=24)
    limitations: tuple[str, ...] = Field(default=(), max_length=12)

    @field_validator("resolved_at", "context_as_of")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC) if value else None

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"context_id", "resolved_at"}), sort_keys=True, separators=(",", ":"))

    def context_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode()).hexdigest()


class AssistantContextRequest(InvestmentStrictModel):
    schema_version: Literal["InvestmentAssistantContextRequest/v1"] = "InvestmentAssistantContextRequest/v1"
    selector: InvestmentAssistantSelector
    max_evidence: int = Field(default=12, ge=1, le=24)


class InvestmentAssistantQueryRequest(InvestmentStrictModel):
    schema_version: Literal["InvestmentAssistantQueryRequest/v1"] = "InvestmentAssistantQueryRequest/v1"
    selector: InvestmentAssistantSelector
    question: str = Field(min_length=1, max_length=1000)
    max_evidence: int = Field(default=12, ge=1, le=24)
    model: str | None = Field(default=None, max_length=128)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return " ".join(value.split())


class InvestmentAssistantToolName(StrEnum):
    GET_CONTEXT = "get_investment_context"


class InvestmentAssistantToolRequest(InvestmentStrictModel):
    tool: Literal["get_investment_context"]
    selector: InvestmentAssistantSelector
    max_evidence: int = Field(default=12, ge=1, le=24)


class AssistantCitation(InvestmentStrictModel):
    citation_id: str = Field(min_length=1, max_length=160)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_type: str = Field(min_length=1, max_length=64)
    as_of: datetime | None = None
    trust: Literal["atlas_validated"] = "atlas_validated"

    @field_validator("as_of")
    @classmethod
    def citation_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("citation timestamps must be timezone-aware")
        return value.astimezone(UTC) if value else None


class AssistantResponseSection(InvestmentStrictModel):
    kind: AssistantSectionKind
    text: str = Field(min_length=1, max_length=2000)
    citations: tuple[AssistantCitation, ...] = Field(default=(), max_length=12)


class InvestmentAssistantResponse(InvestmentStrictModel):
    schema_version: Literal["InvestmentAssistantResponse/v1"] = "InvestmentAssistantResponse/v1"
    response_id: str = Field(min_length=1, max_length=160)
    context_id: str
    status: Literal["ok", "offline", "refused", "error"]
    sections: tuple[AssistantResponseSection, ...] = Field(default=(), max_length=24)
    limitations: tuple[str, ...] = Field(default=(), max_length=12)


class InvestmentAssistantToolResult(InvestmentStrictModel):
    tool: Literal["get_investment_context"]
    context: InvestmentAssistantContext


class AssistantContextError(ValueError):
    """Sanitized context resolution failure."""


InvestmentContextError = AssistantContextError


def _packet_projection(packet: Any) -> AssistantEvidenceProjection:
    return AssistantEvidenceProjection(
        packet_id=packet.packet_id,
        packet_hash=packet.packet_hash,
    )


def resolve_investment_context(*, repository: InvestmentRepository, owner_id: int, request: AssistantContextRequest) -> InvestmentAssistantContext:
    selector = request.selector
    recommendation_projection = None
    committee = None
    evidence: list[dict[str, Any]] = []
    limitations: list[str] = []

    if selector.recommendation_id:
        try:
            recommendation_projection = repository.get_recommendation(owner_id=owner_id, recommendation_id=selector.recommendation_id)
        except InvestmentRepositoryError as exc:
            raise InvestmentContextError("investment context integrity validation failed") from exc
        if recommendation_projection is None:
            raise InvestmentContextError("investment context unavailable")
        recommendation = recommendation_projection.recommendation
        if recommendation.committee_finding_id:
            try:
                committee = repository.get_committee_finding_domain(owner_id=owner_id, finding_id=recommendation.committee_finding_id)
            except InvestmentRepositoryError as exc:
                raise InvestmentContextError("committee context integrity validation failed") from exc
            if committee is None:
                limitations.append("committee context unavailable")
        try:
            packet = repository.get_evidence_packet(owner_id=owner_id, recommendation_record_id=recommendation_projection.row.id)
        except InvestmentRepositoryError as exc:
            raise InvestmentContextError("investment evidence integrity validation failed") from exc
        if packet is not None:
            evidence.append(_packet_projection(packet))
        else:
            limitations.append("evidence packet unavailable")

    if selector.committee_finding_id and committee is None:
        try:
            committee = repository.get_committee_finding_domain(owner_id=owner_id, finding_id=selector.committee_finding_id)
            finding_row = repository.get_committee_finding(owner_id=owner_id, finding_id=selector.committee_finding_id)
        except InvestmentRepositoryError as exc:
            raise InvestmentContextError("committee context integrity validation failed") from exc
        if committee is None or finding_row is None:
            raise InvestmentContextError("investment context unavailable")
        try:
            packet = repository.get_evidence_packet(owner_id=owner_id, finding_record_id=finding_row.id)
        except InvestmentRepositoryError as exc:
            raise InvestmentContextError("investment evidence integrity validation failed") from exc
        if packet is not None:
            evidence.append(_packet_projection(packet))
        else:
            limitations.append("evidence packet unavailable")

    if not recommendation_projection and not committee:
        limitations.append("the selected security/discovery context is not available through the investment repository")

    state = AssistantContextState.READY if recommendation_projection or committee else AssistantContextState.UNAVAILABLE
    recommendation = (
        AssistantRecommendationProjection.model_validate({
            "recommendation_id": recommendation_projection.recommendation.recommendation_id,
            "security_id": recommendation_projection.recommendation.security_id,
            "recommendation_type": recommendation_projection.recommendation.recommendation_type.value,
            "status": recommendation_projection.recommendation.status.value,
            "recommendation_as_of": recommendation_projection.recommendation.recommendation_as_of,
            "analysis_as_of": recommendation_projection.recommendation.analysis_as_of,
            "thesis": recommendation_projection.recommendation.thesis,
            "rationale": recommendation_projection.recommendation.rationale,
            "key_risks": recommendation_projection.recommendation.key_risks,
            "invalidation_conditions": recommendation_projection.recommendation.invalidation_conditions,
        })
        if recommendation_projection else None
    )
    committee_payload = (
        AssistantCommitteeProjection.model_validate({
            "finding_id": committee.finding_id,
            "subject_security_id": committee.subject_security_id,
            "committee_view": committee.committee_view.value,
            "thesis": committee.thesis,
            "key_risks": committee.key_risks,
            "uncertainties": committee.uncertainties,
            "invalidation_conditions": committee.invalidation_conditions,
            "analysis_as_of": committee.analysis_as_of,
        })
        if committee else None
    )
    context_as_of = (getattr(committee, "analysis_as_of", None) or getattr(recommendation_projection.recommendation, "recommendation_as_of", None)) if recommendation_projection or committee else None
    source_hashes = [item.packet_hash for item in evidence]
    if recommendation_projection:
        source_hashes.append(recommendation_projection.recommendation.recommendation_hash)
    if committee:
        source_hashes.append(committee.finding_hash)
    payload = {
        "owner_id": owner_id,
        "state": state,
        "context_as_of": context_as_of,
        "source_hashes": tuple(dict.fromkeys(source_hashes)),
        "recommendation": recommendation,
        "committee": committee_payload,
        "evidence": tuple(evidence[: request.max_evidence]),
        "limitations": tuple(limitations),
    }
    provisional = InvestmentAssistantContext(context_id="pending", resolved_at=datetime.now(UTC), **payload)
    return provisional.model_copy(update={"context_id": f"investment-context:{provisional.context_hash()[:32]}"})


__all__ = [
    "AssistantCitation", "AssistantCommitteeProjection", "AssistantContextError", "AssistantContextRequest", "AssistantEvidenceProjection",
    "InvestmentAssistantToolName", "InvestmentAssistantToolRequest", "InvestmentAssistantToolResult", "InvestmentAssistantQueryRequest",
    "AssistantContextState", "AssistantRecommendationProjection", "AssistantResponseSection", "AssistantSectionKind",
    "InvestmentAssistantContext", "InvestmentAssistantResponse",
    "InvestmentAssistantSelector", "InvestmentContextError", "UntrustedText",
    "resolve_investment_context",
]
