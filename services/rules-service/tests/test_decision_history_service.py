"""Focused Phase 4 decision-history append-only and recovery tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import register_sqlite_compat
from app.forecasts.decision_history_service import DecisionHistoryConflictError, DecisionHistoryNotFoundError, DecisionHistoryService, DecisionHistoryValidationError
from app.models import DecisionAuditEvent, DecisionHistoryEntry, DecisionJournalEntry
from app.models.decision_journal_identities import canonical_idempotency_key_hash, decision_journal_id_for
from tests.test_outcome_evaluation_migration import _plant_world

ROOT = Path(__file__).resolve().parent.parent
REVISION = "V0a1b2c3d4e5"


@pytest.fixture
def world(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'history.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = Config(str(ROOT / "alembic.ini")); cfg.set_main_option("script_location", str(ROOT / "alembic")); cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, REVISION)
        engine = create_engine(url); register_sqlite_compat(engine)
        with Session(engine) as session, session.begin():
            planted = _plant_world(session, local_user_sub="history-user", email="history@example.com")
        yield engine, planted


def _record(session, world, *, key="history-key", supersedes=None, rationale="Reasoned choice"):
    return DecisionHistoryService(session).record(user_id=world["user"], goal_id=world["goal"], recommendation_id=world["recommendation"], decision_journal_entry_id=world["decision"], alternatives=["do_nothing", "accept"], rationale=rationale, raw_idempotency_key=key, supersedes_history_entry_id=supersedes)


def test_record_replay_audit_and_correction_chain(world):
    engine, ids = world
    with Session(engine) as session:
        first = _record(session, ids)
        replay = _record(session, ids)
        correction = _record(session, ids, key="history-correct", supersedes=first.entry.id, rationale="Corrected rationale")
        assert replay.replayed is True and replay.entry.id == first.entry.id
        assert correction.entry.supersedes_history_entry_id == first.entry.id
        assert session.query(DecisionAuditEvent).count() == 2
        assert {event.event_action for event in session.query(DecisionAuditEvent)} == {"recorded", "corrected"}


def test_conflict_and_validation_are_bounded(world):
    engine, ids = world
    with Session(engine) as session:
        _record(session, ids)
        with pytest.raises(DecisionHistoryConflictError): _record(session, ids, rationale="Different")
        # The same replay token cannot be recycled to another decision row.
        other_key_hash = canonical_idempotency_key_hash("another-decision")
        other_decision_id = decision_journal_id_for(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_action="reject", idempotency_key_hash=other_key_hash, schema_version="decision/v1")
        session.add(DecisionJournalEntry(id=other_decision_id, user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_action="reject", schema_version="decision/v1", idempotency_key_hash=other_key_hash, currency="USD", decided_at=__import__("datetime").datetime.now()))
        session.commit()
        with pytest.raises(DecisionHistoryConflictError):
            DecisionHistoryService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=other_decision_id, alternatives=["do_nothing"], rationale="x", raw_idempotency_key="history-key")
        with pytest.raises(DecisionHistoryValidationError):
            DecisionHistoryService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], alternatives=["accept"], rationale="x", raw_idempotency_key="bad")


def test_owner_indistinguishability_and_append_only_guards(world):
    engine, ids = world
    with Session(engine) as session:
        entry_id = _record(session, ids).entry.id
        with pytest.raises(DecisionHistoryNotFoundError):
            DecisionHistoryService(session).record(user_id=999, goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], alternatives=["do_nothing"], rationale="x", raw_idempotency_key="cross")
    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE decision_history_entries SET rationale='rewrite' WHERE id=:id"), {"id": entry_id}); session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM decision_audit_events")); session.commit()
        session.rollback()
        # Direct SQL cannot forge an audit event for another owner.
        with pytest.raises(IntegrityError):
            session.execute(text("INSERT INTO decision_audit_events (id, history_entry_id, user_id, goal_id, recommendation_id, decision_journal_entry_id, event_action, actor_scope, correlation_hash, policy_result, occurred_at) VALUES ('00000000-0000-4000-8000-000000000099', :history, 999, :goal, :rec, :decision, 'recorded', 'owner', :hash, 'recorded', CURRENT_TIMESTAMP)"), {"history": entry_id, "goal": ids["goal"], "rec": ids["recommendation"], "decision": ids["decision"], "hash": "c" * 64})
            session.commit()


def test_migration_round_trip_on_empty_history(monkeypatch):
    """A clean database can reverse the additive migration; populated history cannot."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'round-trip.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = Config(str(ROOT / "alembic.ini")); cfg.set_main_option("script_location", str(ROOT / "alembic")); cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, REVISION)
        command.downgrade(cfg, "U9a1b2c3d4e5")
