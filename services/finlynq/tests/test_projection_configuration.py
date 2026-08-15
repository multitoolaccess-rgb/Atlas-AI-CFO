"""Synthetic tests for the bounded GoalProjectionConfig operator boundary."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Goal, GoalProjectionConfig, User
from app.projection_state.configuration import (
    ProjectionConfigurationError,
    apply_configuration,
    plan_configuration,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(local_user_sub="atlas-config-user", email="config@example.com", hashed_password="x", is_active=True)
    session.add(user)
    session.flush()
    goal = Goal(user_id=user.id, name="Synthetic Goal", target_amount=1000.0, horizon_years=10, is_archived=False)
    session.add(goal)
    session.commit()
    try:
        yield session, user, goal
    finally:
        session.close()


def test_dry_run_resolves_one_owned_goal_without_mutation(db):
    session, user, goal = db
    _, resolved_goal, request, existing = plan_configuration(
        session,
        user_sub=user.local_user_sub,
        monthly_contribution="500.00",
        observed_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    assert resolved_goal.id == goal.id
    assert request.monthly_contribution == Decimal("500.00")
    assert request.currency_code == "USD"
    assert request.projection_kind == "net_worth"
    assert request.source_reference == "operator-confirmed-personal-plan"
    assert existing is None
    assert session.scalar(select(GoalProjectionConfig)) is None


def test_apply_is_decimal_safe_and_idempotent_for_same_intent(db):
    session, user, goal = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    first = apply_configuration(session, user_sub=user.local_user_sub, monthly_contribution="500.00", goal_id=goal.id, observed_at=observed)
    second = apply_configuration(session, user_sub=user.local_user_sub, monthly_contribution=Decimal("500.00"), goal_id=goal.id, observed_at=datetime(2026, 8, 15, 0, 1, tzinfo=timezone.utc))
    config = session.scalar(select(GoalProjectionConfig))
    assert first == {"status": "recorded", "projection": "ready"}
    assert second == {"status": "idempotent_replay", "projection": "ready"}
    assert config is not None
    assert config.monthly_contribution == Decimal("500.00")
    assert config.currency_code == "USD"
    assert config.projection_kind == "net_worth"
    assert config.contribution_source_reference == "operator-confirmed-personal-plan"
    assert config.contribution_observed_at.replace(tzinfo=timezone.utc) == observed


def test_divergent_existing_configuration_fails_closed(db):
    session, user, goal = db
    apply_configuration(session, user_sub=user.local_user_sub, monthly_contribution="500.00", goal_id=goal.id)
    with pytest.raises(ProjectionConfigurationError, match="projection_configuration_conflict"):
        plan_configuration(session, user_sub=user.local_user_sub, monthly_contribution="500.01", goal_id=goal.id)


@pytest.mark.parametrize("value,reason", [
    ("500.001", "monthly_contribution_precision"),
    ("-1.00", "invalid_monthly_contribution"),
    ("NaN", "invalid_monthly_contribution"),
    ("Infinity", "invalid_monthly_contribution"),
])
def test_invalid_contribution_is_rejected_without_mutation(db, value, reason):
    session, user, goal = db
    with pytest.raises(ProjectionConfigurationError, match=reason):
        plan_configuration(session, user_sub=user.local_user_sub, monthly_contribution=value, goal_id=goal.id)
    assert session.scalar(select(GoalProjectionConfig)) is None


def test_ambiguous_or_cross_owner_goal_selection_fails_closed(db):
    session, user, goal = db
    session.add(Goal(user_id=user.id, name="Second Synthetic Goal", target_amount=2000.0, horizon_years=10, is_archived=False))
    session.commit()
    with pytest.raises(ProjectionConfigurationError, match="active_goal_ambiguity"):
        plan_configuration(session, user_sub=user.local_user_sub, monthly_contribution="500.00", goal_id=goal.id)


def test_inactive_or_missing_operator_user_fails_closed(db):
    session, user, goal = db
    user.is_active = False
    session.commit()
    with pytest.raises(ProjectionConfigurationError, match="operator_user_unavailable"):
        plan_configuration(session, user_sub=user.local_user_sub, monthly_contribution="500.00", goal_id=goal.id)
    with pytest.raises(ProjectionConfigurationError, match="operator_user_unavailable"):
        plan_configuration(session, user_sub="other-user", monthly_contribution="500.00", goal_id=goal.id)
