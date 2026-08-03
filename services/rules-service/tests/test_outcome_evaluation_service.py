"""Focused Phase 3 outcome-evaluation service contracts."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.forecasts.decision_journal_service import DecisionJournalService
from app.forecasts.outcome_evaluation_service import (
    OutcomeEvaluationConflictError,
    OutcomeEvaluationNotFoundError,
    OutcomeEvaluationService,
)
from tests._commit3_world import primary_goal_id, primary_user_id, recommendation_row_id, world_with_recommendation


def _accepted_decision(session: Session) -> str:
    return DecisionJournalService(session).record(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        recommendation_id=recommendation_row_id(), decision_action="accept",
        raw_idempotency_key="phase3-accepted-decision",
    ).entry.id


def test_measured_outcome_requires_authoritative_evidence(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        decision_id = _accepted_decision(session)
        with pytest.raises(OutcomeEvaluationNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=1, goal_id=1, recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=decision_id, lifecycle="measured",
                raw_idempotency_key="phase3-missing-evidence",
            )


def test_outcome_requires_acceptance_and_is_idempotent(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        decision_id = _accepted_decision(session)
        service = OutcomeEvaluationService(session)
        args = dict(
            user_id=1, goal_id=1, recommendation_id=recommendation_row_id(),
            decision_journal_entry_id=decision_id, lifecycle="measured",
            raw_idempotency_key="phase3-measured-outcome",
            authoritative_evidence_reference="verified-statement-period-2026-07",
            measurement_window_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            measurement_window_end=datetime(2026, 7, 31, tzinfo=timezone.utc),
            inputs={"source": "verified_statement"}, result={"status": "observed"},
            confidence="high", explanation="Authoritative statement evidence was evaluated.",
        )
        first = service.record(**args)
        replay = service.record(**args)
        assert not first.replayed and replay.replayed
        assert first.evaluation.id == replay.evaluation.id
        assert session.execute(text("SELECT count(*) FROM outcome_evaluations")).scalar_one() == 1


def test_outcome_rejects_nonaccepted_decision(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        rejected_id = DecisionJournalService(session).record(
            user_id=1, goal_id=1, recommendation_id=recommendation_row_id(),
            decision_action="reject", raw_idempotency_key="phase3-rejected-decision",
        ).entry.id
        with pytest.raises(OutcomeEvaluationNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=1, goal_id=1, recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=rejected_id, lifecycle="pending",
                raw_idempotency_key="phase3-rejected-outcome",
            )


def test_outcome_same_key_different_request_conflicts(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        decision_id = _accepted_decision(session)
        service = OutcomeEvaluationService(session)
        service.record(user_id=1, goal_id=1, recommendation_id=recommendation_row_id(), decision_journal_entry_id=decision_id, lifecycle="pending", raw_idempotency_key="phase3-conflict")
        with pytest.raises(OutcomeEvaluationConflictError):
            service.record(user_id=1, goal_id=1, recommendation_id=recommendation_row_id(), decision_journal_entry_id=decision_id, lifecycle="not_yet_measurable", raw_idempotency_key="phase3-conflict")


def test_outcome_replay_rejects_changed_measured_evidence(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        decision_id = _accepted_decision(session)
        service = OutcomeEvaluationService(session)
        args = dict(user_id=1, goal_id=1, recommendation_id=recommendation_row_id(), decision_journal_entry_id=decision_id, lifecycle="measured", raw_idempotency_key="phase3-replay-content", authoritative_evidence_reference="verified-ref", measurement_window_start=datetime(2026, 7, 1, tzinfo=timezone.utc), measurement_window_end=datetime(2026, 7, 31, tzinfo=timezone.utc), inputs={"source": "verified_statement"}, result={"status": "observed"}, confidence="high", explanation="Evidence evaluated.")
        service.record(**args)
        with pytest.raises(OutcomeEvaluationConflictError):
            service.record(**{**args, "result": {"status": "not_observed"}})


def test_outcome_rejects_sensitive_evidence_fields(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        decision_id = _accepted_decision(session)
        with pytest.raises(OutcomeEvaluationNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=1, goal_id=1, recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=decision_id, lifecycle="measured",
                raw_idempotency_key="phase3-sensitive", authoritative_evidence_reference="verified-ref",
                measurement_window_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
                measurement_window_end=datetime(2026, 7, 31, tzinfo=timezone.utc),
                inputs={"account_balance": "redacted"}, result={"status": "observed"},
                confidence="high", explanation="Evidence evaluated.",
            )
        with pytest.raises(OutcomeEvaluationNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=1, goal_id=1, recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=decision_id, lifecycle="measured",
                raw_idempotency_key="phase3-sensitive-value", authoritative_evidence_reference="verified-ref",
                measurement_window_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
                measurement_window_end=datetime(2026, 7, 31, tzinfo=timezone.utc),
                inputs={"source": "statement says account balance is $42,000"}, result={"status": "observed"},
                confidence="high", explanation="Evidence evaluated.",
            )


def test_outcome_database_triggers_reject_mutation(world_with_recommendation):
    with Session(world_with_recommendation) as session:
        decision_id = _accepted_decision(session)
        evaluation = OutcomeEvaluationService(session).record(
            user_id=1, goal_id=1, recommendation_id=recommendation_row_id(),
            decision_journal_entry_id=decision_id, lifecycle="pending",
            raw_idempotency_key="phase3-immutable",
        ).evaluation
        with pytest.raises(Exception):
            session.execute(text("UPDATE outcome_evaluations SET lifecycle = 'measured' WHERE id = :id"), {"id": evaluation.id})
        session.rollback()
        with pytest.raises(Exception):
            session.execute(text("DELETE FROM outcome_evaluations WHERE id = :id"), {"id": evaluation.id})
