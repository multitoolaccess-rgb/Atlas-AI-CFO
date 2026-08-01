"""Append-only decision-journal write service with idempotent-replay semantics.

Phase 2 Slice 1 commit-3 application-layer journal service.

Semantics enforced here:

* **Idempotent key is hashed before persistence.**  The raw
  ``Idempotency-Key`` header value NEVER appears in the database,
  never appears in logs, never appears in error responses.  Only the
  SHA-256 digest of the canonical ``atlas-idempotency-key/v1`` form
  reaches the journal row.

* **Ownership-before-existence.**  Goal ownership is verified
  BEFORE the recommendation row is loaded and BEFORE the journal
  write is attempted.  Cross-user access returns a sanitized
  :class:`GoalNotFoundError` /
  :class:`RecommendationNotFoundError` that a non-owner cannot use
  to distinguish ``missing`` from ``cross-user``.

* **Idempotent-replay + cross-row conflict detection.**  Same raw
  Idempotency-Key + same canonical request ⇒ same row
  (``replayed=True``).  Same key + DIFFERENT canonical request
  (action, recommendation, or note differs) ⇒
  :class:`DecisionConflictError` carrying only the stable
  ``current_etag`` of the existing row (no raw UUID, no raw key, no
  raw note).

* **Race handling.**  Two parallel writers with the same canonical
  request race on the UNAIQUE (user, goal, recommendation,
  idempotency_key_hash) constraint.  The service catches the
  integrity error, looks up the committed winner, and replays the
  loser's request as ``replayed=True``.  No row is created twice.
  No transaction is left half-open.

* **Immutable DB protections remain effective through service ops.**
  The service never issues UPDATE or DELETE against the journal.
  The Phase 1 SQL + Postgres triggers remain the final defence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.forecasts.recommendation_schemas import DECISION_JOURNAL_SCHEMA_VERSION
from app.models import DecisionJournalEntry, Goal, Recommendation
from app.models.decision_journal_identities import (
    canonical_idempotency_key_hash,
    decision_journal_id_for,
)


_ACTION_ALLOWED: Final[frozenset[str]] = frozenset({"accept", "reject", "defer"})
_DECISION_ETAG_VERSION: Final[str] = "1"
_NOW_FN = lambda: datetime.now(timezone.utc)  # noqa: E731


class JournalError(Exception):
    """Base class. The ``code`` attribute is the only safe contract surface."""

    code: str = "journal_invalid"


class GoalNotFoundError(JournalError):
    code: Final[str] = "goal_not_found"


class RecommendationNotFoundError(JournalError):
    code: Final[str] = "recommendation_not_found"


class DecisionConflictError(JournalError):
    """Same Idempotency-Key on a different canonical request.

    The error carries ONLY the stable ``current_etag`` of the
    existing row.  Raw key, raw action, raw payload are never
    included on the exception surface.
    """

    code: Final[str] = "decision_conflict"

    def __init__(self, current_etag: str) -> None:
        super().__init__("decision_conflict")
        self.current_etag = current_etag


class IdempotencyKeyRequiredError(JournalError):
    code: Final[str] = "idempotency_key_required"


class IdempotencyKeyInvalidError(JournalError):
    code: Final[str] = "idempotency_key_required"


@dataclass(frozen=True)
class JournalWriteResult:
    entry: DecisionJournalEntry
    replayed: bool
    conflict: bool
    current_etag: str


# ----------------------------------------------------------------------
# Helpers (public so tests can exercise them directly)
# ----------------------------------------------------------------------


def decision_etag_for(entry_id: str) -> str:
    """Stable decision ETag for a journal row (commit-1 envelope parity)."""
    return f"{entry_id}-d{_DECISION_ETAG_VERSION}"


def _now() -> datetime:
    return _NOW_FN()


# ----------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------


class DecisionJournalService:
    """Append-only journal write transaction. Owns commit / rollback."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Authorization (ownership-before-existence)
    # ------------------------------------------------------------------

    def _authorize_goal_ownership(self, *, user_id: int, goal_id: int) -> Goal:
        goal = self._session.get(Goal, goal_id)
        if goal is None or goal.user_id != user_id:
            raise GoalNotFoundError("goal not accessible")
        if goal.is_archived:
            raise GoalNotFoundError("goal not accessible")
        return goal

    def _authorize_recommendation_ownership(
        self, *, user_id: int, goal_id: int, recommendation_id: str,
    ) -> Recommendation:
        rec = self._session.get(Recommendation, recommendation_id)
        if rec is None or rec.user_id != user_id or rec.goal_id != goal_id:
            raise RecommendationNotFoundError("recommendation not accessible")
        return rec

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

    def _lookup_by_pk(self, journal_id: str) -> DecisionJournalEntry | None:
        return self._session.get(DecisionJournalEntry, journal_id)

    def _lookup_by_idempotency_key(
        self, *, user_id: int, idempotency_key_hash: str,
    ) -> DecisionJournalEntry | None:
        stmt = select(DecisionJournalEntry).where(
            DecisionJournalEntry.user_id == user_id,
            DecisionJournalEntry.idempotency_key_hash == idempotency_key_hash,
        )
        return self._session.scalar(stmt)

    @staticmethod
    def _canonical_fields_match(
        existing: DecisionJournalEntry,
        *,
        recommendation_id: str,
        decision_action: str,
        schema_version: str,
        note: str | None,
    ) -> bool:
        if existing.recommendation_id != recommendation_id:
            return False
        if existing.decision_action != decision_action:
            return False
        if existing.schema_version != schema_version:
            return False
        # ``note`` stored as ``str | None``; treat NULL as equal only to NULL.
        if (existing.note or None) != (note or None):
            return False
        return True

    # ------------------------------------------------------------------
    # Single-attempt insert
    # ------------------------------------------------------------------

    def _persist_once(
        self,
        *,
        user_id: int,
        goal_id: int,
        recommendation_id: str,
        decision_action: str,
        schema_version: str,
        idempotency_key_hash: str,
        note: str | None,
        metadata_json: Mapping[str, Any] | None,
        journal_id: str,
    ) -> DecisionJournalEntry:
        entry = DecisionJournalEntry(
            id=journal_id,
            recommendation_id=recommendation_id,
            user_id=user_id,
            goal_id=goal_id,
            decision_action=decision_action,
            schema_version=schema_version,
            idempotency_key_hash=idempotency_key_hash,
            currency="USD",
            note=note,
            metadata_json=None if metadata_json is None else _sanitize_metadata(metadata_json),
            decided_at=_now(),
        )
        self._session.add(entry)
        self._session.flush()
        return entry

    def _safe_metadata(self, value: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
        return None if value is None else _sanitize_metadata(value)

    # ------------------------------------------------------------------
    # Race recovery
    # ------------------------------------------------------------------

    def _recover_database_winner(
        self, *, journal_id: str,
    ) -> DecisionJournalEntry | None:
        return self._session.get(DecisionJournalEntry, journal_id)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        user_id: int,
        goal_id: int,
        recommendation_id: str,
        decision_action: str,
        raw_idempotency_key: str,
        note: str | None = None,
        metadata_json: Mapping[str, Any] | None = None,
        schema_version: str = DECISION_JOURNAL_SCHEMA_VERSION,
    ) -> JournalWriteResult:
        """Persist a decision journal row with idempotent-replay + conflict semantics.

        The ``raw_idempotency_key`` argument holds the client-supplied
        Idempotency-Key header value verbatim; the service hashes it
        BEFORE persistence and never stores the raw form.
        """
        # 1. Bounded action token.
        if decision_action not in _ACTION_ALLOWED:
            raise RecommendationNotFoundError("decision_action is not in the bounded set")
        # 2. Idempotency key is required.
        idempotency_key_hash = self._hash_idempotency_key(raw_idempotency_key)
        # 3. Deterministic PK (must come from hashed key + canonical inputs).
        journal_id = decision_journal_id_for(
            user_id=user_id,
            goal_id=goal_id,
            recommendation_id=recommendation_id,
            decision_action=decision_action,
            idempotency_key_hash=idempotency_key_hash,
            schema_version=schema_version,
        )
        # 4. Authorization BEFORE any persistence decision.
        self._authorize_goal_ownership(user_id=user_id, goal_id=goal_id)
        self._authorize_recommendation_ownership(
            user_id=user_id, goal_id=goal_id, recommendation_id=recommendation_id,
        )

        sanitized_metadata = self._safe_metadata(metadata_json)

        # 5. PRIMARY lookup: same canonical request ⇒ same row ⇒ replay.
        existing_by_pk = self._lookup_by_pk(journal_id=journal_id)
        if existing_by_pk is not None:
            if not self._canonical_fields_match(
                existing_by_pk,
                recommendation_id=recommendation_id,
                decision_action=decision_action,
                schema_version=schema_version,
                note=note,
            ):
                # Same deterministic PK but a different canonical payload
                # is a stable cross-row conflict — the request cannot
                # silently overwrite the past journal entry, and we do
                # not pretend it is an idempotent replay.
                raise DecisionConflictError(
                    current_etag=decision_etag_for(existing_by_pk.id),
                )
            return JournalWriteResult(
                entry=existing_by_pk,
                replayed=True,
                conflict=False,
                current_etag=decision_etag_for(existing_by_pk.id),
            )

        # 6. Cross-row CONFLICT lookup: same idempotency key hash, different request.
        existing_by_key = self._lookup_by_idempotency_key(
            user_id=user_id, idempotency_key_hash=idempotency_key_hash,
        )
        if existing_by_key is not None and not self._canonical_fields_match(
            existing_by_key,
            recommendation_id=recommendation_id,
            decision_action=decision_action,
            schema_version=schema_version,
            note=note,
        ):
            raise DecisionConflictError(
                current_etag=decision_etag_for(existing_by_key.id),
            )

        # 7. Insert; on race, retry the PK lookup to surface the commit winner.
        try:
            entry = self._persist_once(
                user_id=user_id,
                goal_id=goal_id,
                recommendation_id=recommendation_id,
                decision_action=decision_action,
                schema_version=schema_version,
                idempotency_key_hash=idempotency_key_hash,
                note=note,
                metadata_json=sanitized_metadata,
                journal_id=journal_id,
            )
            self._session.commit()
            return JournalWriteResult(
                entry=entry, replayed=False, conflict=False,
                current_etag=decision_etag_for(entry.id),
            )
        except (
            GoalNotFoundError,
            RecommendationNotFoundError,
            IdempotencyKeyRequiredError,
            IdempotencyKeyInvalidError,
        ):
            self._session.rollback()
            raise
        except (IntegrityError, OperationalError):
            self._session.rollback()
            recovered = self._recover_database_winner(journal_id=journal_id)
            if recovered is None:
                # Either the integrity failure was non-uniqueness, or the
                # rollback is unrecoverable.  Surface as a sanitized error.
                raise RecommendationNotFoundError("journal persistence conflict")
            # Apply the same canonical-fields check on the recovered
            # winner so a same-key-but-different-``note`` race cannot be
            # silently replayed as the loser's payload.
            if not self._canonical_fields_match(
                recovered,
                recommendation_id=recommendation_id,
                decision_action=decision_action,
                schema_version=schema_version,
                note=note,
            ):
                raise DecisionConflictError(
                    current_etag=decision_etag_for(recovered.id),
                )
            self._session.commit()
            return JournalWriteResult(
                entry=recovered, replayed=True, conflict=False,
                current_etag=decision_etag_for(recovered.id),
            )


def _sanitize_metadata(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Strip keys or values that could leak financial source state."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        if any(sensitive in key.lower() for sensitive in (
            "balance", "amount", "contribution", "snapshot", "raw", "token",
            "secret", "password", "api_key", "apikey",
        )):
            continue
        if not isinstance(value, (str, int, bool, type(None))):
            continue
        out[key] = value
    return out


__all__ = [
    "JournalError",
    "GoalNotFoundError",
    "RecommendationNotFoundError",
    "DecisionConflictError",
    "IdempotencyKeyRequiredError",
    "IdempotencyKeyInvalidError",
    "JournalWriteResult",
    "DecisionJournalService",
    "decision_etag_for",
]
