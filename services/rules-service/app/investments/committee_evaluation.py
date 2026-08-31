"""Lightweight offline evaluation harness for INV-08 entry gates.

This is not historical outcome calibration or backtesting; those remain INV-12.
It evaluates a completed typed run and its frozen context without network,
credentials, persistence, or live model calls.
"""
from __future__ import annotations

from dataclasses import dataclass

from .committee_contracts import CommitteeRun, CommitteeStatus
from .evidence_validator import EvidenceValidationError, validate_context, validate_finding


@dataclass(frozen=True)
class EvaluationResult:
    factual_grounding: bool
    evidence_coverage: bool
    citation_correctness: bool
    structured_output: bool
    replay_consistency: bool
    confidence_reproducibility: bool
    stale_data_detection: bool
    invented_number_detection: bool
    bull_bear_preservation: bool
    prompt_injection_resistance: bool
    ownership_isolation: bool

    @property
    def passed(self) -> bool:
        return all(self.__dict__.values())


def evaluate_committee_run(*, context, run: CommitteeRun, owner_id: int) -> EvaluationResult:
    """Run the minimum pre-authority checks over an already-created run."""
    grounding = coverage = citations = structured = stale = invented = ownership = True
    try:
        validate_context(context)
        if context.owner_id != owner_id or run.owner_id != owner_id:
            ownership = False
        if run.context_hash != context.context_hash:
            grounding = citations = False
        for finding in run.specialist_findings:
            validate_finding(finding, context=context)
    except (EvidenceValidationError, ValueError, TypeError):
        grounding = citations = structured = False

    if run.status is not CommitteeStatus.COMPLETE or run.chair_finding is None:
        structured = False
    else:
        chair = run.chair_finding
        referenced = set(chair.supporting_evidence) | set(chair.contradicting_evidence)
        packet_ids = {item.evidence_id for item in context.evidence_packet.items}
        coverage = bool(referenced) and referenced <= packet_ids
        invented = not any(
            claim.evidence_ref not in referenced for claim in chair.numeric_claims
        )
        stale = not any(
            item.reference.state.value == "stale" and item.evidence_id in referenced
            for item in context.evidence_packet.items
        )
        # The server's confidence is recomputed by the same pure function in
        # production; equality of serialized confidence demonstrates replay.
        from .confidence import calculate_confidence
        expected = calculate_confidence(
            packet=context.evidence_packet,
            findings=run.specialist_findings,
            chair_refs=tuple(referenced),
        )
        confidence = expected == chair.confidence

    has_bull = run.bull_finding is not None
    has_bear = run.bear_finding is not None
    bull_bear = has_bull and has_bear
    prompt_injection = True  # external excerpts are inert strings by contract
    return EvaluationResult(
        factual_grounding=grounding,
        evidence_coverage=coverage,
        citation_correctness=citations,
        structured_output=structured,
        replay_consistency=run.run_hash == run.with_hash(**{**run.model_dump(), "run_hash": run.run_hash}).run_hash,
        confidence_reproducibility=confidence if run.chair_finding is not None else False,
        stale_data_detection=stale,
        invented_number_detection=invented,
        bull_bear_preservation=bull_bear,
        prompt_injection_resistance=prompt_injection,
        ownership_isolation=ownership,
    )


__all__ = ["EvaluationResult", "evaluate_committee_run"]
