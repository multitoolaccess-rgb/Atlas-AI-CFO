"""Deterministic confidence authority for INV-08.

The model can describe uncertainty, but it cannot author the confidence score.
This calculator is intentionally small and versioned until later calibration
work in INV-12 provides historical outcome data.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .committee_contracts import (
    AgentFinding,
    CommitteeDataQuality,
    ConfidenceAssessment,
    ConfidenceBand,
    EvidencePacket,
    FindingDirection,
)

CONFIDENCE_METHODOLOGY_VERSION = "committee-confidence/v1"


def calculate_confidence(
    *,
    packet: EvidencePacket,
    findings: Iterable[AgentFinding],
    chair_refs: tuple[str, ...] = (),
) -> ConfidenceAssessment:
    """Calculate a reproducible bounded confidence assessment.

    The inputs are evidence coverage, packet quality, and agreement between
    non-abstained specialist directions. This is an analysis reliability score,
    not a probability of investment return.
    """
    findings = tuple(finding for finding in findings if not finding.abstained)
    cited = {ref for finding in findings for ref in (*finding.evidence_refs, *finding.calculation_refs)}
    cited.update(chair_refs)
    packet_ids = {item.evidence_id for item in packet.items}
    coverage = Decimal(len(cited & packet_ids)) / Decimal(len(packet_ids)) if packet_ids else Decimal(0)

    unavailable_states = {
        CommitteeDataQuality.UNKNOWN,
        CommitteeDataQuality.MISSING,
        CommitteeDataQuality.STALE,
        CommitteeDataQuality.INSUFFICIENT_HISTORY,
        CommitteeDataQuality.UNAVAILABLE,
        CommitteeDataQuality.UNRESOLVED,
        CommitteeDataQuality.UNSUPPORTED,
    }
    quality = Decimal(0)
    if packet.items:
        quality = Decimal(sum(1 for item in packet.items if item.reference.state.value == "observed")) / Decimal(len(packet.items))
        if any(item.reference.state.value == "stale" for item in packet.items):
            quality = min(quality, Decimal("0.5"))

    directional = [finding.direction for finding in findings if finding.direction is not FindingDirection.UNKNOWN]
    if directional:
        counts = {direction: directional.count(direction) for direction in set(directional)}
        agreement = Decimal(max(counts.values())) / Decimal(len(directional))
    else:
        agreement = Decimal(0)

    score_decimal = (coverage * Decimal(50)) + (quality * Decimal(30)) + (agreement * Decimal(20))
    score = max(0, min(100, int(score_decimal.to_integral_value())))
    limitations: list[str] = []
    drivers: list[str] = []
    if coverage < 1:
        limitations.append("not all packet evidence was cited")
    if quality < 1:
        limitations.append("one or more evidence items are not observed")
    if not findings:
        limitations.append("no specialist finding was available")
    if len(set(directional)) > 1:
        limitations.append("specialist directions conflict")
    if coverage >= Decimal("0.8"):
        drivers.append("broad evidence coverage")
    if agreement >= Decimal("0.75"):
        drivers.append("specialist findings are mostly aligned")
    if not drivers:
        drivers.append("bounded evidence and specialist agreement inputs")

    if score == 0:
        band = ConfidenceBand.UNAVAILABLE
    elif score < 50:
        band = ConfidenceBand.LOW
    elif score < 80:
        band = ConfidenceBand.MEDIUM
    else:
        band = ConfidenceBand.HIGH
    return ConfidenceAssessment(
        score=score,
        band=band,
        evidence_coverage=format(coverage.normalize(), "f"),
        valid_evidence_quality=format(quality.normalize(), "f"),
        specialist_agreement=format(agreement.normalize(), "f"),
        drivers=tuple(drivers),
        limitations=tuple(limitations),
        methodology_version=CONFIDENCE_METHODOLOGY_VERSION,
    )


__all__ = ["CONFIDENCE_METHODOLOGY_VERSION", "calculate_confidence"]
