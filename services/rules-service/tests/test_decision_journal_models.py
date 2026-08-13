"""In-memory ORM invariants for Phase 2 decision-journal substrate.

Locks:

1. Canonical UUID + lowercase SHA-256 hex format constraints on both tables.
2. ``UNIQUE (user_id, goal_id, recommendation_id, idempotency_key_hash)`` makes
   ``DecisionJournalEntry`` writes deterministically idempotent.
3. ``decision_action IN ('accept', 'reject', 'defer')`` is the only valid set.
4. Deterministic-UUID helper module derived from canonical JSON + SHA-256 + first
   16 bytes (RFC 4122 §4.1 ``uuid.UUID(bytes=...)``) is stable across replays
   and unique across input tuples.
5. UUID-byte truncation produces a different identity for every change in
   canonical inputs (no spurious collisions).
6. Confidence-score range is fail-closed 0..1 at the DB layer.
7. ``expected_impact_min <= expected_impact_max`` ordering holds at the DB
   layer.
8. ``decision_journal_entries.note`` is bounded-length and may be NULL.
9. Cross-currency writes (``USD`` is the only acceptable value) fail closed.

Mirrors :mod:`tests.test_forecast_models` so the rules-service test suite can
share the hermetic SQLite bootstrap through a ``StaticPool`` engine.
"""
from __future__ import annotations

import re
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    DecisionJournalEntry,
    Goal,
    Recommendation,
    User,
)
from app.models.decision_journal_identities import (
    DERIVATION_HASH_ALGORITHM,
    canonical_digest,
    canonical_idempotency_key_hash,
    canonical_uuid_from_digest,
    decision_journal_id_for,
    decision_slot_id_for,
    derivation_sha256_hex,
    is_canonical_uuid,
    is_lowercase_hex_sha256,
    recommendation_id_for,
)


# ---------------------------------------------------------------------------
# World fixture helpers (StaticPool keeps the boot DB shared across sessions)
# ---------------------------------------------------------------------------


_FORECAST_VERSION_ID = "00000000-0000-4000-8000-000000000002"
_FORECAST_IDENTITY = "00000000-0000-4000-8000-000000000001"


def _new_engine_with_world() -> object:
    """Return a hermetic SQLite engine with one user + goal + forecast + version row.

    ``StaticPool`` keeps a single shared connection so data planted in one
    session is visible to every other session bound to the same engine.
    The ``forecasts`` + ``forecast_versions`` rows are required because
    :class:`app.models.Recommendation` declares an FK to ``forecast_versions.id``.
    """
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(
            User(id=1, local_user_sub="synth", email="synth@example.com", hashed_password="x")
        )
        session.add(
            Goal(id=1, user_id=1, name="Decision Goal", target_amount=1.0, priority=0, is_archived=False)
        )
        # Plant a minimal ``forecasts`` + ``forecast_versions`` row so the
        # ``recommendations.forecast_version_id`` FK is satisfied.
        from sqlalchemy import text

        session.execute(
            text(
                "INSERT INTO forecasts (id, user_id, goal_id) VALUES "
                "(:id, 1, 1)"
            ),
            {"id": _FORECAST_IDENTITY},
        )
        session.execute(
            text(
                "INSERT INTO forecast_versions (id, forecast_id, version_number, "
                "input_state_hash, idempotency_key_hash, snapshot_schema_version, "
                "hash_schema_version, model_version, calculation_version, "
                "calculated_at, data_as_of, max_data_age_days, data_age_days, "
                "input_snapshot_json, assumption_snapshot_json, output_snapshot_json, "
                "provenance_snapshot_json, ending_balance, target_gap) VALUES "
                "(:id, :forecast_id, 1, :h, :k, 'v1', 'v1', 'model-v1', 'calc-v1', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 0, '{}', '{}', '{}', '{}', "
                "1.23, 0.00)"
            ),
            {
                "id": _FORECAST_VERSION_ID,
                "forecast_id": _FORECAST_IDENTITY,
                "h": "a" * 64,
                "k": "b" * 64,
            },
        )
    return engine


@pytest.fixture
def engine():
    return _new_engine_with_world()


# ---------------------------------------------------------------------------
# Deterministic-UUID helper unit tests (no DB needed)
# ---------------------------------------------------------------------------


def test_canonical_uuid_from_digest_produces_lowercase_uuid_format():
    digest = canonical_digest({"a": 1, "b": "two"}, b"unit-test:")
    uuid_text = canonical_uuid_from_digest(digest)
    parsed = _uuid.UUID(uuid_text)
    assert str(parsed) == uuid_text
    raw = parsed.bytes
    assert raw == digest[:16]


def test_decision_identity_helpers_are_stable_across_replays():
    inputs = {
        "user_id": 7,
        "goal_id": 11,
        "forecast_version_id": "00000000-0000-4000-8000-000000000123",
        "recommendation_kind": "extend_horizon",
        "rule_version": "v2.1",
        "derivation_schema_version": "atlas-recommendation/v1",
    }
    first = recommendation_id_for(**inputs)
    second = recommendation_id_for(**inputs)
    assert first == second
    assert is_canonical_uuid(first)
    flipped = dict(inputs, rule_version="v2.2")
    assert recommendation_id_for(**flipped) != first


def test_decision_slot_identity_is_stable_per_recommendation():
    rec_id = "00000000-0000-4000-8000-000000000999"
    slot1 = decision_slot_id_for(rec_id)
    slot2 = decision_slot_id_for(rec_id)
    assert slot1 == slot2
    assert is_canonical_uuid(slot1)
    assert slot1 != decision_slot_id_for("00000000-0000-4000-8000-000000000998")


def test_decision_journal_id_distinguishes_action_and_idempotency_key():
    base = {
        "user_id": 1,
        "goal_id": 1,
        "recommendation_id": "00000000-0000-4000-8000-000000000001",
        "schema_version": "atlas-decision-journal/v1",
        "idempotency_key_hash": "c" * 64,
    }
    accept = decision_journal_id_for(decision_action="accept", **base)
    reject = decision_journal_id_for(decision_action="reject", **base)
    defer = decision_journal_id_for(decision_action="defer", **base)
    assert accept != reject != defer != accept
    different_key = decision_journal_id_for(
        decision_action="accept", **{**base, "idempotency_key_hash": "d" * 64}
    )
    assert different_key != accept


def test_derivation_sha256_hex_is_64_char_lowercase_hex():
    digest_hex = derivation_sha256_hex({"k": "v"}, b"hex-unit-test:")
    assert is_lowercase_hex_sha256(digest_hex)
    assert len(digest_hex) == 64
    assert digest_hex == digest_hex.lower()


def test_derivation_hash_algorithm_constant_is_sha256():
    assert DERIVATION_HASH_ALGORITHM == "sha256"


def test_canonical_idempotency_key_hash_is_stable_and_lowercase_hex():
    digest_a = canonical_idempotency_key_hash("retry-key-2026-08-01")
    digest_b = canonical_idempotency_key_hash("retry-key-2026-08-01")
    assert digest_a == digest_b == digest_a.lower()
    assert is_lowercase_hex_sha256(digest_a)
    digest_other = canonical_idempotency_key_hash("retry-key-2026-08-02")
    assert digest_other != digest_a


# ---------------------------------------------------------------------------
# In-memory ORM invariants (engine stays alive across sub-tests via StaticPool)
# ---------------------------------------------------------------------------


def _add_recommendation(
    session: Session,
    *,
    recommendation_kind: str = "increase_contribution",
    rule_version: str = "v1.0",
    schema_version: str = "atlas-recommendation/v1",
    min_delta: Decimal = Decimal("0"),
    max_delta: Decimal = Decimal("100"),
    confidence: Decimal = Decimal("0.50"),
    forecast_input_state_hash: str = "a" * 64,
    forecast_version_id: str = _FORECAST_VERSION_ID,
    reason: str = "increase monthly investable cash flow until projected outcomes reach target band",
    currency: str = "USD",
    expires_at=None,
    flush: bool = True,
) -> Recommendation:
    rec_id = recommendation_id_for(
        user_id=1,
        goal_id=1,
        forecast_version_id=forecast_version_id,
        recommendation_kind=recommendation_kind,
        rule_version=rule_version,
        derivation_schema_version=schema_version,
    )
    rec = Recommendation(
        id=rec_id,
        user_id=1,
        goal_id=1,
        forecast_version_id=forecast_version_id,
        forecast_input_state_hash=forecast_input_state_hash,
        recommendation_kind=recommendation_kind,
        rule_version=rule_version,
        derivation_schema_version=schema_version,
        currency=currency,
        reason=reason,
        expected_impact_min_decimal=min_delta,
        expected_impact_max_decimal=max_delta,
        confidence_score=confidence,
        assumptions_json='{"monthly_contribution_band":"0-100"}',
        risks_json='{"bandwidth":"capped_at_100"}',
        freshness_json='{"observed_at":"2026-07-01T12:00:00Z"}',
        provenance_json=f'{{"forecast_version_id":"{forecast_version_id}","rule":"{rule_version}"}}',
        metadata_json=None,
        derived_at=datetime.now(timezone.utc),
        data_as_of=datetime.now(timezone.utc) - timedelta(days=1),
        expires_at=expires_at,
    )
    session.add(rec)
    if flush:
        session.flush()
    return rec


def _add_journal_entry(
    session: Session,
    *,
    recommendation_id: str,
    decision_action: str = "accept",
    idempotency_key_hash: str = "b" * 64,
    schema_version: str = "atlas-decision-journal/v1",
    currency: str = "USD",
    note: str | None = "looking good",
    flush: bool = True,
) -> DecisionJournalEntry:
    journal_id = decision_journal_id_for(
        user_id=1,
        goal_id=1,
        recommendation_id=recommendation_id,
        decision_action=decision_action,
        idempotency_key_hash=idempotency_key_hash,
        schema_version=schema_version,
    )
    entry = DecisionJournalEntry(
        id=journal_id,
        recommendation_id=recommendation_id,
        user_id=1,
        goal_id=1,
        decision_action=decision_action,
        schema_version=schema_version,
        idempotency_key_hash=idempotency_key_hash,
        currency=currency,
        note=note,
        metadata_json=None,
        decided_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    if flush:
        session.flush()
    return entry


def test_recommendation_unique_constraint_catches_duplicate_deterministic_uuid(engine):
    with Session(engine) as session, session.begin():
        _add_recommendation(session)
        with pytest.raises(IntegrityError):
            _add_recommendation(session)
            session.flush()


def test_recommendation_decimal_range_and_confidence_bounds_fail_closed(engine):
    # attempt 1: out-of-order min/max
    with Session(engine) as session, session.begin():
        _add_recommendation(
            session,
            min_delta=Decimal("200"),
            max_delta=Decimal("100"),
            flush=False,
        )
        with pytest.raises(IntegrityError):
            session.flush()

    # attempt 2: confidence above 1
    with Session(engine) as session, session.begin():
        _add_recommendation(
            session,
            confidence=Decimal("1.10"),
            flush=False,
        )
        with pytest.raises(IntegrityError):
            session.flush()

    # attempt 3: confidence negative
    with Session(engine) as session, session.begin():
        _add_recommendation(
            session,
            confidence=Decimal("-0.01"),
            flush=False,
        )
        with pytest.raises(IntegrityError):
            session.flush()

    # attempt 4: reason too long
    with Session(engine) as session, session.begin():
        _add_recommendation(session, reason="." * 1025, flush=False)
        with pytest.raises(IntegrityError):
            session.flush()

    # attempt 5: recommendation_kind too short (length 1, must be >= 2)
    with Session(engine) as session, session.begin():
        _add_recommendation(session, recommendation_kind="a", flush=False)
        with pytest.raises(IntegrityError):
            session.flush()


def test_decision_journal_entry_idempotency_replay_rejected_by_unique(engine):
    with Session(engine) as session, session.begin():
        rec = _add_recommendation(session)
        _add_journal_entry(
            session,
            recommendation_id=rec.id,
            decision_action="accept",
            idempotency_key_hash="e" * 64,
        )
        # second INSERT with same idempotency_key_hash fails
        with pytest.raises(IntegrityError):
            _add_journal_entry(
                session,
                recommendation_id=rec.id,
                decision_action="accept",
                idempotency_key_hash="e" * 64,
            )
            session.commit()
        session.rollback()

    # a different idempotency_key_hash on the same action registers as a new entry
    with Session(engine) as session, session.begin():
        rec = _add_recommendation(session)
        _add_journal_entry(
            session,
            recommendation_id=rec.id,
            decision_action="accept",
            idempotency_key_hash="f" * 64,
        )
        _add_journal_entry(
            session,
            recommendation_id=rec.id,
            decision_action="accept",
            idempotency_key_hash="g" * 64,
        )
        assert session.query(DecisionJournalEntry).count() == 2


def test_decision_journal_entry_rejects_unknown_action(engine):
    with Session(engine) as session, session.begin():
        rec = _add_recommendation(session)
        _add_journal_entry(
            session,
            recommendation_id=rec.id,
            decision_action="drop",
            flush=False,
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_recommendation_currency_fail_closed_to_usd(engine):
    with Session(engine) as session, session.begin():
        rec = _add_recommendation(session, flush=False)
        rec.currency = "EUR"
        with pytest.raises(IntegrityError):
            session.flush()


def test_recommendation_rejects_malformed_canonical_uuid_on_id(engine):
    with Session(engine) as session, session.begin():
        bad = Recommendation(
            id="not-a-canonical-uuid",
            user_id=1,
            goal_id=1,
            forecast_version_id=_FORECAST_VERSION_ID,
            forecast_input_state_hash="a" * 64,
            recommendation_kind="increase_contribution",
            rule_version="v1.0",
            derivation_schema_version="atlas-recommendation/v1",
            currency="USD",
            reason="tamper attempt",
            expected_impact_min_decimal=Decimal("0"),
            expected_impact_max_decimal=Decimal("1"),
            confidence_score=Decimal("0.5"),
            assumptions_json="{}",
            risks_json="{}",
            freshness_json="{}",
            provenance_json="{}",
            derived_at=datetime.now(timezone.utc),
            data_as_of=datetime.now(timezone.utc),
        )
        session.add(bad)
        with pytest.raises(IntegrityError):
            session.flush()


def test_recommendation_rejects_non_lowercase_input_state_hash(engine):
    with Session(engine) as session, session.begin():
        rec = _add_recommendation(session, flush=False)
        rec.forecast_input_state_hash = "A" * 64  # uppercase
        with pytest.raises(IntegrityError):
            session.flush()


def test_decision_journal_entry_currency_fail_closed_to_usd(engine):
    with Session(engine) as session, session.begin():
        rec = _add_recommendation(session)
        entry = _add_journal_entry(session, recommendation_id=rec.id, flush=False)
        entry.currency = "eur"
        with pytest.raises(IntegrityError):
            session.flush()


def test_decision_journal_entry_note_bounded_to_2048(engine):
    """``note`` may be NULL or bounded; an overlong note is rejected."""
    with Session(engine) as session, session.begin():
        rec = _add_recommendation(session)
        # a 2049-char note is rejected
        _add_journal_entry(
            session,
            recommendation_id=rec.id,
            idempotency_key_hash="h" * 64,
            note="." * 2049,
            flush=False,
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_recommendation_idempotent_replay_collapses_onto_same_row(engine):
    """Same canonical inputs ⇒ Same PK ⇒ UNIQUE rejects second INSERT.

    This mirrors the application's idempotent retry semantics for
    re-runs of the deterministic recommendation derivation.
    """
    with Session(engine) as session, session.begin():
        _add_recommendation(
            session,
            rule_version="v3.2",
            recommendation_kind="extend_horizon",
        )
        with pytest.raises(IntegrityError):
            _add_recommendation(
                session,
                rule_version="v3.2",
                recommendation_kind="extend_horizon",
            )
            session.flush()


def test_recommendation_raises_at_for_same_kind_different_rule_version(engine):
    """Different ``rule_version`` produces a different PK (acceptable)."""
    with Session(engine) as session, session.begin():
        _add_recommendation(session, rule_version="v1.0")
        _add_recommendation(session, rule_version="v1.1")
        assert session.query(Recommendation).count() == 2


def test_deterministic_uuid_byte_truncation_distinguishes_rule_version():
    """A change of ``rule_version`` flips the identity byte-level."""
    inputs = {
        "user_id": 1,
        "goal_id": 1,
        "forecast_version_id": _FORECAST_VERSION_ID,
        "recommendation_kind": "increase_contribution",
        "derivation_schema_version": "atlas-recommendation/v1",
    }
    a = recommendation_id_for(rule_version="v1.0", **inputs)
    b = recommendation_id_for(rule_version="v1.1", **inputs)
    # Full SHA-256 digests differ at multiple byte positions.
    digest_a = canonical_digest({**inputs, "rule_version": "v1.0"}, b"atlas-recommendation/v1:")
    digest_b = canonical_digest({**inputs, "rule_version": "v1.1"}, b"atlas-recommendation/v1:")
    assert digest_a != digest_b
    # Their first 16 bytes also differ.
    assert digest_a[:16] != digest_b[:16]
    # The formatted UUIDs differ accordingly.
    assert a != b
    # Both formatted UUIDs are lowercase canonical 36-char IDs.
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", a)
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", b)
