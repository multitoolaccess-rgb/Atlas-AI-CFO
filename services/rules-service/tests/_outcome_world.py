"""Phase 3 Slice 1 outcome-evaluation test world (local to outcome tests).

Reuses the Phase 2 commit-3 world (:mod:`tests._commit3_world` — users,
goals, forecast, forecast_version, recommendation) and extends it with
decision journal entries so the outcome evaluation service has a real
accepted decision to evaluate against.

The decision ids are deterministic (``decision_journal_id_for``) and the
raw idempotency keys used to plant them are fixed strings, so the
``*_decision_row_id()`` accessors return the exact ids the fixtures
planted.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.forecasts.recommendation_schemas import DECISION_JOURNAL_SCHEMA_VERSION
from app.models import DecisionJournalEntry
from app.models.decision_journal_identities import (
    canonical_idempotency_key_hash,
    decision_journal_id_for,
)

from tests._commit3_world import (
    primary_goal_id,
    primary_user_id,
    recommendation_row_id,
    world_with_recommendation,
)


def decision_row_id(*, action: str) -> str:
    """Deterministic decision id the world plants for ``action``."""
    idem_hash = canonical_idempotency_key_hash(f"outcome-world-decision-{action}")
    return decision_journal_id_for(
        user_id=primary_user_id(),
        goal_id=primary_goal_id(),
        recommendation_id=recommendation_row_id(),
        decision_action=action,
        idempotency_key_hash=idem_hash,
        schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
    )


def accepted_decision_row_id() -> str:
    return decision_row_id(action="accept")


def rejected_decision_row_id() -> str:
    return decision_row_id(action="reject")


def deferred_decision_row_id() -> str:
    return decision_row_id(action="defer")


def _plant_decision(engine, *, action: str) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as session, session.begin():
        session.add(
            DecisionJournalEntry(
                id=decision_row_id(action=action),
                recommendation_id=recommendation_row_id(),
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                decision_action=action,
                schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
                idempotency_key_hash=canonical_idempotency_key_hash(
                    f"outcome-world-decision-{action}"
                ),
                currency="USD",
                decided_at=now,
            )
        )
        session.flush()


@pytest.fixture
def world_with_accepted_decision(world_with_recommendation):
    """Commit-3 world + an ``accept`` decision for the recommendation."""
    _plant_decision(world_with_recommendation, action="accept")
    return world_with_recommendation


@pytest.fixture
def world_with_rejected_decision(world_with_recommendation):
    """Commit-3 world + a ``reject`` decision for the recommendation."""
    _plant_decision(world_with_recommendation, action="reject")
    return world_with_recommendation


@pytest.fixture
def world_with_deferred_decision(world_with_recommendation):
    """Commit-3 world + a ``defer`` decision for the recommendation."""
    _plant_decision(world_with_recommendation, action="defer")
    return world_with_recommendation


__all__ = [
    "world_with_accepted_decision",
    "world_with_rejected_decision",
    "world_with_deferred_decision",
    "decision_row_id",
    "accepted_decision_row_id",
    "rejected_decision_row_id",
    "deferred_decision_row_id",
]
