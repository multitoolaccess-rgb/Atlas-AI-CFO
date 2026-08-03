"""Append-only, evidence-gated outcome evaluations for accepted decisions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.forecasts.decision_journal_service import IdempotencyKeyInvalidError, IdempotencyKeyRequiredError
from app.models import DecisionJournalEntry, Goal, OutcomeEvaluation, Recommendation
from app.models.decision_journal_identities import canonical_idempotency_key_hash, outcome_evaluation_id_for

OUTCOME_EVALUATION_SCHEMA_VERSION: Final[str] = "atlas-outcome-evaluation/v1"
_LIFECYCLES: Final[frozenset[str]] = frozenset({"pending", "not_yet_measurable", "measured"})
_CONFIDENCES: Final[frozenset[str]] = frozenset({"high", "medium", "low"})
_SENSITIVE_TOKENS: Final[tuple[str, ...]] = (
    "balance", "amount", "contribution", "transaction", "snapshot", "account",
    "token", "secret", "password", "api_key", "apikey",
)


class OutcomeEvaluationError(Exception):
    code: str = "outcome_evaluation_invalid"


class OutcomeEvaluationNotFoundError(OutcomeEvaluationError):
    code = "outcome_evaluation_not_found"


class OutcomeEvaluationConflictError(OutcomeEvaluationError):
    code = "outcome_evaluation_conflict"


@dataclass(frozen=True)
class OutcomeEvaluationWriteResult:
    evaluation: OutcomeEvaluation
    replayed: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _idempotency_hash(raw_key: str) -> str:
    if not isinstance(raw_key, str) or not raw_key:
        raise IdempotencyKeyRequiredError("missing")
    if len(raw_key) > 255 or any(ord(char) < 0x21 or ord(char) > 0x7E for char in raw_key):
        raise IdempotencyKeyInvalidError("invalid")
    return canonical_idempotency_key_hash(raw_key)


def _safe_evidence_map(value: Mapping[str, str] | None) -> Mapping[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or not 1 <= len(value) <= 8:
        raise OutcomeEvaluationNotFoundError("invalid evidence map")
    safe: dict[str, str] = {}
    for key, item in value.items():
        if (not isinstance(key, str) or not isinstance(item, str) or not key
                or len(key) > 64 or len(item) > 512
                or any(token in key.lower() for token in _SENSITIVE_TOKENS)):
            raise OutcomeEvaluationNotFoundError("invalid evidence map")
        safe[key] = item
    return safe


class OutcomeEvaluationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self, *, user_id: int, goal_id: int, recommendation_id: str,
        decision_journal_entry_id: str, lifecycle: str, raw_idempotency_key: str,
        authoritative_evidence_reference: str | None = None,
        measurement_window_start: datetime | None = None,
        measurement_window_end: datetime | None = None,
        inputs: Mapping[str, str] | None = None, result: Mapping[str, str] | None = None,
        confidence: str | None = None, explanation: str | None = None,
    ) -> OutcomeEvaluationWriteResult:
        if lifecycle not in _LIFECYCLES:
            raise OutcomeEvaluationNotFoundError("invalid lifecycle")
        measured = lifecycle == "measured"
        required = (authoritative_evidence_reference, measurement_window_start, measurement_window_end, inputs, result, confidence, explanation)
        if measured and (not all(required) or confidence not in _CONFIDENCES or measurement_window_start > measurement_window_end):
            raise OutcomeEvaluationNotFoundError("invalid measurement")
        if not measured and any(value is not None for value in required):
            raise OutcomeEvaluationNotFoundError("non-measured evidence")
        safe_inputs = _safe_evidence_map(inputs)
        safe_result = _safe_evidence_map(result)
        key_hash = _idempotency_hash(raw_idempotency_key)
        goal = self._session.get(Goal, goal_id)
        decision = self._session.get(DecisionJournalEntry, decision_journal_entry_id)
        recommendation = self._session.get(Recommendation, recommendation_id)
        if (goal is None or goal.user_id != user_id or goal.is_archived or recommendation is None
                or recommendation.user_id != user_id or recommendation.goal_id != goal_id
                or decision is None or decision.user_id != user_id or decision.goal_id != goal_id
                or decision.recommendation_id != recommendation_id or decision.decision_action != "accept"):
            raise OutcomeEvaluationNotFoundError("not accessible")
        evaluation_id = outcome_evaluation_id_for(user_id=user_id, goal_id=goal_id, recommendation_id=recommendation_id, decision_journal_entry_id=decision_journal_entry_id, lifecycle=lifecycle, idempotency_key_hash=key_hash, schema_version=OUTCOME_EVALUATION_SCHEMA_VERSION)
        existing = self._session.get(OutcomeEvaluation, evaluation_id)
        if existing is not None:
            return OutcomeEvaluationWriteResult(existing, replayed=True)
        conflict = self._session.scalar(select(OutcomeEvaluation).where(OutcomeEvaluation.user_id == user_id, OutcomeEvaluation.idempotency_key_hash == key_hash))
        if conflict is not None:
            raise OutcomeEvaluationConflictError("idempotency conflict")
        evaluation = OutcomeEvaluation(id=evaluation_id, recommendation_id=recommendation_id, decision_journal_entry_id=decision_journal_entry_id, user_id=user_id, goal_id=goal_id, lifecycle=lifecycle, schema_version=OUTCOME_EVALUATION_SCHEMA_VERSION, idempotency_key_hash=key_hash, currency="USD", authoritative_evidence_reference=authoritative_evidence_reference, measurement_window_start=measurement_window_start, measurement_window_end=measurement_window_end, inputs_json=None if safe_inputs is None else json.dumps(dict(safe_inputs), sort_keys=True, separators=(",", ":")), result_json=None if safe_result is None else json.dumps(dict(safe_result), sort_keys=True, separators=(",", ":")), confidence=confidence, explanation=explanation, recorded_at=_now())
        self._session.add(evaluation)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            existing = self._session.get(OutcomeEvaluation, evaluation_id)
            if existing is None:
                raise OutcomeEvaluationConflictError("persistence conflict")
            return OutcomeEvaluationWriteResult(existing, replayed=True)
        return OutcomeEvaluationWriteResult(evaluation, replayed=False)
