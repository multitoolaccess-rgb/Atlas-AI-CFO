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
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import register_sqlite_compat
from app.forecasts.decision_history_service import DecisionHistoryConflictError, DecisionHistoryNotFoundError, DecisionHistoryService, DecisionHistoryValidationError
from app.forecasts.outcome_evaluation_service import OutcomeEvaluationService
from app.models import DecisionAuditEvent, DecisionHistoryEntry, DecisionJournalEntry, Goal
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
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text("INSERT INTO decision_audit_events (id, history_entry_id, user_id, goal_id, recommendation_id, decision_journal_entry_id, event_action, actor_scope, correlation_hash, policy_result, occurred_at) VALUES ('00000000-0000-4000-8000-000000000097', :history, :user, :goal, :rec, :decision, 'evaluated', 'owner', :hash, 'recorded', CURRENT_TIMESTAMP)"), {"history": entry_id, "user": ids["user"], "goal": ids["goal"], "rec": ids["recommendation"], "decision": ids["decision"], "hash": "e" * 64})
            session.commit()
        session.rollback()
        outcome = OutcomeEvaluationService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], lifecycle="pending", raw_idempotency_key="sql-audit-outcome").entry
        with pytest.raises(IntegrityError):
            session.execute(text("INSERT INTO decision_audit_events (id, history_entry_id, user_id, goal_id, recommendation_id, decision_journal_entry_id, outcome_evaluation_id, event_action, actor_scope, correlation_hash, policy_result, occurred_at) VALUES ('00000000-0000-4000-8000-000000000096', :history, :user, :goal, :rec, :decision, :outcome, 'corrected', 'owner', :hash, 'recorded', CURRENT_TIMESTAMP)"), {"history": entry_id, "user": ids["user"], "goal": ids["goal"], "rec": ids["recommendation"], "decision": ids["decision"], "outcome": outcome.id, "hash": "f" * 64})
            session.commit()
        session.rollback()
        other_goal = Goal(user_id=ids["user"], name="Same owner, other goal", target_amount=1, priority=0)
        session.add(other_goal); session.commit()
        # Same user is not sufficient: the recommendation and decision tuple
        # must resolve to this exact goal, even for direct SQL.
        with pytest.raises(IntegrityError):
            session.execute(text("INSERT INTO decision_history_entries (id,user_id,goal_id,recommendation_id,decision_journal_entry_id,decision_action,alternatives_json,rationale,schema_version,idempotency_key_hash,currency,recorded_at) VALUES ('00000000-0000-4000-8000-000000000098',:user,:goal,:rec,:decision,'accept','[\"do_nothing\"]','forged','history/v1',:hash,'USD',CURRENT_TIMESTAMP)"), {"user": ids["user"], "goal": other_goal.id, "rec": ids["recommendation"], "decision": ids["decision"], "hash": "d" * 64})
            session.commit()


def test_migration_round_trip_on_empty_history(monkeypatch):
    """A clean database can reverse the additive migration; populated history cannot."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'round-trip.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = Config(str(ROOT / "alembic.ini")); cfg.set_main_option("script_location", str(ROOT / "alembic")); cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, REVISION)
        command.downgrade(cfg, "U9a1b2c3d4e5")


def test_evaluated_audit_links_only_matching_safe_outcome(world):
    engine, ids = world
    with Session(engine) as session:
        outcome = OutcomeEvaluationService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], lifecycle="pending", raw_idempotency_key="history-outcome").entry
        result = _record(session, ids, key="history-evaluated")
        # A linked outcome creates an immutable, bounded evaluated audit event;
        # no outcome content enters this service's contract.
        linked = DecisionHistoryService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], alternatives=["do_nothing", "accept"], rationale="Measured later", raw_idempotency_key="history-evaluated-2", outcome_evaluation_id=outcome.id)
        event = session.query(DecisionAuditEvent).filter_by(history_entry_id=linked.entry.id, event_action="evaluated").one()
        assert result.entry.id != linked.entry.id
        assert event.event_action == "evaluated" and event.outcome_evaluation_id == outcome.id
        # Same replay key cannot silently add/remove/change outcome linkage.
        with pytest.raises(DecisionHistoryConflictError):
            DecisionHistoryService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], alternatives=["do_nothing", "accept"], rationale="Measured later", raw_idempotency_key="history-evaluated-2")


def test_correction_with_outcome_keeps_both_append_only_audit_events(world):
    engine, ids = world
    with Session(engine) as session:
        prior = _record(session, ids, key="prior-correction")
        outcome = OutcomeEvaluationService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], lifecycle="pending", raw_idempotency_key="correction-outcome").entry
        corrected = _record(session, ids, key="corrected-with-outcome", supersedes=prior.entry.id, rationale="Corrected with later measurement")
        # record the correction-linked outcome as the same canonical request
        # (new idempotency key is intentional; it is a second immutable row).
        linked = DecisionHistoryService(session).record(user_id=ids["user"], goal_id=ids["goal"], recommendation_id=ids["recommendation"], decision_journal_entry_id=ids["decision"], alternatives=["do_nothing", "accept"], rationale="Corrected and measured", raw_idempotency_key="corrected-measured", supersedes_history_entry_id=prior.entry.id, outcome_evaluation_id=outcome.id)
        events = session.query(DecisionAuditEvent).filter_by(history_entry_id=linked.entry.id).all()
        assert corrected.entry.supersedes_history_entry_id == prior.entry.id
        assert {event.event_action for event in events} == {"corrected", "evaluated"}
        assert next(event for event in events if event.event_action == "evaluated").outcome_evaluation_id == outcome.id


def test_operational_race_recovers_canonical_winner_without_details():
    """A commit race re-reads only the canonical winner and reports replay."""
    from types import SimpleNamespace
    from app.models import Recommendation

    class RaceSession:
        failed = False
        added = ()
        def get(self, model, ident):
            if model is Goal: return SimpleNamespace(user_id=1)
            if model is Recommendation: return SimpleNamespace(user_id=1, goal_id=1)
            if model is DecisionJournalEntry: return SimpleNamespace(user_id=1, goal_id=1, recommendation_id="00000000-0000-4000-8000-000000000001", decision_action="accept")
            if model is DecisionHistoryEntry:
                return self.added[0] if self.failed and self.added else None
            return None
        def scalar(self, statement): return None
        def add_all(self, entries): self.added = tuple(entries)
        def commit(self): self.failed = True; raise OperationalError("INSERT", {}, RuntimeError("locked"))
        def rollback(self): pass

    result = DecisionHistoryService(RaceSession()).record(user_id=1, goal_id=1, recommendation_id="00000000-0000-4000-8000-000000000001", decision_journal_entry_id="00000000-0000-4000-8000-000000000002", alternatives=["do_nothing", "accept"], rationale="Race-safe", raw_idempotency_key="race-key")
    assert result.replayed is True


def test_operational_race_winner_requires_equivalent_outcome_linkage():
    """A retry after an operational race compares the opaque outcome ID too."""
    from types import SimpleNamespace
    from app.models import Recommendation

    outcome_id = "00000000-0000-4000-8000-000000000003"

    class RaceSession:
        failed = False
        added = ()
        scalar_calls = 0
        def get(self, model, ident):
            if model is Goal: return SimpleNamespace(user_id=1)
            if model is Recommendation: return SimpleNamespace(user_id=1, goal_id=1)
            if model is DecisionJournalEntry: return SimpleNamespace(user_id=1, goal_id=1, recommendation_id="00000000-0000-4000-8000-000000000001", decision_action="accept")
            if model.__name__ == "OutcomeEvaluation": return SimpleNamespace(user_id=1, goal_id=1, recommendation_id="00000000-0000-4000-8000-000000000001", decision_journal_entry_id="00000000-0000-4000-8000-000000000002")
            if model is DecisionHistoryEntry: return self.added[0] if self.failed and self.added else None
            return None
        def scalar(self, statement):
            self.scalar_calls += 1
            return outcome_id if self.failed else None
        def add_all(self, entries): self.added = tuple(entries)
        def commit(self): self.failed = True; raise OperationalError("INSERT", {}, RuntimeError("locked"))
        def rollback(self): pass

    kwargs = dict(user_id=1, goal_id=1, recommendation_id="00000000-0000-4000-8000-000000000001", decision_journal_entry_id="00000000-0000-4000-8000-000000000002", alternatives=["do_nothing", "accept"], rationale="Race-safe", raw_idempotency_key="race-outcome", outcome_evaluation_id=outcome_id)
    assert DecisionHistoryService(RaceSession()).record(**kwargs).replayed is True
    absent = {key: value for key, value in kwargs.items() if key != "outcome_evaluation_id"}
    with pytest.raises(DecisionHistoryConflictError):
        DecisionHistoryService(RaceSession()).record(**absent)
    changed = {**kwargs, "outcome_evaluation_id": "00000000-0000-4000-8000-000000000004"}
    with pytest.raises(DecisionHistoryConflictError):
        DecisionHistoryService(RaceSession()).record(**changed)
