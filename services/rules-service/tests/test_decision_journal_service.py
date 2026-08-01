"""DB-level tests for :class:`DecisionJournalService`.

The world fixtures live in :mod:`tests._commit3_world` and use
``alembic.command.upgrade`` so the Phase 2 ``decision_journal_entries``
immutability triggers ARE installed.  Every test opens + asserts
inside a single ``with Session(engine)`` block so the returned ORM
object stays attached while attributes are read.

Coverage invariants:

* ownership-before-existence (goal + recommendation)
* accept | reject | defer persistence with deterministic PK
* idempotent retry ⇒ identical row, ``replayed=True``
* same raw idempotency key + different ``decision_action`` ⇒
  ``DecisionConflictError`` carrying only ``current_etag``
* same idempotency key + different ``recommendation_id`` ⇒
  ``DecisionConflictError``
* same idempotency key + different ``note`` ⇒
  ``DecisionConflictError``
* raw ``Idempotency-Key`` never appears on disk or in error messages
* race-handling: pre-seeded winner + new-session call ⇒
  ``replayed=True``
* Phase 1 immutable DB protections still block UPDATE / DELETE at
  the SQL layer
* failed transaction leaves no partial journal row
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.forecasts.decision_journal_service import (
    DecisionConflictError,
    DecisionJournalService,
    GoalNotFoundError,
    IdempotencyKeyRequiredError,
    JournalWriteResult,
    RecommendationNotFoundError,
    decision_etag_for,
)
from app.models import DecisionJournalEntry
from app.models.decision_journal_identities import (
    canonical_idempotency_key_hash,
    decision_journal_id_for,
    recommendation_id_for,
)

from tests._commit3_world import (
    cross_user_id,
    primary_goal_id,
    primary_user_id,
    raw_idempotency_key,
    recommendation_row_id,
    world_with_recommendation,
    world_engine,
)


# ---------------------------------------------------------------------------
# Ownership-before-existence
# ---------------------------------------------------------------------------


def test_service_rejects_cross_user_goal(world_with_recommendation):
    rec_id = recommendation_row_id()
    with Session(world_with_recommendation) as session:
        with pytest.raises(GoalNotFoundError):
            DecisionJournalService(session).record(
                user_id=cross_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id=rec_id,
                decision_action="accept",
                raw_idempotency_key="k-cross-goal-1",
            )


def test_service_rejects_cross_user_recommendation(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        with pytest.raises(RecommendationNotFoundError):
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id="00000000-0000-4000-8000-000000000099",
                decision_action="accept",
                raw_idempotency_key="k-cross-rec-1",
            )


# ---------------------------------------------------------------------------
# Idempotency-Key required + hashed-only storage
# ---------------------------------------------------------------------------


def test_service_rejects_empty_idempotency_key(world_with_recommendation):
    rec_id = recommendation_row_id()
    with Session(world_with_recommendation) as session:
        with pytest.raises(IdempotencyKeyRequiredError):
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id=rec_id,
                decision_action="accept",
                raw_idempotency_key="",
            )


def test_service_never_persists_raw_idempotency_key(world_with_recommendation, raw_idempotency_key):
    rec_id = recommendation_row_id()
    raw = raw_idempotency_key
    with Session(world_with_recommendation) as session:
        result = DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key=raw,
        )
        journal_id = result.entry.id
        # Confirm the live ORM state never references the raw key.
        entry_attrs = (
            result.entry.id,
            result.entry.recommendation_id,
            result.entry.user_id,
            result.entry.goal_id,
            result.entry.decision_action,
            result.entry.schema_version,
            result.entry.idempotency_key_hash,
            result.entry.currency,
            result.entry.note,
            result.entry.metadata_json,
        )
        assert raw not in (str(v) for v in entry_attrs if v is not None)
    # Confirm the persisted DB column carries the canonical canonical
    # SHA-256 hex digest and never the raw key.  A loose ``row_dump``
    # substring scan was unreliable because fixture substrings like
    # ``"atlas"`` / ``"v1"`` could collide with adjacent column values;
    # the bounded assertions below target the exact contract.
    with Session(world_with_recommendation) as session:
        stored_hash = session.execute(
            text("SELECT idempotency_key_hash FROM decision_journal_entries WHERE id = :id"),
            {"id": journal_id},
        ).scalar_one()
        assert stored_hash == canonical_idempotency_key_hash(raw)
        assert stored_hash != raw
        assert len(stored_hash) == 64
        # Strict format: 64-char lowercase hex.
        assert re.fullmatch(r"[0-9a-f]{64}", stored_hash)


# ---------------------------------------------------------------------------
# accept / reject / defer persistence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["accept", "reject", "defer"])
def test_service_persists_each_bounded_action(world_with_recommendation, action):
    rec_id = recommendation_row_id()
    key = f"key-{action}-1"
    with Session(world_with_recommendation) as session:
        result = DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action=action,
            raw_idempotency_key=key,
        )
        assert isinstance(result, JournalWriteResult)
        assert result.replayed is False
        assert result.conflict is False
        assert result.current_etag == decision_etag_for(result.entry.id)
        # Sanity: row exists with the bounded action.
        stored = session.execute(
            text(
                "SELECT decision_action FROM decision_journal_entries WHERE id = :id"
            ),
            {"id": result.entry.id},
        ).scalar_one()
        assert stored == action


def test_service_rejects_unknown_action(world_with_recommendation):
    rec_id = recommendation_row_id()
    with Session(world_with_recommendation) as session:
        with pytest.raises(RecommendationNotFoundError):
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id=rec_id,
                decision_action="drop",
                raw_idempotency_key="k-bad-action-1",
            )


# ---------------------------------------------------------------------------
# Idempotent replay ↔ conflict detection
# ---------------------------------------------------------------------------


def test_service_idempotent_replay_returns_same_row(world_with_recommendation):
    rec_id = recommendation_row_id()
    with Session(world_with_recommendation) as session:
        first = DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key="k-replay-1",
        )
        first_id = first.entry.id
    with Session(world_with_recommendation) as session:
        replay = DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key="k-replay-1",
        )
        assert first_id == replay.entry.id
        assert replay.replayed is True
        assert replay.conflict is False


def test_service_same_key_different_action_raises_conflict(world_with_recommendation):
    rec_id = recommendation_row_id()
    with Session(world_with_recommendation) as session:
        first = DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key="k-conflict-action",
        )
        first_journal_id = first.entry.id
    with Session(world_with_recommendation) as session:
        with pytest.raises(DecisionConflictError) as captured:
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id=rec_id,
                decision_action="reject",
                raw_idempotency_key="k-conflict-action",
            )
    # The ETag must match the FIRST journal row's identity, not the
    # recommendation id (those are different identities).
    assert captured.value.code == "decision_conflict"
    assert captured.value.current_etag == decision_etag_for(first_journal_id)
    assert captured.value.current_etag.endswith("-d1")
    assert len(captured.value.current_etag) == 36 + len("-d1")


def test_service_same_key_different_note_raises_conflict(world_with_recommendation):
    rec_id = recommendation_row_id()
    with Session(world_with_recommendation) as session:
        DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key="k-conflict-note",
            note="ok",
        )
    with Session(world_with_recommendation) as session:
        with pytest.raises(DecisionConflictError):
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id=rec_id,
                decision_action="accept",
                raw_idempotency_key="k-conflict-note",
                note="changed",
            )


def test_service_conflict_error_carries_only_etag(world_with_recommendation):
    rec_id = recommendation_row_id()
    raw_key = "k-conflict-payload"
    note_text = "initial"
    with Session(world_with_recommendation) as session:
        DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key=raw_key,
            note=note_text,
        )
    with Session(world_with_recommendation) as session:
        with pytest.raises(DecisionConflictError) as captured:
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id=rec_id,
                decision_action="reject",
                raw_idempotency_key=raw_key,
                note=note_text,
            )
    surf = (captured.value.current_etag + " " + captured.value.code).lower()
    # These must NOT appear on the exception surface.
    for sensitive in (
        raw_key.lower(),
        "accept",
        "reject",
        "defer",
        note_text.lower(),
        rec_id.lower(),
    ):
        assert sensitive not in surf, f"sensitive leak on conflict surface: {sensitive!r}"
    # The ETag does carry the journal_id (which is necessary for the
    # client to reconnect to the prior decision); only the rec_id is
    # confirmed absent.
    assert not surf.replace("-d1", "").endswith(rec_id.lower())


def test_service_same_key_different_recommendation_raises_conflict(world_engine):
    """Plant TWO recommendations on the same goal; same key + different rec ⇒ conflict."""
    rec_a = recommendation_id_for(
        user_id=primary_user_id(),
        goal_id=primary_goal_id(),
        forecast_version_id="00000000-0000-4000-8000-000000000020",
        recommendation_kind="hold",
        rule_version="v1.0",
        derivation_schema_version="atlas-recommendation/v1",
    )
    rec_b = recommendation_id_for(
        user_id=primary_user_id(),
        goal_id=primary_goal_id(),
        forecast_version_id="00000000-0000-4000-8000-000000000020",
        recommendation_kind="increase_contribution",
        rule_version="v1.0",
        derivation_schema_version="atlas-recommendation/v1",
    )
    assert rec_a != rec_b
    now = datetime.now(timezone.utc)
    with Session(world_engine) as session, session.begin():
        session.execute(
            text(
                "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                "forecast_input_state_hash, recommendation_kind, rule_version, "
                "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                "expected_impact_max_decimal, confidence_score, assumptions_json, "
                "risks_json, freshness_json, provenance_json, derived_at, data_as_of) "
                "VALUES (:id, 1, 1, '00000000-0000-4000-8000-000000000020', :h, 'hold', "
                "'v1.0', 'atlas-recommendation/v1', 'USD', 'r1', 0.0, 0.0, 0.95, "
                "'{}', '[]', '{}', '{}', :now, :now)"
            ),
            {"id": rec_a, "h": "a" * 64, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                "forecast_input_state_hash, recommendation_kind, rule_version, "
                "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                "expected_impact_max_decimal, confidence_score, assumptions_json, "
                "risks_json, freshness_json, provenance_json, derived_at, data_as_of) "
                "VALUES (:id, 1, 1, '00000000-0000-4000-8000-000000000020', :h, "
                "'increase_contribution', 'v1.0', 'atlas-recommendation/v1', 'USD', "
                "'r2', 0.0, 0.0, 0.65, '{}', '[]', '{}', '{}', :now, :now)"
            ),
            {"id": rec_b, "h": "a" * 64, "now": now},
        )
    with Session(world_engine) as session:
        DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_a,
            decision_action="accept",
            raw_idempotency_key="k-conflict-rec",
        )
    with Session(world_engine) as session:
        with pytest.raises(DecisionConflictError):
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id=rec_b,
                decision_action="accept",
                raw_idempotency_key="k-conflict-rec",
            )


# ---------------------------------------------------------------------------
# Race recovery: pre-seeded winner + new-session call replays
# ---------------------------------------------------------------------------


def test_service_race_recovery_returns_committed_winner(world_with_recommendation):
    """Simulate a parallel-winner race by pre-seeding the deterministic PK row.

    The pre-seeded writer-A winner and the synchronous writer-B request
    must share the exact canonical payload (including ``note`` and
    ``schema_version``) so the service's ``_canonical_fields_match``
    check on the recovered row returns ``replayed=True`` rather than
    ``DecisionConflictError``.  A different-payload race is exercised
    separately in :func:`test_service_same_key_different_note_raises_conflict`.
    """
    from app.forecasts.recommendation_schemas import DECISION_JOURNAL_SCHEMA_VERSION
    rec_id = recommendation_row_id()
    raw_key = "k-race-1"
    idemp_hash = canonical_idempotency_key_hash(raw_key)
    # Mirror the service's ``schema_version`` default exactly so the
    # deterministic PK matches across seed and call.
    journal_id = decision_journal_id_for(
        user_id=primary_user_id(),
        goal_id=primary_goal_id(),
        recommendation_id=rec_id,
        decision_action="accept",
        idempotency_key_hash=idemp_hash,
        schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
    )
    now = datetime.now(timezone.utc)
    shared_note = "racing writers agree on this note"
    with Session(world_with_recommendation) as session, session.begin():
        session.add(
            DecisionJournalEntry(
                id=journal_id,
                recommendation_id=rec_id,
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                decision_action="accept",
                schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
                idempotency_key_hash=idemp_hash,
                currency="USD",
                note=shared_note,
                metadata_json=None,
                decided_at=now,
            )
        )
        session.flush()
    with Session(world_with_recommendation) as session:
        result = DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key=raw_key,
            note=shared_note,
        )
        assert result.replayed is True
        assert result.conflict is False
        assert result.entry.note == shared_note


# ---------------------------------------------------------------------------
# Phase 2 immutable DB protections remain effective through service ops
# ---------------------------------------------------------------------------


def test_phase2_immutable_trigger_still_blocks_update(world_with_recommendation):
    rec_id = recommendation_row_id()
    raw_key = "k-immut-bypass-1"
    with Session(world_with_recommendation) as session:
        DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key=raw_key,
        )
    with Session(world_with_recommendation) as session:
        # SQLite ``RAISE(ABORT, ...)`` raises ``IntegrityError``; the
        # statement fails inside ``session.execute(...)`` before any
        # explicit ``commit`` so the assertion wraps the execute call.
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "UPDATE decision_journal_entries SET note = 'tampered' "
                    "WHERE user_id = 1"
                ),
            )


def test_phase2_immutable_trigger_still_blocks_delete(world_with_recommendation):
    rec_id = recommendation_row_id()
    raw_key = "k-immut-bypass-2"
    with Session(world_with_recommendation) as session:
        DecisionJournalService(session).record(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            recommendation_id=rec_id,
            decision_action="accept",
            raw_idempotency_key=raw_key,
        )
    with Session(world_with_recommendation) as session:
        # Same SQLite ``RAISE(ABORT, ...)`` semantics as in the UPDATE
        # test; the statement raises ``IntegrityError`` inside
        # ``session.execute(...)`` so we wrap the call there.
        with pytest.raises(IntegrityError):
            session.execute(
                text("DELETE FROM decision_journal_entries WHERE user_id = 1"),
            )


# ---------------------------------------------------------------------------
# Rollback behaviour (failed transaction leaves no partial journal row)
# ---------------------------------------------------------------------------


def test_failed_record_does_not_persist_partial_row(world_engine):
    before = 0
    with Session(world_engine) as session:
        before = session.execute(
            text("SELECT COUNT(*) FROM decision_journal_entries")
        ).scalar_one()
    assert before == 0
    with Session(world_engine) as session:
        with pytest.raises(RecommendationNotFoundError):
            DecisionJournalService(session).record(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                recommendation_id="00000000-0000-4000-8000-000000000099",
                decision_action="accept",
                raw_idempotency_key="k-rollback-1",
            )
    with Session(world_engine) as session:
        after = session.execute(
            text("SELECT COUNT(*) FROM decision_journal_entries")
        ).scalar_one()
    assert after == 0
