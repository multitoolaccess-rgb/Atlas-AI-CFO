"""INV-08 bounded AI Investment Committee orchestration.

This module coordinates typed analysis only. It does not persist records, call
providers, mutate portfolio state, create recommendations, or execute actions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Iterable

from pydantic import ValidationError

from .committee_adapters import CommitteeModel, CommitteeModelError, bounded_role_context
from .committee_contracts import (
    AgentFinding,
    CommitteeContext,
    CommitteeFailureCode,
    CommitteeFinding,
    CommitteeModelMetadata,
    CommitteeRun,
    CommitteeStatus,
    ModelChairPayload,
    ModelFindingPayload,
    SpecialistRole,
)
from .confidence import calculate_confidence
from .evidence_validator import (
    EvidenceValidationError,
    validate_chair_payload,
    validate_context,
    validate_context_owner,
    validate_finding,
    validate_model_finding,
)

COMMITTEE_METHODOLOGY_VERSION = "investment-committee/v1"
DEFAULT_SPECIALIST_ROLES = (
    SpecialistRole.FUNDAMENTAL,
    SpecialistRole.TECHNICAL,
    SpecialistRole.MACRO,
    SpecialistRole.QUANT,
    SpecialistRole.PORTFOLIO,
    SpecialistRole.RISK,
)


def _metadata(model: CommitteeModel) -> CommitteeModelMetadata:
    return CommitteeModelMetadata(
        provider=model.provider,
        model=model.model,
        model_version=model.model_version,
        prompt_template_version=model.prompt_template_version,
    )


def _failure_run(
    *,
    context: CommitteeContext,
    model_metadata: CommitteeModelMetadata,
    code: CommitteeFailureCode,
    reason: str,
    created_at: datetime,
    original_run_id: str | None = None,
) -> CommitteeRun:
    sanitized_reason = " ".join(str(reason).split())[:240] or code.value
    return CommitteeRun.with_hash(
        run_id=context.run_id,
        original_run_id=original_run_id,
        owner_id=context.owner_id,
        subject_security_id=context.subject_security_id,
        analysis_as_of=context.analysis_as_of,
        context_hash=context.context_hash,
        specialist_findings=(),
        bull_finding=None,
        bear_finding=None,
        chair_finding=None,
        status=CommitteeStatus.ABSTAINED,
        failure_code=code,
        failure_reason=sanitized_reason,
        created_at=created_at,
        methodology_version=COMMITTEE_METHODOLOGY_VERSION,
        model_metadata=model_metadata,
    )


def _finding(
    *,
    context: CommitteeContext,
    role: SpecialistRole,
    payload: ModelFindingPayload,
    metadata: CommitteeModelMetadata,
) -> AgentFinding:
    raw_id = f"{context.run_id}:{role.value}"
    finding_id = f"finding:{hashlib.sha256(raw_id.encode()).hexdigest()[:32]}"
    return AgentFinding.with_hash(
        finding_id=finding_id,
        run_id=context.run_id,
        specialist=role,
        subject_security_id=context.subject_security_id,
        claim=payload.claim,
        claim_class=payload.claim_class,
        direction=payload.direction,
        evidence_refs=payload.evidence_refs,
        calculation_refs=payload.calculation_refs,
        risks=payload.risks,
        uncertainties=payload.uncertainties,
        data_quality=payload.data_quality,
        numeric_claims=payload.numeric_claims,
        as_of=context.analysis_as_of,
        methodology_version=COMMITTEE_METHODOLOGY_VERSION,
        model_metadata=metadata,
        abstained=payload.abstained,
        abstention_reason=payload.abstention_reason,
    )


def _chair_finding(
    *,
    context: CommitteeContext,
    payload: ModelChairPayload,
    confidence,
    metadata: CommitteeModelMetadata,
    findings: tuple[AgentFinding, ...],
) -> CommitteeFinding:
    finding_id = f"committee:{hashlib.sha256(context.run_id.encode()).hexdigest()[:32]}"
    input_hashes = tuple(sorted({context.context_hash, *(finding.finding_hash for finding in findings)}))
    return CommitteeFinding.with_hash(
        finding_id=finding_id,
        run_id=context.run_id,
        subject_security_id=context.subject_security_id,
        committee_view=payload.committee_view,
        thesis=payload.thesis,
        supporting_evidence=payload.supporting_evidence,
        contradicting_evidence=payload.contradicting_evidence,
        key_risks=payload.key_risks,
        uncertainties=payload.uncertainties,
        invalidation_conditions=payload.invalidation_conditions,
        specialist_disagreement=payload.specialist_disagreement,
        numeric_claims=payload.numeric_claims,
        confidence=confidence,
        analysis_as_of=context.analysis_as_of,
        methodology_version=COMMITTEE_METHODOLOGY_VERSION,
        model_metadata=metadata,
        input_hashes=input_hashes,
    )


def _failed_model_payload(model: CommitteeModel, role: SpecialistRole, context: CommitteeContext) -> dict:
    """Return a safe abstention payload for fixture/model failure tests."""
    return {
        "claim": f"{role.value} analysis unavailable",
        "claim_class": "uncertainty",
        "direction": "unknown",
        "uncertainties": (f"{role.value} model output unavailable",),
        "data_quality": ("unavailable",),
        "abstained": True,
        "abstention_reason": "specialist model unavailable",
    }


def _run_id_for_challenge(original_run: CommitteeRun, context: CommitteeContext) -> None:
    if context.run_id == original_run.run_id:
        raise EvidenceValidationError("challenge must create a new run")
    if context.owner_id != original_run.owner_id:
        raise EvidenceValidationError("challenge owner does not match original run")
    if context.subject_security_id != original_run.subject_security_id:
        raise EvidenceValidationError("challenge subject does not match original run")


def run_committee(
    context: CommitteeContext,
    model: CommitteeModel,
    *,
    specialist_roles: Iterable[SpecialistRole] = DEFAULT_SPECIALIST_ROLES,
    owner_id: int | None = None,
    created_at: datetime | None = None,
) -> CommitteeRun:
    """Run a bounded offline-capable committee pipeline.

    The model sees a role-specific projection and can only return strict JSON
    payloads. Any malformed, unsupported, future, or uncited output abstains;
    no best-effort repair is performed.
    """
    now = created_at or datetime.now(UTC)
    metadata = _metadata(model)
    try:
        if owner_id is not None:
            validate_context_owner(context, owner_id)
        validate_context(context)
    except EvidenceValidationError as exc:
        code = CommitteeFailureCode.TEMPORAL_VIOLATION if "future" in str(exc) or "as_of" in str(exc) else CommitteeFailureCode.INVALID_EVIDENCE
        return _failure_run(context=context, model_metadata=metadata, code=code, reason=str(exc), created_at=now)

    findings: list[AgentFinding] = []
    roles = tuple(dict.fromkeys(role for role in specialist_roles if role not in {SpecialistRole.BULL, SpecialistRole.BEAR, SpecialistRole.CHAIR}))
    for role in roles:
        try:
            raw = model.generate(role=role, context=bounded_role_context(context, role))
            payload = ModelFindingPayload.model_validate(raw)
            validate_model_finding(payload, context=context)
            finding = _finding(context=context, role=role, payload=payload, metadata=metadata)
            validate_finding(finding, context=context)
            findings.append(finding)
        except (CommitteeModelError, ValidationError, EvidenceValidationError, TypeError, ValueError) as exc:
            return _failure_run(
                context=context,
                model_metadata=metadata,
                code=(
                    CommitteeFailureCode.SPECIALIST_FAILURE
                    if isinstance(exc, CommitteeModelError)
                    else CommitteeFailureCode.EVIDENCE_VALIDATION_FAILURE
                    if isinstance(exc, EvidenceValidationError)
                    else CommitteeFailureCode.SCHEMA_VALIDATION_FAILURE
                ),
                reason=str(exc),
                created_at=now,
            )

    # Bear and Bull are separate, attributable findings and receive the same
    # frozen packet. A challenge cannot silently discard either perspective.
    challenge_findings: dict[SpecialistRole, AgentFinding] = {}
    for role in (SpecialistRole.BEAR, SpecialistRole.BULL):
        try:
            raw = model.generate(
                role=role,
                context=bounded_role_context(context, role, prior_findings=tuple(findings)),
            )
            payload = ModelFindingPayload.model_validate(raw)
            validate_model_finding(payload, context=context)
            finding = _finding(context=context, role=role, payload=payload, metadata=metadata)
            validate_finding(finding, context=context)
            challenge_findings[role] = finding
            findings.append(finding)
        except (CommitteeModelError, ValidationError, EvidenceValidationError, TypeError, ValueError) as exc:
            return _failure_run(
                context=context,
                model_metadata=metadata,
                code=(
                    CommitteeFailureCode.SPECIALIST_FAILURE
                    if isinstance(exc, CommitteeModelError)
                    else CommitteeFailureCode.EVIDENCE_VALIDATION_FAILURE
                    if isinstance(exc, EvidenceValidationError)
                    else CommitteeFailureCode.SCHEMA_VALIDATION_FAILURE
                ),
                reason=str(exc),
                created_at=now,
            )

    all_findings = tuple(findings)
    try:
        raw_chair = model.generate(
            role=SpecialistRole.CHAIR,
            context=bounded_role_context(context, SpecialistRole.CHAIR, prior_findings=all_findings),
        )
        chair_payload = ModelChairPayload.model_validate(raw_chair)
        validate_chair_payload(chair_payload, context=context)
        confidence = calculate_confidence(
            packet=context.evidence_packet,
            findings=all_findings,
            chair_refs=tuple(dict.fromkeys((*chair_payload.supporting_evidence, *chair_payload.contradicting_evidence))),
        )
        chair = _chair_finding(
            context=context,
            payload=chair_payload,
            confidence=confidence,
            metadata=metadata,
            findings=all_findings,
        )
    except (CommitteeModelError, ValidationError, EvidenceValidationError, TypeError, ValueError) as exc:
        return _failure_run(
            context=context,
            model_metadata=metadata,
            code=CommitteeFailureCode.EVIDENCE_VALIDATION_FAILURE if isinstance(exc, EvidenceValidationError) else CommitteeFailureCode.SCHEMA_VALIDATION_FAILURE,
            reason=str(exc),
            created_at=now,
        )

    return CommitteeRun.with_hash(
        run_id=context.run_id,
        original_run_id=None,
        owner_id=context.owner_id,
        subject_security_id=context.subject_security_id,
        analysis_as_of=context.analysis_as_of,
        context_hash=context.context_hash,
        specialist_findings=all_findings,
        bull_finding=challenge_findings[SpecialistRole.BULL],
        bear_finding=challenge_findings[SpecialistRole.BEAR],
        chair_finding=chair,
        status=CommitteeStatus.COMPLETE,
        failure_code=None,
        failure_reason=None,
        created_at=now,
        methodology_version=COMMITTEE_METHODOLOGY_VERSION,
        model_metadata=metadata,
    )


def challenge_committee(
    original_run: CommitteeRun,
    context: CommitteeContext,
    model: CommitteeModel,
    *,
    owner_id: int | None = None,
    created_at: datetime | None = None,
) -> CommitteeRun:
    """Create a new immutable challenge run linked to the original run."""
    _run_id_for_challenge(original_run, context)
    if owner_id is not None and owner_id != original_run.owner_id:
        raise EvidenceValidationError("unauthorized committee challenge")
    result = run_committee(context, model, owner_id=owner_id, created_at=created_at)
    values = result.model_dump()
    values["original_run_id"] = original_run.run_id
    values.pop("run_hash", None)
    return CommitteeRun.with_hash(**values)


__all__ = [
    "COMMITTEE_METHODOLOGY_VERSION",
    "DEFAULT_SPECIALIST_ROLES",
    "challenge_committee",
    "run_committee",
]
