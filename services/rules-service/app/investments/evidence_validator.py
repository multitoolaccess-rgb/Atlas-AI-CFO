"""Deterministic evidence gates for INV-08.

The validator accepts only references in the frozen packet. It never repairs
model output or resolves an invented citation on the model's behalf.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .committee_contracts import (
    AgentFinding,
    ClaimClass,
    CommitteeContext,
    CommitteeDataQuality,
    EvidencePacket,
    ModelChairPayload,
    ModelFindingPayload,
)


class EvidenceValidationError(ValueError):
    """Sanitized failure for an invalid or unauthorized evidence reference."""


def _packet_items(packet: EvidencePacket) -> dict[str, object]:
    return {item.evidence_id: item for item in packet.items}


def validate_packet(packet: EvidencePacket) -> None:
    """Verify the packet hash, ownership, temporal order, and source links."""
    expected = EvidencePacket.with_hash(
        packet_id=packet.packet_id,
        owner_id=packet.owner_id,
        subject_security_id=packet.subject_security_id,
        analysis_as_of=packet.analysis_as_of,
        items=packet.items,
    )
    if packet.packet_hash != expected.packet_hash:
        raise EvidenceValidationError("evidence packet hash is invalid")
    for item in packet.items:
        if item.reference.evidence_id != item.evidence_id:
            raise EvidenceValidationError("evidence reference identity is inconsistent")
        if item.reference.as_of > packet.analysis_as_of:
            raise EvidenceValidationError("evidence is not valid at analysis as_of")
        if item.reference.as_of > item.reference.retrieved_at:
            raise EvidenceValidationError("evidence retrieval precedes evidence as_of")
        if item.reference.state.value in {"missing", "unknown"}:
            raise EvidenceValidationError("missing evidence cannot enter a packet")


def validate_context(context: CommitteeContext) -> None:
    """Validate packet integrity and the context-to-packet ownership boundary."""
    validate_packet(context.evidence_packet)
    expected_inputs = tuple(sorted(set((context.evidence_packet.packet_hash, *context.input_hashes))))
    if context.evidence_packet.packet_hash not in expected_inputs:
        raise EvidenceValidationError("context does not identify its evidence packet")
    expected = CommitteeContext.with_hash(
        run_id=context.run_id,
        owner_id=context.owner_id,
        subject_security_id=context.subject_security_id,
        analysis_as_of=context.analysis_as_of,
        evidence_packet=context.evidence_packet,
        portfolio_snapshot_hash=context.portfolio_snapshot_hash,
        input_hashes=context.input_hashes,
    )
    if context.context_hash != expected.context_hash:
        raise EvidenceValidationError("committee context hash is invalid")


def _validate_refs(
    refs: tuple[str, ...],
    *,
    packet: EvidencePacket,
    claim_class: ClaimClass | None = None,
    data_quality: tuple[CommitteeDataQuality, ...] = (),
) -> dict[str, object]:
    items = _packet_items(packet)
    if len(refs) != len(set(refs)):
        raise EvidenceValidationError("duplicate evidence references are not allowed")
    resolved: dict[str, object] = {}
    for ref in refs:
        item = items.get(ref)
        if item is None:
            raise EvidenceValidationError("finding references evidence outside the packet")
        if item.reference.as_of > packet.analysis_as_of:
            raise EvidenceValidationError("finding references future evidence")
        if item.owner_id not in (None, packet.owner_id):
            raise EvidenceValidationError("finding references unauthorized evidence")
        if item.subject_security_id not in (None, packet.subject_security_id):
            raise EvidenceValidationError("finding references another security")
        if item.reference.state.value in {"missing", "unknown"}:
            raise EvidenceValidationError("finding references unavailable evidence")
        if item.reference.state.value == "stale" and claim_class not in {ClaimClass.UNCERTAINTY} and CommitteeDataQuality.STALE not in data_quality:
            raise EvidenceValidationError("stale evidence must be disclosed")
        resolved[ref] = item
    return resolved


def _validate_numeric_claims(payload, resolved: dict[str, object]) -> None:
    for claim in payload.numeric_claims:
        item = resolved.get(claim.evidence_ref)
        if item is None:
            raise EvidenceValidationError("numeric claim cites an unselected evidence item")
        numeric_value = getattr(item, "numeric_value", None)
        if numeric_value is None:
            raise EvidenceValidationError("numeric claim has no canonical numeric evidence")
        try:
            if Decimal(claim.value) != Decimal(numeric_value):
                raise EvidenceValidationError("numeric claim does not match canonical evidence")
        except (InvalidOperation, ValueError) as exc:
            raise EvidenceValidationError("numeric claim is not a valid decimal") from exc


def validate_model_finding(payload: ModelFindingPayload, *, context: CommitteeContext) -> None:
    """Validate model citations and numerical claims before attribution."""
    refs = (*payload.evidence_refs, *payload.calculation_refs)
    resolved = _validate_refs(
        refs,
        packet=context.evidence_packet,
        claim_class=payload.claim_class,
        data_quality=payload.data_quality,
    )
    _validate_numeric_claims(payload, resolved)
    if payload.abstained:
        return
    if payload.claim_class is ClaimClass.OBSERVED_FACT and not payload.evidence_refs:
        raise EvidenceValidationError("observed fact requires a source evidence reference")
    if payload.claim_class is ClaimClass.CALCULATED_METRIC and not payload.calculation_refs:
        raise EvidenceValidationError("calculated metric requires a calculation reference")


def validate_finding(finding: AgentFinding, *, context: CommitteeContext) -> None:
    """Validate an attributed finding against its exact run context."""
    if finding.run_id != context.run_id or finding.subject_security_id != context.subject_security_id:
        raise EvidenceValidationError("finding scope does not match committee context")
    if finding.as_of > context.analysis_as_of:
        raise EvidenceValidationError("finding is future-dated")
    refs = (*finding.evidence_refs, *finding.calculation_refs)
    resolved = _validate_refs(
        refs,
        packet=context.evidence_packet,
        claim_class=finding.claim_class,
        data_quality=finding.data_quality,
    )
    _validate_numeric_claims(finding, resolved)


def validate_chair_payload(payload: ModelChairPayload, *, context: CommitteeContext) -> None:
    """Validate chair citations; unsupported synthesis is rejected, not repaired."""
    refs = (*payload.supporting_evidence, *payload.contradicting_evidence)
    resolved = _validate_refs(refs, packet=context.evidence_packet)
    _validate_numeric_claims(payload, resolved)
    if payload.committee_view.value != "insufficient_evidence" and not refs:
        raise EvidenceValidationError("chair conclusion has no evidence")


def validate_context_owner(context: CommitteeContext, owner_id: int) -> None:
    """Enforce owner isolation before any private context is consumed."""
    if context.owner_id != owner_id:
        raise EvidenceValidationError("unauthorized committee context")


__all__ = [
    "EvidenceValidationError",
    "validate_chair_payload",
    "validate_context",
    "validate_context_owner",
    "validate_finding",
    "validate_model_finding",
    "validate_packet",
]
