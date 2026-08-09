"""Append-only outcome-evaluation write service with idempotent-replay semantics.

Phase 3 Slice 1 commit-3 application-layer outcome evaluation service.

Semantics enforced here:

* **Raw evidence is NEVER accepted, persisted, logged, or echoed.**  The
  ``evidence_reference_hash`` is **server-derived** from an authoritative
  bounded source (canonical evaluation identity + source kind).  The
  caller provides ``evidence_source_kind`` (bounded allowlist) plus the
  evaluation context; the hash is computed by the service, never trusted
  from client input.

* **Ownership-before-existence.**  Goal, recommendation, and decision
  journal entry ownership are verified BEFORE any persistence decision.
  Cross-user access returns sanitized :class:`GoalNotFoundError` /
  :class:`RecommendationNotFoundError` /
  :class:`DecisionNotFoundError` that a non-owner cannot use to
  distinguish ``missing`` from ``cross-user``.

* **Decision must already be accepted.**  An outcome evaluation can only
  be recorded against a decision journal entry with
  ``decision_action='accept'``.  Rejected or deferred decisions cannot
  be evaluated.

* **Lifecycle-state evidence contract.**  ``pending`` and
  ``not_yet_measurable`` forbid all evidence fields.  ``measured``
  requires all evidence fields.  The DB CHECK constraint is the final
  defence; the service enforces the same contract for defense-in-depth.

* **Privacy contract.**  ``evidence_source_kind`` is a strict
  allowlisted enum and ``evidence_reference_hash`` is a server-derived
  64-char lowercase SHA-256 hex.  The evidence REFERENCE is the only
  pointer to where evidence lives, and it is hash-only: no raw URLs,
  filenames, account IDs, or transaction identifiers are ever accepted
  or stored as references.  ``result_json`` and ``explanation`` carry
  the measured outcome data and its human explanation (size-bounded,
  not content-scrubbed); they ARE the outcome, never evidence
  references.

* **Idempotent-replay + cross-row conflict detection.**  Same raw
  Idempotency-Key + same canonical request = same row
  (``replayed=True``).  Same key + DIFFERENT canonical request
  raises :class:`OutcomeConflictError` carrying only the stable
  ``current_etag`` of the existing row (no raw UUID, no raw key).

* **Race handling.**  Two parallel writers with the same canonical
  request race on the UNIQUE constraint.  The service catches the
  integrity error, looks up the committed winner, and replays the
  loser's request as ``replayed=True``.

* **Immutable DB protections remain effective through service ops.**
  The service never issues UPDATE or DELETE against outcome_evaluations.
  The Phase 3 SQL triggers remain the final defence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.forecasts.outcome_evaluation_schemas import OUTCOME_EVALUATION_SCHEMA_VERSION
from app.models import (
    DecisionJournalEntry,
    Goal,
    OutcomeEvaluation,
    Recommendation,
)
from app.models.decision_journal_identities import (
    canonical_idempotency_key_hash,
    canonical_digest,
    outcome_evaluation_id_for,
)


# ---------------------------------------------------------------------------
# Allowlists + constants
# ---------------------------------------------------------------------------

_LIFECYCLE_ALLOWED: Final[frozenset[str]] = frozenset({
    "pending",
    "not_yet_measurable",
    "measured",
})

_EVIDENCE_SOURCE_KIND_ALLOWED: Final[frozenset[str]] = frozenset({
    "forecast_projection",
    "account_balance_delta",
    "transaction_pattern",
})

# Fields the CALLER must supply for a measured record.  The
# evidence_reference_hash is deliberately absent: it is server-derived
# from the canonical identity after these fields validate.
_MEASURED_CLIENT_FIELDS: Final[frozenset[str]] = frozenset({
    "evidence_source_kind",
    "measurement_window_start",
    "measurement_window_end",
    "result_json",
    "confidence",
    "explanation",
})

# The FULL measured evidence set the DB CHECK requires, including the
# server-derived evidence_reference_hash.
_MEASURED_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset({
    "evidence_source_kind",
    "evidence_reference_hash",
    "measurement_window_start",
    "measurement_window_end",
    "result_json",
    "confidence",
    "explanation",
})

_OUTCOME_ETAG_VERSION: Final[str] = "1"

# Namespace for server-derived evidence_reference_hash.  The hash is
# NEVER a raw URL, filename, account ID, or transaction payload; it is
# a deterministic digest of the canonical evaluation identity + source kind.
_EVIDENCE_REF_NAMESPACE: Final[bytes] = b"atlas-evidence-ref/v1:"

_NOW_FN = lambda: datetime.now(timezone.utc)  # noqa: E731


# ---------------------------------------------------------------------------
# Exceptions (code-only contract surface — no raw evidence leaked)
# ---------------------------------------------------------------------------


class OutcomeError(Exception):
    """Base class.  The ``code`` attribute is the only safe contract surface."""

    code: str = "outcome_invalid"


class GoalNotFoundError(OutcomeError):
    code: Final[str] = "goal_not_found"


class RecommendationNotFoundError(OutcomeError):
    code: Final[str] = "recommendation_not_found"


class DecisionNotFoundError(OutcomeError):
    """Decision not found or not accepted (indistinguishable)."""

    code: Final[str] = "decision_not_found"


class OutcomeConflictError(OutcomeError):
    """Same Idempotency-Key on a different canonical request.

    Carries ONLY the stable ``current_etag`` of the existing row.
    No raw key, no raw payload, no raw evidence.
    """

    code: Final[str] = "outcome_conflict"

    def __init__(self, current_etag: str) -> None:
        super().__init__("outcome_conflict")
        self.current_etag = current_etag


class IdempotencyKeyRequiredError(OutcomeError):
    code: Final[str] = "idempotency_key_required"


class IdempotencyKeyInvalidError(OutcomeError):
    code: Final[str] = "idempotency_key_invalid"


class LifecycleError(OutcomeError):
    """Lifecycle-state evidence contract violation at the service layer."""

    code: Final[str] = "lifecycle_violation"


class EvidenceSourceKindError(OutcomeError):
    """Non-allowlisted evidence_source_kind rejected at the service layer."""

    code: Final[str] = "evidence_source_kind_invalid"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutcomeWriteResult:
    entry: OutcomeEvaluation
    replayed: bool
    conflict: bool
    current_etag: str


# ---------------------------------------------------------------------------
# Helpers (public so tests can exercise them directly)
# ---------------------------------------------------------------------------


def outcome_etag_for(entry_id: str) -> str:
    """Stable outcome ETag for an evaluation row."""
    return f"{entry_id}-o{_OUTCOME_ETAG_VERSION}"


def _now() -> datetime:
    return _NOW_FN()


def _derive_evidence_reference_hash(
    *,
    user_id: int,
    goal_id: int,
    recommendation_id: str,
    decision_journal_entry_id: str,
    evidence_source_kind: str,
    measurement_window_start: datetime,
    measurement_window_end: datetime,
) -> str:
    """Server-derive the evidence_reference_hash from authoritative bounded inputs.

    The hash is NEVER a raw URL, filename, account ID, or transaction
    payload.  It is a deterministic SHA-256 digest of the canonical
    evaluation identity + source kind + measurement window.  This
    ensures:

    1. The hash is server-derived, not client-supplied.
    2. The same canonical tuple always produces the same hash.
    3. No raw evidence reference is ever persisted, logged, or echoed —
       only its digest.
    """
    inputs = {
        "decision_journal_entry_id": decision_journal_entry_id,
        "evidence_source_kind": evidence_source_kind,
        "goal_id": goal_id,
        "measurement_window_end": measurement_window_end.isoformat(),
        "measurement_window_start": measurement_window_start.isoformat(),
        "recommendation_id": recommendation_id,
        "user_id": user_id,
    }
    return canonical_digest(inputs, _EVIDENCE_REF_NAMESPACE).hex()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OutcomeEvaluationService:
    """Append-only outcome evaluation write transaction. Owns commit / rollback."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Authorization (ownership-before-existence)
    # ------------------------------------------------------------------

    def _authorize_goal_ownership(self, *, user_id: int, goal_id: int) -> Goal:
        goal = self._session.get(Goal, goal_id)
        if goal is None or goal.user_id != user_id:
            raise GoalNotFoundError("goal not accessible")
        return goal

    def _authorize_recommendation_ownership(
        self, *, user_id: int, goal_id: int, recommendation_id: str,
    ) -> Recommendation:
        rec = self._session.get(Recommendation, recommendation_id)
        if rec is None or rec.user_id != user_id or rec.goal_id != goal_id:
            raise RecommendationNotFoundError("recommendation not accessible")
        return rec

    def _authorize_decision_accepted(
        self,
        *,
        user_id: int,
        goal_id: int,
        recommendation_id: str,
        decision_journal_entry_id: str,
    ) -> DecisionJournalEntry:
        """Verify the decision exists, is owned by the user, is for the right
        recommendation, and was an ``accept`` action.

        A rejected or deferred decision cannot carry an outcome evaluation.
        The error does not distinguish missing from cross-user or
        non-accepted (the sanitized surface).
        """
        decision = self._session.get(DecisionJournalEntry, decision_journal_entry_id)
        if (
            decision is None
            or decision.user_id != user_id
            or decision.goal_id != goal_id
            or decision.recommendation_id != recommendation_id
            or decision.decision_action != "accept"
        ):
            raise DecisionNotFoundError("decision not accessible or not accepted")
        return decision

    # ------------------------------------------------------------------
    # Lifecycle validation (defense-in-depth before the DB CHECK)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_lifecycle_evidence_contract(
        *,
        lifecycle: str,
        required_fields: frozenset[str],
        evidence_source_kind: str | None,
        evidence_reference_hash: str | None,
        measurement_window_start,
        measurement_window_end,
        result_json: str | None,
        confidence: str | None,
        explanation: str | None,
    ) -> None:
        """Enforce the lifecycle-state evidence contract at the service layer.

        ``required_fields`` distinguishes the caller-supplied set (checked
        before derivation) from the full set including the server-derived
        ``evidence_reference_hash`` (checked after derivation).

        Defense-in-depth: the DB CHECK constraint is the final defence.
        """
        if lifecycle in ("pending", "not_yet_measurable"):
            has_evidence = any(v is not None for v in (
                evidence_source_kind, evidence_reference_hash,
                measurement_window_start, measurement_window_end,
                result_json, confidence, explanation,
            ))
            if has_evidence:
                raise LifecycleError(
                    f"{lifecycle} lifecycle must not carry evidence fields"
                )
        elif lifecycle == "measured":
            missing = []
            for field in required_fields:
                if locals()[field] is None:
                    missing.append(field)
            if missing:
                raise LifecycleError(
                    f"measured lifecycle requires evidence fields: {', '.join(missing)}"
                )
        else:
            raise LifecycleError(f"unknown lifecycle: {lifecycle!r}")

    # ------------------------------------------------------------------
    # Evidence source kind validation (defense-in-depth before the DB CHECK)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_evidence_source_kind(kind: str | None) -> None:
        if kind is not None and kind not in _EVIDENCE_SOURCE_KIND_ALLOWED:
            raise EvidenceSourceKindError(
                f"evidence_source_kind must be one of {sorted(_EVIDENCE_SOURCE_KIND_ALLOWED)}"
            )

    # ------------------------------------------------------------------
    # Idempotent raw-key hashing (canonical pre-storage form)
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_idempotency_key(raw_key: str) -> str:
        if not isinstance(raw_key, str) or not raw_key:
            raise IdempotencyKeyRequiredError("missing")
        if len(raw_key) > 255:
            raise IdempotencyKeyInvalidError("too long")
        if any(ord(c) < 0x21 or ord(c) > 0x7E for c in raw_key):
            raise IdempotencyKeyInvalidError("non-printable characters")
        return canonical_idempotency_key_hash(raw_key)

    # ------------------------------------------------------------------
    # Lookup paths
    # ------------------------------------------------------------------

    def _lookup_by_pk(self, evaluation_id: str) -> OutcomeEvaluation | None:
        return self._session.get(OutcomeEvaluation, evaluation_id)

    def _lookup_by_idempotency_key(
        self, *, user_id: int, idempotency_key_hash: str,
    ) -> OutcomeEvaluation | None:
        stmt = select(OutcomeEvaluation).where(
            OutcomeEvaluation.user_id == user_id,
            OutcomeEvaluation.idempotency_key_hash == idempotency_key_hash,
        )
        return self._session.scalar(stmt)

    @staticmethod
    def _canonical_fields_match(
        existing: OutcomeEvaluation,
        *,
        recommendation_id: str,
        decision_journal_entry_id: str,
        lifecycle: str,
        schema_version: str,
        evidence_source_kind: str | None,
        measurement_window_start,
        measurement_window_end,
        result_json: str | None,
        confidence: str | None,
        explanation: str | None,
    ) -> bool:
        if existing.recommendation_id != recommendation_id:
            return False
        if existing.decision_journal_entry_id != decision_journal_entry_id:
            return False
        if existing.lifecycle != lifecycle:
            return False
        if existing.schema_version != schema_version:
            return False
        # The measured evidence payload is part of the canonical request
        # identity.  A retry with the same idempotency key but a different
        # evidence payload must NOT silently replay the prior row.
        if (existing.evidence_source_kind or None) != (evidence_source_kind or None):
            return False
        if (existing.measurement_window_start or None) != (measurement_window_start or None):
            return False
        if (existing.measurement_window_end or None) != (measurement_window_end or None):
            return False
        if (existing.result_json or None) != (result_json or None):
            return False
        if (existing.confidence or None) != (confidence or None):
            return False
        if (existing.explanation or None) != (explanation or None):
            return False
        return True

    # ------------------------------------------------------------------
    # Single-attempt insert
    # ------------------------------------------------------------------

    def _persist_once(
        self,
        *,
        evaluation_id: str,
        user_id: int,
        goal_id: int,
        recommendation_id: str,
        decision_journal_entry_id: str,
        lifecycle: str,
        schema_version: str,
        idempotency_key_hash: str,
        evidence_source_kind: str | None,
        evidence_reference_hash: str | None,
        measurement_window_start=None,
        measurement_window_end=None,
        result_json: str | None,
        confidence: str | None,
        explanation: str | None,
    ) -> OutcomeEvaluation:
        entry = OutcomeEvaluation(
            id=evaluation_id,
            recommendation_id=recommendation_id,
            decision_journal_entry_id=decision_journal_entry_id,
            user_id=user_id,
            goal_id=goal_id,
            lifecycle=lifecycle,
            schema_version=schema_version,
            idempotency_key_hash=idempotency_key_hash,
            currency="USD",
            evidence_source_kind=evidence_source_kind,
            evidence_reference_hash=evidence_reference_hash,
            measurement_window_start=measurement_window_start,
            measurement_window_end=measurement_window_end,
            result_json=result_json,
            confidence=confidence,
            explanation=explanation,
            recorded_at=_now(),
        )
        self._session.add(entry)
        self._session.flush()
        return entry

    # ------------------------------------------------------------------
    # Race recovery
    # ------------------------------------------------------------------

    def _recover_database_winner(
        self,
        *,
        user_id: int,
        idempotency_key_hash: str,
        evaluation_id: str,
    ) -> OutcomeEvaluation | None:
        by_pk = self._session.get(OutcomeEvaluation, evaluation_id)
        if by_pk is not None:
            return by_pk
        # The losing insert may have collided on the UNIQUE
        # (user_id, recommendation_id, decision_journal_entry_id,
        # idempotency_key_hash) constraint against a concurrent writer whose
        # canonical request diverged (e.g. a different lifecycle ⇒ different
        # deterministic PK).  Fall back to the cross-row idempotency-key
        # lookup so the caller surfaces that winner as an
        # OutcomeConflictError instead of a generic persistence error.
        return self._lookup_by_idempotency_key(
            user_id=user_id, idempotency_key_hash=idempotency_key_hash,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        user_id: int,
        goal_id: int,
        recommendation_id: str,
        decision_journal_entry_id: str,
        raw_idempotency_key: str,
        lifecycle: str,
        schema_version: str = OUTCOME_EVALUATION_SCHEMA_VERSION,
        evidence_source_kind: str | None = None,
        measurement_window_start=None,
        measurement_window_end=None,
        result_json: str | None = None,
        confidence: str | None = None,
        explanation: str | None = None,
    ) -> OutcomeWriteResult:
        """Persist an outcome evaluation row with idempotent-replay + conflict semantics.

        The ``raw_idempotency_key`` argument holds the client-supplied
        Idempotency-Key header value verbatim; the service hashes it
        BEFORE persistence and never stores the raw form.

        The ``evidence_reference_hash`` is **server-derived** from the
        canonical evaluation identity + source kind + measurement window.
        No raw evidence reference is ever accepted, persisted, logged, or
        echoed; ``result_json`` / ``explanation`` carry the measured
        outcome data itself, never an evidence pointer.
        """
        # 1. Bounded lifecycle token.
        if lifecycle not in _LIFECYCLE_ALLOWED:
            raise LifecycleError(f"lifecycle must be one of {sorted(_LIFECYCLE_ALLOWED)}")

        # 2. Idempotency key is required.
        idempotency_key_hash = self._hash_idempotency_key(raw_idempotency_key)

        # 3. Evidence source kind validation (defense-in-depth).
        self._validate_evidence_source_kind(evidence_source_kind)

        # 4. Lifecycle-state evidence contract (defense-in-depth).
        self._validate_lifecycle_evidence_contract(
            lifecycle=lifecycle,
            required_fields=_MEASURED_CLIENT_FIELDS,
            evidence_source_kind=evidence_source_kind,
            evidence_reference_hash=None,  # not yet derived
            measurement_window_start=measurement_window_start,
            measurement_window_end=measurement_window_end,
            result_json=result_json,
            confidence=confidence,
            explanation=explanation,
        )

        # 5. Server-derive the evidence_reference_hash (NEVER from client input).
        if lifecycle == "measured":
            evidence_reference_hash = _derive_evidence_reference_hash(
                user_id=user_id,
                goal_id=goal_id,
                recommendation_id=recommendation_id,
                decision_journal_entry_id=decision_journal_entry_id,
                evidence_source_kind=evidence_source_kind,
                measurement_window_start=measurement_window_start,
                measurement_window_end=measurement_window_end,
            )
            # Run the lifecycle contract check again with the derived hash
            # to verify the full set.
            self._validate_lifecycle_evidence_contract(
                lifecycle=lifecycle,
                required_fields=_MEASURED_REQUIRED_FIELDS,
                evidence_source_kind=evidence_source_kind,
                evidence_reference_hash=evidence_reference_hash,
                measurement_window_start=measurement_window_start,
                measurement_window_end=measurement_window_end,
                result_json=result_json,
                confidence=confidence,
                explanation=explanation,
            )
        else:
            evidence_reference_hash = None

        # 6. Deterministic PK (must come from hashed key + canonical inputs).
        evaluation_id = outcome_evaluation_id_for(
            user_id=user_id,
            goal_id=goal_id,
            recommendation_id=recommendation_id,
            decision_journal_entry_id=decision_journal_entry_id,
            lifecycle=lifecycle,
            idempotency_key_hash=idempotency_key_hash,
            schema_version=schema_version,
        )

        # 7. Authorization BEFORE any persistence decision.
        self._authorize_goal_ownership(user_id=user_id, goal_id=goal_id)
        self._authorize_recommendation_ownership(
            user_id=user_id, goal_id=goal_id, recommendation_id=recommendation_id,
        )
        self._authorize_decision_accepted(
            user_id=user_id,
            goal_id=goal_id,
            recommendation_id=recommendation_id,
            decision_journal_entry_id=decision_journal_entry_id,
        )

        # 8. PRIMARY lookup: same canonical request => same row => replay.
        existing_by_pk = self._lookup_by_pk(evaluation_id=evaluation_id)
        if existing_by_pk is not None:
            if not self._canonical_fields_match(
                existing_by_pk,
                recommendation_id=recommendation_id,
                decision_journal_entry_id=decision_journal_entry_id,
                lifecycle=lifecycle,
                schema_version=schema_version,
                evidence_source_kind=evidence_source_kind,
                measurement_window_start=measurement_window_start,
                measurement_window_end=measurement_window_end,
                result_json=result_json,
                confidence=confidence,
                explanation=explanation,
            ):
                raise OutcomeConflictError(
                    current_etag=outcome_etag_for(existing_by_pk.id),
                )
            return OutcomeWriteResult(
                entry=existing_by_pk,
                replayed=True,
                conflict=False,
                current_etag=outcome_etag_for(existing_by_pk.id),
            )

        # 9. Cross-row CONFLICT lookup: same idempotency key hash, different request.
        existing_by_key = self._lookup_by_idempotency_key(
            user_id=user_id, idempotency_key_hash=idempotency_key_hash,
        )
        if existing_by_key is not None and not self._canonical_fields_match(
            existing_by_key,
            recommendation_id=recommendation_id,
            decision_journal_entry_id=decision_journal_entry_id,
            lifecycle=lifecycle,
            schema_version=schema_version,
            evidence_source_kind=evidence_source_kind,
            measurement_window_start=measurement_window_start,
            measurement_window_end=measurement_window_end,
            result_json=result_json,
            confidence=confidence,
            explanation=explanation,
        ):
            raise OutcomeConflictError(
                current_etag=outcome_etag_for(existing_by_key.id),
            )

        # 10. Insert; on race, retry the PK lookup to surface the commit winner.
        try:
            entry = self._persist_once(
                evaluation_id=evaluation_id,
                user_id=user_id,
                goal_id=goal_id,
                recommendation_id=recommendation_id,
                decision_journal_entry_id=decision_journal_entry_id,
                lifecycle=lifecycle,
                schema_version=schema_version,
                idempotency_key_hash=idempotency_key_hash,
                evidence_source_kind=evidence_source_kind,
                evidence_reference_hash=evidence_reference_hash,
                measurement_window_start=measurement_window_start,
                measurement_window_end=measurement_window_end,
                result_json=result_json,
                confidence=confidence,
                explanation=explanation,
            )
            self._session.commit()
            return OutcomeWriteResult(
                entry=entry,
                replayed=False,
                conflict=False,
                current_etag=outcome_etag_for(entry.id),
            )
        except (
            GoalNotFoundError,
            RecommendationNotFoundError,
            DecisionNotFoundError,
            IdempotencyKeyRequiredError,
            IdempotencyKeyInvalidError,
            LifecycleError,
            EvidenceSourceKindError,
        ):
            self._session.rollback()
            raise
        except (IntegrityError, OperationalError):
            self._session.rollback()
            recovered = self._recover_database_winner(
                user_id=user_id,
                idempotency_key_hash=idempotency_key_hash,
                evaluation_id=evaluation_id,
            )
            if recovered is None:
                raise OutcomeError("outcome persistence conflict")
            if not self._canonical_fields_match(
                recovered,
                recommendation_id=recommendation_id,
                decision_journal_entry_id=decision_journal_entry_id,
                lifecycle=lifecycle,
                schema_version=schema_version,
                evidence_source_kind=evidence_source_kind,
                measurement_window_start=measurement_window_start,
                measurement_window_end=measurement_window_end,
                result_json=result_json,
                confidence=confidence,
                explanation=explanation,
            ):
                raise OutcomeConflictError(
                    current_etag=outcome_etag_for(recovered.id),
                )
            self._session.commit()
            return OutcomeWriteResult(
                entry=recovered,
                replayed=True,
                conflict=False,
                current_etag=outcome_etag_for(recovered.id),
            )


__all__ = [
    "OutcomeError",
    "GoalNotFoundError",
    "RecommendationNotFoundError",
    "DecisionNotFoundError",
    "OutcomeConflictError",
    "IdempotencyKeyRequiredError",
    "IdempotencyKeyInvalidError",
    "LifecycleError",
    "EvidenceSourceKindError",
    "OutcomeWriteResult",
    "OutcomeEvaluationService",
    "outcome_etag_for",
    "_derive_evidence_reference_hash",
]
