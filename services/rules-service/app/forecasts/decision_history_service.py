"""Append-only Phase 4 decision-history writer.

The service deliberately creates a new record for correction.  It has no
update/delete operation and never accepts evidence references or outcome data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import DecisionAuditEvent, DecisionHistoryEntry, DecisionJournalEntry, Goal, OutcomeEvaluation, Recommendation
from app.models.decision_journal_identities import canonical_idempotency_key_hash, decision_audit_id_for, decision_history_id_for

DECISION_HISTORY_SCHEMA_VERSION: Final[str] = "atlas-decision-history/v1"
_ACTIONS: Final[frozenset[str]] = frozenset({"accept", "reject", "defer"})
_ALTERNATIVES: Final[frozenset[str]] = frozenset({"do_nothing", "accept", "reject", "defer"})


class DecisionHistoryError(Exception):
    code = "decision_history_invalid"


class DecisionHistoryNotFoundError(DecisionHistoryError):
    code = "decision_history_not_found"


class DecisionHistoryConflictError(DecisionHistoryError):
    code = "decision_history_conflict"


class DecisionHistoryValidationError(DecisionHistoryError):
    code = "decision_history_validation"


@dataclass(frozen=True)
class DecisionHistoryWriteResult:
    entry: DecisionHistoryEntry
    replayed: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionHistoryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _key_hash(raw_key: str) -> str:
        if not isinstance(raw_key, str) or not raw_key or len(raw_key) > 255 or any(ord(c) < 0x21 or ord(c) > 0x7e for c in raw_key):
            raise DecisionHistoryValidationError("idempotency key invalid")
        return canonical_idempotency_key_hash(raw_key)

    def _parents(self, *, user_id: int, goal_id: int, recommendation_id: str, decision_id: str) -> DecisionJournalEntry:
        # All parents are checked before any history lookup or write.  One
        # sanitized exception prevents an owner probe from disclosing which
        # linked object exists.
        goal = self._session.get(Goal, goal_id)
        rec = self._session.get(Recommendation, recommendation_id)
        decision = self._session.get(DecisionJournalEntry, decision_id)
        if (goal is None or rec is None or decision is None or goal.user_id != user_id
                or rec.user_id != user_id or rec.goal_id != goal_id
                or decision.user_id != user_id or decision.goal_id != goal_id
                or decision.recommendation_id != recommendation_id):
            raise DecisionHistoryNotFoundError("not accessible")
        return decision

    @staticmethod
    def _alternatives(value: Sequence[str]) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not (1 <= len(value) <= 8):
            raise DecisionHistoryValidationError("alternatives invalid")
        if any(not isinstance(item, str) or item not in _ALTERNATIVES for item in value):
            raise DecisionHistoryValidationError("alternatives invalid")
        if "do_nothing" not in value or len(set(value)) != len(value):
            raise DecisionHistoryValidationError("alternatives invalid")
        return tuple(value)

    def record(self, *, user_id: int, goal_id: int, recommendation_id: str,
               decision_journal_entry_id: str, alternatives: Sequence[str], rationale: str,
               raw_idempotency_key: str, supersedes_history_entry_id: str | None = None,
               outcome_evaluation_id: str | None = None) -> DecisionHistoryWriteResult:
        key_hash = self._key_hash(raw_idempotency_key)
        decision = self._parents(user_id=user_id, goal_id=goal_id, recommendation_id=recommendation_id, decision_id=decision_journal_entry_id)
        alternatives_value = self._alternatives(alternatives)
        if not isinstance(rationale, str) or not (1 <= len(rationale) <= 2048):
            raise DecisionHistoryValidationError("rationale invalid")
        if supersedes_history_entry_id is not None:
            prior = self._session.get(DecisionHistoryEntry, supersedes_history_entry_id)
            if (prior is None or prior.user_id != user_id or prior.goal_id != goal_id
                    or prior.recommendation_id != recommendation_id):
                raise DecisionHistoryNotFoundError("not accessible")
        if outcome_evaluation_id is not None:
            outcome = self._session.get(OutcomeEvaluation, outcome_evaluation_id)
            if (outcome is None or outcome.user_id != user_id or outcome.goal_id != goal_id
                    or outcome.recommendation_id != recommendation_id
                    or outcome.decision_journal_entry_id != decision_journal_entry_id):
                raise DecisionHistoryNotFoundError("not accessible")
        history_id = decision_history_id_for(user_id=user_id, goal_id=goal_id, recommendation_id=recommendation_id,
                                              decision_journal_entry_id=decision_journal_entry_id,
                                              idempotency_key_hash=key_hash, schema_version=DECISION_HISTORY_SCHEMA_VERSION)
        existing = self._session.get(DecisionHistoryEntry, history_id)
        encoded = json.dumps(list(alternatives_value), separators=(",", ":"), ensure_ascii=True)
        # A key is a user-scoped replay token, not a per-recommendation token.
        # Looking it up before the table's narrower unique constraint prevents a
        # caller from reusing one key to create a distinct history record.
        existing_by_key = self._session.scalar(select(DecisionHistoryEntry).where(
            DecisionHistoryEntry.user_id == user_id,
            DecisionHistoryEntry.idempotency_key_hash == key_hash,
        ))
        if existing_by_key is not None and existing_by_key.id != history_id:
            raise DecisionHistoryConflictError("idempotency conflict")
        if existing is not None:
            if (existing.alternatives_json == encoded and existing.rationale == rationale
                    and existing.supersedes_history_entry_id == supersedes_history_entry_id):
                return DecisionHistoryWriteResult(existing, True)
            raise DecisionHistoryConflictError("idempotency conflict")
        entry = DecisionHistoryEntry(id=history_id, user_id=user_id, goal_id=goal_id,
            recommendation_id=recommendation_id, decision_journal_entry_id=decision_journal_entry_id,
            supersedes_history_entry_id=supersedes_history_entry_id, decision_action=decision.decision_action,
            alternatives_json=encoded, rationale=rationale, schema_version=DECISION_HISTORY_SCHEMA_VERSION,
            idempotency_key_hash=key_hash, currency="USD", recorded_at=_now())
        event_action = "evaluated" if outcome_evaluation_id else ("corrected" if supersedes_history_entry_id else "recorded")
        audit = DecisionAuditEvent(id=decision_audit_id_for(history_entry_id=history_id, event_action=event_action),
            history_entry_id=history_id, user_id=user_id, goal_id=goal_id, recommendation_id=recommendation_id,
            decision_journal_entry_id=decision_journal_entry_id, outcome_evaluation_id=outcome_evaluation_id, event_action=event_action, actor_scope="owner",
            correlation_hash=key_hash, policy_result="recorded", occurred_at=_now())
        try:
            self._session.add_all((entry, audit))
            self._session.commit()
        except (IntegrityError, OperationalError):
            self._session.rollback()
            winner = self._session.get(DecisionHistoryEntry, history_id)
            if winner is not None and winner.alternatives_json == encoded and winner.rationale == rationale and winner.supersedes_history_entry_id == supersedes_history_entry_id:
                return DecisionHistoryWriteResult(winner, True)
            raise DecisionHistoryConflictError("idempotency conflict")
        return DecisionHistoryWriteResult(entry, False)

    def list_for_goal(self, *, user_id: int, goal_id: int) -> tuple[DecisionHistoryEntry, ...]:
        goal = self._session.get(Goal, goal_id)
        if goal is None or goal.user_id != user_id:
            raise DecisionHistoryNotFoundError("not accessible")
        return tuple(self._session.scalars(select(DecisionHistoryEntry).where(
            DecisionHistoryEntry.user_id == user_id, DecisionHistoryEntry.goal_id == goal_id
        ).order_by(DecisionHistoryEntry.recorded_at.asc(), DecisionHistoryEntry.id.asc())))
