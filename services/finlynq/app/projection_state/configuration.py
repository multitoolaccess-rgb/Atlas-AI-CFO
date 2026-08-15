"""Bounded operator path for explicit goal projection configuration.

This module is intentionally server/local-operator only.  It is not a browser
request model and never derives financial authority from client state.  The
existing ``GoalProjectionConfig`` row is immutable in its meaning: a divergent
existing configuration is refused rather than silently replaced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Goal, GoalProjectionConfig, User
from app.projection_state.currency import CurrencyEvidenceError, validate_stable_reference

PROJECTION_KIND = "net_worth"
CURRENCY_CODE = "USD"
SOURCE_REFERENCE = "operator-confirmed-personal-plan"
MONEY_QUANTUM = Decimal("0.01")
MAX_CONTRIBUTION = Decimal("1E+24")


class ProjectionConfigurationError(ValueError):
    """Stable, sanitized operator configuration failure."""


@dataclass(frozen=True)
class ProjectionConfigurationRequest:
    monthly_contribution: Decimal
    observed_at: datetime
    source_reference: str = SOURCE_REFERENCE
    projection_kind: str = PROJECTION_KIND
    currency_code: str = CURRENCY_CODE


def canonical_monthly_contribution(value: str | Decimal) -> Decimal:
    """Validate a non-negative, exactly-cent Decimal without float conversion."""
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProjectionConfigurationError("invalid_monthly_contribution") from exc
    if not parsed.is_finite() or parsed < 0 or parsed > MAX_CONTRIBUTION:
        raise ProjectionConfigurationError("invalid_monthly_contribution")
    if parsed != parsed.quantize(MONEY_QUANTUM):
        raise ProjectionConfigurationError("monthly_contribution_precision")
    return parsed.quantize(MONEY_QUANTUM)


def build_request(monthly_contribution: str | Decimal, *, observed_at: datetime | None = None) -> ProjectionConfigurationRequest:
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ProjectionConfigurationError("invalid_observed_at")
    try:
        validate_stable_reference(SOURCE_REFERENCE)
    except CurrencyEvidenceError as exc:
        raise ProjectionConfigurationError("invalid_source_reference") from exc
    return ProjectionConfigurationRequest(
        monthly_contribution=canonical_monthly_contribution(monthly_contribution),
        observed_at=observed.astimezone(timezone.utc),
    )


def _resolve_user(db: Session, user_sub: str) -> User:
    user = db.scalar(select(User).where(User.local_user_sub == user_sub, User.is_active.is_(True)))
    if user is None:
        raise ProjectionConfigurationError("operator_user_unavailable")
    return user


def _resolve_goal(db: Session, *, user_id: int, goal_id: int | None) -> Goal:
    goals = list(
        db.scalars(
            select(Goal)
            .where(Goal.user_id == user_id, Goal.is_archived.is_(False))
            .order_by(Goal.id.asc())
        )
    )
    if len(goals) != 1:
        raise ProjectionConfigurationError("active_goal_ambiguity")
    goal = goals[0]
    if goal_id is not None and goal.id != int(goal_id):
        raise ProjectionConfigurationError("goal_selection_mismatch")
    return goal


def _same_configuration(config: GoalProjectionConfig, request: ProjectionConfigurationRequest) -> bool:
    return (
        config.projection_kind == request.projection_kind
        and config.currency_code == request.currency_code
        and Decimal(str(config.monthly_contribution)) == request.monthly_contribution
        and config.contribution_source_reference == request.source_reference
    )


def plan_configuration(
    db: Session,
    *,
    user_sub: str,
    monthly_contribution: str | Decimal,
    goal_id: int | None = None,
    observed_at: datetime | None = None,
) -> tuple[User, Goal, ProjectionConfigurationRequest, GoalProjectionConfig | None]:
    """Resolve exactly one owned active goal and reject divergent state."""
    user = _resolve_user(db, user_sub)
    goal = _resolve_goal(db, user_id=int(user.id), goal_id=goal_id)
    request = build_request(monthly_contribution, observed_at=observed_at)
    config = db.scalar(
        select(GoalProjectionConfig).where(
            GoalProjectionConfig.user_id == user.id,
            GoalProjectionConfig.goal_id == goal.id,
        )
    )
    if config is not None and not _same_configuration(config, request):
        raise ProjectionConfigurationError("projection_configuration_conflict")
    return user, goal, request, config


def apply_configuration(
    db: Session,
    *,
    user_sub: str,
    monthly_contribution: str | Decimal,
    goal_id: int | None = None,
    observed_at: datetime | None = None,
) -> dict[str, str]:
    """Append the one allowed configuration row or return an idempotent replay."""
    _, goal, request, config = plan_configuration(
        db,
        user_sub=user_sub,
        monthly_contribution=monthly_contribution,
        goal_id=goal_id,
        observed_at=observed_at,
    )
    if config is not None:
        return {"status": "idempotent_replay", "projection": "ready"}
    config = GoalProjectionConfig(
        user_id=goal.user_id,
        goal_id=goal.id,
        projection_kind=request.projection_kind,
        currency_code=request.currency_code,
        monthly_contribution=request.monthly_contribution,
        contribution_source_reference=request.source_reference,
        contribution_observed_at=request.observed_at,
    )
    db.add(config)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _, _, _, winner = plan_configuration(
            db,
            user_sub=user_sub,
            monthly_contribution=monthly_contribution,
            goal_id=goal_id,
            observed_at=observed_at,
        )
        if winner is not None:
            return {"status": "idempotent_replay", "projection": "ready"}
        raise ProjectionConfigurationError("projection_configuration_conflict") from exc
    return {"status": "recorded", "projection": "ready"}
