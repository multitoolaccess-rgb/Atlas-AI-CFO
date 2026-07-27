"""Phase 2 — Policy-based rule evaluation endpoint.

Reads ``policies/default-policy.yaml`` and evaluates the user's current
financial state against it. Returns a list of evaluation results, each
with a rule name, status (ok/warning/critical), message, and optional
numeric details.

Evaluation rules:
1. **Portfolio drift**: compare actual account-type allocation vs
   policy targetAllocation. Warns when any category drifts beyond
   rebalanceThresholdPct.
2. **Idle cash**: flags when cash percentage exceeds
   idleCashThresholdPct.
3. **Goal progress**: checks whether current net worth is on track
   for the policy goal's targetValue by targetDate.

The endpoint is a pure GET — it does NOT create RecommendationLog
entries. Integration with the recommendation system happens in
``generate_smart_recommendations()`` which calls the evaluation
internally.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends
from sqlalchemy import case as sa_case, func
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Account, Goal
from app.routes.shared import get_or_create_local_user
from app.schemas import EvaluateResponse, EvaluationItem

LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["evaluate"])

# Path to the policy file, resolved relative to the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_POLICY_PATH = _PROJECT_ROOT / "policies" / "default-policy.yaml"

# Account-type → allocation category mapping.
# Excludes credit/liability accounts from the portfolio denominator.
_ACCOUNT_TYPE_TO_CATEGORY: dict[str, str] = {
    "checking": "cash",
    "savings": "cash",
    "money_market": "cash",
    "cd": "cash",
    "brokerage": "us_equity",
    "taxable_brokerage": "us_equity",
    "401k": "us_equity",
    "403b": "us_equity",
    "ira": "us_equity",
    "roth_ira": "us_equity",
    "sep_ira": "us_equity",
    "hsa": "us_equity",
    "529": "us_equity",
    "pension": "bond",
    "annuity": "bond",
    "other_investment": "us_equity",
}

# Account types that are liabilities — excluded from portfolio allocation.
_LIABILITY_TYPES = frozenset({"credit_card", "loan", "mortgage"})


def _load_policy(path: Path | None = None) -> dict[str, Any]:
    """Load and parse the policy YAML file."""
    path = path or _POLICY_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, OSError) as exc:
        LOG.warning("Could not read policy file %s: %s", path, exc)
        return {}


def _evaluate_portfolio_drift(
    db: Session,
    user_id: int,
    policy: dict[str, Any],
) -> EvaluationItem | None:
    """Evaluate portfolio drift against target allocation.

    Maps account_type to allocation categories, computes current
    percentages, and flags categories that drift beyond the threshold.
    """
    target = policy.get("targetAllocation", {})
    threshold = policy.get("rebalanceThresholdPct", 5)

    if not target:
        return None

    # Sum balances by allocation category, excluding liabilities.
    rows = (
        db.query(
            Account.account_type,
            func.coalesce(
                func.sum(
                    sa_case(
                        (
                            Account.account_type.in_(list(_LIABILITY_TYPES)),
                            -Account.current_balance,
                        ),
                        else_=Account.current_balance,
                    )
                ),
                0.0,
            ).label("balance"),
        )
        .filter(
            Account.user_id == user_id,
            Account.is_active.is_(True),
        )
        .group_by(Account.account_type)
        .all()
    )

    # Aggregate by allocation category.
    category_totals: dict[str, float] = {}
    for row in rows:
        acct_type = (row.account_type or "checking").lower()
        if acct_type in _LIABILITY_TYPES:
            continue
        category = _ACCOUNT_TYPE_TO_CATEGORY.get(acct_type, "us_equity")
        category_totals[category] = category_totals.get(category, 0.0) + float(row.balance)

    total_portfolio = sum(category_totals.values())
    if total_portfolio <= 0:
        return EvaluationItem(
            rule="portfolio_drift",
            status="ok",
            message="No portfolio assets found. Add accounts to enable drift evaluation.",
            details={"total_portfolio": 0.0},
        )

    # Compute actual percentages and check drift.
    drifts: list[dict[str, Any]] = []
    for cat, target_pct in target.items():
        actual_pct = category_totals.get(cat, 0.0) / total_portfolio
        drift = abs(actual_pct - target_pct) * 100
        if drift > threshold:
            drifts.append({
                "category": cat,
                "actual_pct": round(actual_pct * 100, 1),
                "target_pct": round(target_pct * 100, 1),
                "drift_pct": round(drift, 1),
            })

    if not drifts:
        return EvaluationItem(
            rule="portfolio_drift",
            status="ok",
            message="Portfolio allocation is within target thresholds.",
            details={
                "total_portfolio": round(total_portfolio, 2),
                "threshold_pct": threshold,
            },
        )

    # Find the worst drift.
    worst = max(drifts, key=lambda d: d["drift_pct"])
    status = "critical" if worst["drift_pct"] > threshold * 2 else "warning"

    return EvaluationItem(
        rule="portfolio_drift",
        status=status,
        message=(
            f"{worst['category']} is at {worst['actual_pct']}% "
            f"(target: {worst['target_pct']}%, threshold: {threshold}%). "
            f"Rebalancing recommended."
        ),
        details={
            "total_portfolio": round(total_portfolio, 2),
            "threshold_pct": threshold,
            "drifts": drifts,
        },
    )


def _evaluate_idle_cash(
    db: Session,
    user_id: int,
    policy: dict[str, Any],
) -> EvaluationItem | None:
    """Evaluate whether cash allocation exceeds the idle cash threshold."""
    threshold = policy.get("idleCashThresholdPct", 0.05)

    # Sum cash accounts.
    cash_balance = (
        db.query(
            func.coalesce(func.sum(Account.current_balance), 0.0)
        )
        .filter(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            Account.account_type.in_(["checking", "savings", "money_market", "cd"]),
        )
        .scalar()
    ) or 0.0

    # Sum total portfolio (excluding liabilities).
    total_balance = (
        db.query(
            func.coalesce(
                func.sum(
                    sa_case(
                        (
                            Account.account_type.in_(list(_LIABILITY_TYPES)),
                            -Account.current_balance,
                        ),
                        else_=Account.current_balance,
                    )
                ),
                0.0,
            )
        )
        .filter(
            Account.user_id == user_id,
            Account.is_active.is_(True),
        )
        .scalar()
    ) or 0.0

    if total_balance <= 0:
        return EvaluationItem(
            rule="idle_cash",
            status="ok",
            message="No portfolio assets found.",
            details={"cash_balance": 0.0, "total_balance": 0.0},
        )

    cash_pct = cash_balance / total_balance
    threshold_pct = threshold * 100

    if cash_pct > threshold:
        status = "critical" if cash_pct > threshold * 2 else "warning"
        return EvaluationItem(
            rule="idle_cash",
            status=status,
            message=(
                f"Cash is at {cash_pct * 100:.1f}% of portfolio "
                f"(${cash_balance:,.2f} of ${total_balance:,.2f}). "
                f"This exceeds the {threshold_pct}% maximum idle cash threshold."
            ),
            details={
                "cash_balance": round(cash_balance, 2),
                "total_balance": round(total_balance, 2),
                "cash_pct": round(cash_pct * 100, 1),
                "threshold_pct": threshold_pct,
            },
        )

    return EvaluationItem(
        rule="idle_cash",
        status="ok",
        message=(
            f"Cash allocation is at {cash_pct * 100:.1f}%, "
            f"within the {threshold_pct}% threshold."
        ),
        details={
            "cash_balance": round(cash_balance, 2),
            "total_balance": round(total_balance, 2),
            "cash_pct": round(cash_pct * 100, 1),
            "threshold_pct": threshold_pct,
        },
    )


def _evaluate_goal_progress(
    db: Session,
    user_id: int,
    policy: dict[str, Any],
) -> EvaluationItem | None:
    """Evaluate progress toward the policy goal.

    Checks whether current net worth is on track for the goal's
    targetValue by targetDate, using a linear interpolation of
    expected progress.
    """
    goal_config = policy.get("goal", {})
    target_value = goal_config.get("targetValue")
    target_date_str = goal_config.get("targetDate")

    if not target_value or not target_date_str:
        return None

    # PyYAML safe_load auto-parses ISO dates as datetime.date objects,
    # so accept both str and date to avoid strptime() TypeError.
    try:
        if isinstance(target_date_str, date):
            target_date = datetime(target_date_str.year, target_date_str.month, target_date_str.day, tzinfo=timezone.utc)
        else:
            target_date = datetime.strptime(str(target_date_str), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        LOG.warning("Invalid goal targetDate format: %s", target_date_str)
        return None

    # Get current net worth (assets minus liabilities).
    net_worth = (
        db.query(
            func.coalesce(
                func.sum(
                    sa_case(
                        (
                            Account.account_type.in_(list(_LIABILITY_TYPES)),
                            -Account.current_balance,
                        ),
                        else_=Account.current_balance,
                    )
                ),
                0.0,
            )
        )
        .filter(
            Account.user_id == user_id,
            Account.is_active.is_(True),
        )
        .scalar()
    ) or 0.0

    # Compute expected progress using linear interpolation.
    # Assume the goal started at year 2020 (or user's first account creation).
    # For simplicity, use a fixed start date.
    now = datetime.now(timezone.utc)
    start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)

    total_days = (target_date - start_date).days
    elapsed_days = (now - start_date).days

    if total_days <= 0:
        return EvaluationItem(
            rule="goal_progress",
            status="ok",
            message="Goal target date is in the past.",
            details={"target_value": target_value, "net_worth": round(net_worth, 2)},
        )

    progress_ratio = min(1.0, max(0.0, elapsed_days / total_days))
    expected_value = target_value * progress_ratio
    actual_pct = (net_worth / target_value) * 100 if target_value > 0 else 0
    expected_pct = progress_ratio * 100

    # Determine status based on how far behind/ahead.
    gap_pct = actual_pct - expected_pct

    if gap_pct >= -10:
        status = "ok"
        message = (
            f"On track for ${target_value:,.0f} goal by {target_date_str}. "
            f"Current: ${net_worth:,.0f} ({actual_pct:.1f}% of target, "
            f"expected: {expected_pct:.1f}%)."
        )
    elif gap_pct >= -25:
        status = "warning"
        message = (
            f"Behind on ${target_value:,.0f} goal by {target_date_str}. "
            f"Current: ${net_worth:,.0f} ({actual_pct:.1f}% of target, "
            f"expected: {expected_pct:.1f}%). Consider increasing contributions."
        )
    else:
        status = "critical"
        message = (
            f"Significantly behind on ${target_value:,.0f} goal by {target_date_str}. "
            f"Current: ${net_worth:,.0f} ({actual_pct:.1f}% of target, "
            f"expected: {expected_pct:.1f}%). Review savings strategy."
        )

    return EvaluationItem(
        rule="goal_progress",
        status=status,
        message=message,
        details={
            "target_value": target_value,
            "target_date": target_date_str,
            "net_worth": round(net_worth, 2),
            "actual_pct": round(actual_pct, 1),
            "expected_pct": round(expected_pct, 1),
            "gap_pct": round(gap_pct, 1),
        },
    )


@router.get("/evaluate", response_model=EvaluateResponse)
async def evaluate(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> EvaluateResponse:
    """Evaluate the user's financial state against the policy file.

    Reads ``policies/default-policy.yaml`` and runs three evaluation
    rules:
    1. Portfolio drift — are account-type allocations within threshold?
    2. Idle cash — is cash percentage below the maximum?
    3. Goal progress — is net worth on track for the target?

    Returns a list of evaluation results, each with a rule name,
    status (ok/warning/critical), message, and optional details.
    """
    local_user = get_or_create_local_user(db, _current_user)
    policy = _load_policy()

    evaluations: list[EvaluationItem] = []

    # Rule 1: Portfolio drift
    drift_result = _evaluate_portfolio_drift(db, local_user.id, policy)
    if drift_result:
        evaluations.append(drift_result)

    # Rule 2: Idle cash
    cash_result = _evaluate_idle_cash(db, local_user.id, policy)
    if cash_result:
        evaluations.append(cash_result)

    # Rule 3: Goal progress
    goal_result = _evaluate_goal_progress(db, local_user.id, policy)
    if goal_result:
        evaluations.append(goal_result)

    return EvaluateResponse(
        evaluations=evaluations,
        policy_path=str(_POLICY_PATH),
        evaluated_at=datetime.now(timezone.utc),
    )
