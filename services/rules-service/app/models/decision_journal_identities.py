"""Deterministic canonical UUID + SHA-256 helpers for the decision-journal substrate.

Phase 2 Slice 1 — both ``Recommendation.id`` and ``DecisionJournalEntry.id``
are deterministic primary keys derived from ``SHA-256[:16]`` formatted
via ``uuid.UUID(bytes=...)`` over canonical-JSON encoded inputs.

Stable-replay semantics:

* Same canonical input tuple ⇒ same PK.
* Idempotent retries collapse onto a single row because the
  ``UNIQUE (user_id, goal_id, recommendation_id, idempotency_key_hash)``
  constraint on ``decision_journal_entries`` rejects duplicate writes.

Per the Phase 1 ledger contract, all canonical hashes are produced as
**16 bytes** of a 32-byte SHA-256 digest and formatted as RFC 4122 §4.1
``uuid.UUID(bytes=first_16_bytes)`` strings (canonical lowercase 8-4-4-4-12
hex grouping). The full 64-character lowercase hex SHA-256 digest is
also exposed for evidence-bound hashing.

Three deterministic identities — kept distinct on purpose:

* ``recommendation_id`` = PK on ``Recommendation`` -- the deterministic
  identity of a recommendation derivation itself.
* ``decision_slot_id``  = a derived identity advertised in the
  recommendation envelope (not stored) -- the "decision slot" the
  recommendation opens. Stable per recommendation.
* ``decision_id``       = PK on ``DecisionJournalEntry`` -- the
  deterministic identity of a specific user decision event on a
  recommendation. Includes action + idempotency_key_hash, so a replay of
  the same client request resolves to the same row.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, Final


# Public re-export so test modules can pin the algorithm choice.
DERIVATION_HASH_ALGORITHM: Final[str] = "sha256"

# Each derivation owns its byte namespace; mixing them across tables would
# produce the same SHA for inputs that should be treated as distinct.
_RECOMMENDATION_NAMESPACE: Final[bytes] = b"atlas-recommendation/v1:"
_DECISION_SLOT_NAMESPACE: Final[bytes] = b"atlas-decision-slot/v1:"
_DECISION_JOURNAL_NAMESPACE: Final[bytes] = b"atlas-decision-journal/v1:"
_OUTCOME_EVALUATION_NAMESPACE: Final[bytes] = b"atlas-outcome-evaluation/v1:"
_DECISION_HISTORY_NAMESPACE: Final[bytes] = b"atlas-decision-history/v1:"
_DECISION_AUDIT_NAMESPACE: Final[bytes] = b"atlas-decision-audit/v1:"
_GENERIC_IDEMPOTENCY_NAMESPACE: Final[bytes] = b"atlas-idempotency-key/v1:"

_CANONICAL_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_LOWERCASE_SHA256_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_encode(inputs: dict[str, Any]) -> bytes:
    """Deterministic UTF-8 JSON encoding: sort_keys, no whitespace, ASCII only.

    ``ensure_ascii=True`` keeps the byte-level digest reproducible across
    platforms (``utf-8`` vs ``utf-16`` quirks) and matches the Phase 1
    canonical-state contract.
    """
    return json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_digest(inputs: dict[str, Any], namespace: bytes) -> bytes:
    """Return the raw 32-byte SHA-256 digest for ``inputs`` under ``namespace``."""
    return hashlib.new(DERIVATION_HASH_ALGORITHM, namespace + canonical_json_encode(inputs)).digest()


def canonical_uuid_from_digest(digest: bytes) -> str:
    """Format the first 16 bytes of ``digest`` as a canonical lowercase UUID string.

    We slice the SHA-256 digest to its leading 16 bytes and feed it to
    RFC 4122 ``uuid.UUID(bytes=...)``. The resulting UUID is bit-pattern
    stable across replays; we do NOT modify or claim a specific UUID
    version or variant bit, since the IDs are internal canonical
    reconciliation identities, not externally-generated UUID5 / UUID1
    values.
    """
    if len(digest) < 16:
        raise ValueError("digest must expose at least 16 bytes to format an RFC 4122 UUID")
    return str(uuid.UUID(bytes=digest[:16]))


def derivation_sha256_hex(inputs: dict[str, Any], namespace: bytes) -> str:
    """Return the full 64-character lowercase hex SHA-256 digest for ``inputs``."""
    return canonical_digest(inputs, namespace).hex()


def recommendation_id_for(
    *,
    user_id: int,
    goal_id: int,
    forecast_version_id: str,
    recommendation_kind: str,
    rule_version: str,
    derivation_schema_version: str,
) -> str:
    """Deterministic PK for ``Recommendation``. Stable across replays."""
    inputs = {
        "user_id": user_id,
        "goal_id": goal_id,
        "forecast_version_id": forecast_version_id,
        "recommendation_kind": recommendation_kind,
        "rule_version": rule_version,
        "derivation_schema_version": derivation_schema_version,
    }
    return canonical_uuid_from_digest(canonical_digest(inputs, _RECOMMENDATION_NAMESPACE))


def decision_slot_id_for(recommendation_id: str) -> str:
    """Deterministic slot identity. Stable per recommendation.

    Not stored as a column on ``Recommendation``: the envelope synthesises
    this identity at response time. Used by the recommendation envelope's
    ``decision_id`` field to advertise the open decision slot without
    requiring a journal entry to exist yet.
    """
    return canonical_uuid_from_digest(canonical_digest({"recommendation_id": recommendation_id}, _DECISION_SLOT_NAMESPACE))


def decision_journal_id_for(
    *,
    user_id: int,
    goal_id: int,
    recommendation_id: str,
    decision_action: str,
    idempotency_key_hash: str,
    schema_version: str,
) -> str:
    """Deterministic PK (``decision_id``) for ``DecisionJournalEntry``.

    A client retry with the same idempotency_key_hash on the same
    recommendation + action produces the same PK, which collides on the
    UNIQUE constraint and lets the orchestrator API layer return the
    prior row instead of inserting a duplicate journal entry.
    """
    inputs = {
        "user_id": user_id,
        "goal_id": goal_id,
        "recommendation_id": recommendation_id,
        "decision_action": decision_action,
        "idempotency_key_hash": idempotency_key_hash,
        "schema_version": schema_version,
    }
    return canonical_uuid_from_digest(canonical_digest(inputs, _DECISION_JOURNAL_NAMESPACE))


def canonical_idempotency_key_hash(raw_key: str) -> str:
    """Hash a raw client-supplied idempotency key as 64-char lowercase SHA-256 hex.

    The raw client key is NEVER persisted; only the hashed form is
    recorded in ``decision_journal_entries.idempotency_key_hash`` so
    PHI / per-user identifiers never reach the database in plaintext.
    """
    if not isinstance(raw_key, str):
        raise TypeError("raw_idempotency_key must be a string")
    return hashlib.new(DERIVATION_HASH_ALGORITHM, _GENERIC_IDEMPOTENCY_NAMESPACE + raw_key.encode("utf-8")).hexdigest()


def is_canonical_uuid(value: str) -> bool:
    """True iff ``value`` matches the canonical lowercase 8-4-4-4-12 hex grouping."""
    return isinstance(value, str) and bool(_CANONICAL_UUID_REGEX.match(value))


def is_lowercase_hex_sha256(value: str) -> bool:
    """True iff ``value`` is a 64-character lowercase hex SHA-256 digest."""
    return isinstance(value, str) and bool(_LOWERCASE_SHA256_REGEX.match(value))


def outcome_evaluation_id_for(
    *,
    user_id: int,
    goal_id: int,
    recommendation_id: str,
    decision_journal_entry_id: str,
    lifecycle: str,
    idempotency_key_hash: str,
    schema_version: str,
) -> str:
    """Deterministic PK for ``OutcomeEvaluation``.

    A client retry with the same idempotency_key_hash on the same
    recommendation + decision + lifecycle produces the same PK, which
    collides on the UNIQUE constraint and lets the orchestrator API layer
    return the prior row instead of inserting a duplicate evaluation.
    """
    inputs = {
        "user_id": user_id,
        "goal_id": goal_id,
        "recommendation_id": recommendation_id,
        "decision_journal_entry_id": decision_journal_entry_id,
        "lifecycle": lifecycle,
        "idempotency_key_hash": idempotency_key_hash,
        "schema_version": schema_version,
    }
    return canonical_uuid_from_digest(canonical_digest(inputs, _OUTCOME_EVALUATION_NAMESPACE))


def decision_history_id_for(*, user_id: int, goal_id: int, recommendation_id: str,
                            decision_journal_entry_id: str, idempotency_key_hash: str,
                            schema_version: str) -> str:
    return canonical_uuid_from_digest(canonical_digest({
        "user_id": user_id, "goal_id": goal_id, "recommendation_id": recommendation_id,
        "decision_journal_entry_id": decision_journal_entry_id,
        "idempotency_key_hash": idempotency_key_hash, "schema_version": schema_version,
    }, _DECISION_HISTORY_NAMESPACE))


def decision_audit_id_for(*, history_entry_id: str, event_action: str) -> str:
    return canonical_uuid_from_digest(canonical_digest(
        {"history_entry_id": history_entry_id, "event_action": event_action}, _DECISION_AUDIT_NAMESPACE
    ))
