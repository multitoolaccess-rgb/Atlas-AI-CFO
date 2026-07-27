"""Phase 4+5 — Recommendation approval workflow endpoints.

Provides CRUD + action endpoints for the approval queue:
- GET  /api/recommendations/           — list (pending first)
- POST /api/recommendations/           — create a new recommendation
- POST /api/recommendations/{id}/action — approve / deny / dismiss
- GET  /api/recommendations/stats      — summary counts
- POST /api/recommendations/generate   — Phase 5 AI Copilot smart alerts
- seed_default_recommendations()       — idempotent startup seed
- generate_smart_recommendations()     — Phase 5 auto-generation
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import RecommendationLog, User
from app.routes.shared import get_or_create_local_user

LOG = logging.getLogger("uvicorn.error")
from app.schemas import (
    RecommendationActionRequest,
    RecommendationLogCreate,
    RecommendationLogListResponse,
    RecommendationLogResponse,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/", response_model=RecommendationLogListResponse)
async def list_recommendations(
    status: str | None = Query(default=None, description="Filter by status: pending, approved, denied, dismissed"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> RecommendationLogListResponse:
    """List recommendations for the current user, newest first.

    When ``status`` is provided, filters to that status. Otherwise
    returns all statuses with pending items sorted first.
    """
    local_user = get_or_create_local_user(db, _current_user)

    query = db.query(RecommendationLog).filter(
        RecommendationLog.user_id == local_user.id,
    )

    if status:
        query = query.filter(RecommendationLog.status == status)

    total = query.count()
    pending_count = (
        db.query(func.count(RecommendationLog.id))
        .filter(
            RecommendationLog.user_id == local_user.id,
            RecommendationLog.status == "pending",
        )
        .scalar()
        or 0
    )

    # Pending first, then newest first within each status group
    items = (
        query.order_by(
            RecommendationLog.status != "pending",  # pending rows first
            RecommendationLog.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return RecommendationLogListResponse(
        items=[RecommendationLogResponse.model_validate(item) for item in items],
        total=total,
        pending_count=pending_count,
    )


@router.post("/", response_model=RecommendationLogResponse, status_code=201)
async def create_recommendation(
    body: RecommendationLogCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> RecommendationLogResponse:
    """Create a new recommendation in ``pending`` status."""
    local_user = get_or_create_local_user(db, _current_user)

    rec = RecommendationLog(
        user_id=local_user.id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        category=body.category,
        impact=body.impact,
        metadata_json=body.metadata_json,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return RecommendationLogResponse.model_validate(rec)


@router.post("/{rec_id}/action", response_model=RecommendationLogResponse)
async def take_action(
    rec_id: int,
    body: RecommendationActionRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> RecommendationLogResponse:
    """Transition a recommendation from ``pending`` to the target status.

    Actions: approve, deny, dismiss. Idempotent — if the recommendation
    is already in the target status, returns it unchanged.
    """
    local_user = get_or_create_local_user(db, _current_user)

    rec = (
        db.query(RecommendationLog)
        .filter(
            RecommendationLog.id == rec_id,
            RecommendationLog.user_id == local_user.id,
        )
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    if rec.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Recommendation is already {rec.status}; only pending recommendations can be acted on.",
        )

    rec.status = body.action if body.action != "dismiss" else "dismissed"
    rec.resolved_at = datetime.now(timezone.utc)
    rec.resolved_by = "user"
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return RecommendationLogResponse.model_validate(rec)


@router.get("/stats")
async def get_recommendation_stats(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> dict:
    """Summary counts by status for the current user."""
    local_user = get_or_create_local_user(db, _current_user)

    rows = (
        db.query(RecommendationLog.status, func.count(RecommendationLog.id))
        .filter(RecommendationLog.user_id == local_user.id)
        .group_by(RecommendationLog.status)
        .all()
    )
    stats = {status: count for status, count in rows}
    return {
        "total": sum(stats.values()),
        "pending": stats.get("pending", 0),
        "approved": stats.get("approved", 0),
        "denied": stats.get("denied", 0),
        "dismissed": stats.get("dismissed", 0),
    }


# ----------------------------------------------------------------------
# Phase 5 — AI Copilot: smart recommendations from finance data
# ----------------------------------------------------------------------

def generate_smart_recommendations(db: Session, user_id: int) -> int:
    """Auto-generate recommendations from anomaly, bill, and trend data.

    Calls the existing finance_query tools and converts their output into
    RecommendationLog entries so the ApprovalQueue UI shows actionable
    alerts derived from the user's real financial data.

    Deduplication: skips insertion when a pending recommendation with the
    same title already exists for this user. Resolved (approved/denied/
    dismissed) recommendations with the same title are NOT duplicated —
    the user already acted on that signal.

    Each auto-generated row carries ``metadata_json`` with
    ``{"source": "auto-generated"}`` so the startup hook can distinguish
    them from seed/demo data and avoid re-generating on every restart.

    Returns the number of NEW recommendations inserted.
    """
    from app.services.finance_query import (
        compute_investable_surplus,
        compute_savings_rate,
        detect_anomalies,
        get_trends,
        predict_upcoming_bills,
    )

    now = datetime.now(timezone.utc)
    now_date = now.date()

    # Fetch ALL existing titles for this user (any status) so we never
    # duplicate a recommendation the user already saw.
    existing_titles = {
        row[0]
        for row in db.query(RecommendationLog.title)
        .filter(RecommendationLog.user_id == user_id)
        .all()
    }

    candidates: list[RecommendationLog] = []

    # --- 1. Anomaly alerts (high priority, spending) -----------------
    try:
        anomalies_res = detect_anomalies(db, {"limit": 5}, user_id)
        for anomaly in anomalies_res.get("anomalies", []):
            merchant = anomaly["merchant"]
            title = f"Unusual spending at {merchant}"
            if title in existing_titles:
                continue
            candidates.append(RecommendationLog(
                user_id=user_id,
                title=title,
                description=(
                    f"A transaction of ${anomaly['amount']:.2f} at {merchant} "
                    f"is {anomaly['multiplier']:.1f}× your 90-day median of "
                    f"${anomaly['median']:.2f}. Review this charge to confirm "
                    f"it's legitimate."
                ),
                priority="high",
                category="spending",
                impact=f"${anomaly['amount']:.2f} flagged charge",
                metadata_json=json.dumps({
                    "source": "auto-generated",
                    "signal": "anomaly",
                    "transaction_id": anomaly["transaction_id"],
                    "merchant": merchant,
                }),
            ))
            existing_titles.add(title)
    except Exception as exc:
        LOG.warning("Smart recs — anomaly scan failed: %s", exc)

    # --- 2. Upcoming bills due within 7 days (medium, spending) ------
    try:
        bills_res = predict_upcoming_bills(db, {}, user_id)
        for bill in bills_res.get("bills", []):
            pred_str = bill.get("predicted_next_date")
            if not pred_str:
                continue
            pred_date = datetime.fromisoformat(pred_str).date()
            days_until = (pred_date - now_date).days
            if days_until < 0 or days_until > 7:
                continue
            merchant = bill["merchant"]
            title = f"Upcoming bill: {merchant}"
            if title in existing_titles:
                continue
            when = "tomorrow" if days_until <= 1 else f"in {days_until} days"
            candidates.append(RecommendationLog(
                user_id=user_id,
                title=title,
                description=(
                    f"A recurring charge of ${bill['median_amount']:.2f} from "
                    f"{merchant} is predicted {when} ({pred_str}). "
                    f"Based on {bill['hit_count']} prior payments with "
                    f"{bill['confidence']:.0%} confidence."
                ),
                priority="medium",
                category="spending",
                impact=f"${bill['median_amount']:.2f} due {when}",
                metadata_json=json.dumps({
                    "source": "auto-generated",
                    "signal": "upcoming_bill",
                    "merchant": merchant,
                }),
            ))
            existing_titles.add(title)
    except Exception as exc:
        LOG.warning("Smart recs — bill prediction failed: %s", exc)

    # --- 3. Low savings rate (high, savings) -------------------------
    try:
        sr = compute_savings_rate(db, {}, user_id)
        rate = sr.get("savings_rate", 0)
        if rate < 10.0:
            title = "Low Savings Rate Alert"
            if title not in existing_titles:
                income = sr.get("income", 0)
                expenses = sr.get("expenses", 0)
                gap = income * 0.10 - (income - expenses) if income > 0 else 0
                candidates.append(RecommendationLog(
                    user_id=user_id,
                    title=title,
                    description=(
                        f"Your savings rate is {rate:.1f}% this month "
                        f"(income: ${income:,.2f}, expenses: ${expenses:,.2f}). "
                        f"A 10% target would require saving an additional "
                        f"${max(0, gap):,.2f}/month."
                    ),
                    priority="high",
                    category="savings",
                    impact=f"{rate:.1f}% savings rate (target: 10%+)",
                    metadata_json=json.dumps({
                        "source": "auto-generated",
                        "signal": "low_savings_rate",
                    }),
                ))
                existing_titles.add(title)
    except Exception as exc:
        LOG.warning("Smart recs — savings rate check failed: %s", exc)

    # --- 4. Rising expense trend (medium, spending) ------------------
    try:
        trends = get_trends(db, {"months": 3}, user_id)
        if trends.get("direction") == "increasing":
            trend_data = trends.get("trend", [])
            if len(trend_data) >= 2:
                first_exp = trend_data[0].get("expenses", 0)
                last_exp = trend_data[-1].get("expenses", 0)
                if first_exp > 0:
                    pct = ((last_exp - first_exp) / first_exp) * 100
                else:
                    pct = 0
                title = "Rising Expense Trend Detected"
                if title not in existing_titles:
                    candidates.append(RecommendationLog(
                        user_id=user_id,
                        title=title,
                        description=(
                            f"Your monthly expenses have increased {pct:.0f}% "
                            f"over the last {len(trend_data)} months "
                            f"(${first_exp:,.0f} → ${last_exp:,.0f}). "
                            f"Review your top spending categories for "
                            f"potential cuts."
                        ),
                        priority="medium",
                        category="spending",
                        impact=f"{pct:.0f}% increase in monthly expenses",
                        metadata_json=json.dumps({
                            "source": "auto-generated",
                            "signal": "rising_trend",
                        }),
                    ))
                    existing_titles.add(title)
    except Exception as exc:
        LOG.warning("Smart recs — trend analysis failed: %s", exc)

    # --- 5. Investable surplus + active goals (low, goal) ------------
    try:
        surplus = compute_investable_surplus(db, {}, user_id)
        avail = surplus.get("investable_surplus", 0)
        if avail > 0 and surplus.get("has_goals"):
            title = "Surplus Available for Goals"
            if title not in existing_titles:
                goal_count = surplus.get("goal_count", 0)
                candidates.append(RecommendationLog(
                    user_id=user_id,
                    title=title,
                    description=(
                        f"You have ${avail:,.2f} of investable surplus this "
                        f"month after expenses and goal contributions. "
                        f"Consider allocating it across your {goal_count} "
                        f"active goal(s) to accelerate progress."
                    ),
                    priority="low",
                    category="goal",
                    impact=f"${avail:,.2f} available to allocate",
                    metadata_json=json.dumps({
                        "source": "auto-generated",
                        "signal": "investable_surplus",
                    }),
                ))
                existing_titles.add(title)
    except Exception as exc:
        LOG.warning("Smart recs — surplus calculation failed: %s", exc)

    # --- 6. Policy-based evaluations (Phase 2) -----------------------
    try:
        from app.routes.evaluate import _load_policy, _evaluate_portfolio_drift, _evaluate_idle_cash, _evaluate_goal_progress
        policy = _load_policy()
        for rule_fn in [_evaluate_portfolio_drift, _evaluate_idle_cash, _evaluate_goal_progress]:
            result = rule_fn(db, user_id, policy)
            if result and result.status in ("warning", "critical"):
                title = f"Policy Alert: {result.rule.replace('_', ' ').title()}"
                if title not in existing_titles:
                    candidates.append(RecommendationLog(
                        user_id=user_id,
                        title=title,
                        description=result.message,
                        priority="high" if result.status == "critical" else "medium",
                        category="general",
                        impact=f"Status: {result.status}",
                        metadata_json=json.dumps({
                            "source": "auto-generated",
                            "signal": "policy_evaluation",
                            "rule": result.rule,
                            "status": result.status,
                        }),
                    ))
                    existing_titles.add(title)
    except Exception as exc:
        LOG.warning("Smart recs — policy evaluation failed: %s", exc)

    # --- Commit ------------------------------------------------------
    inserted = 0
    for rec in candidates:
        db.add(rec)
        inserted += 1
    if inserted > 0:
        db.commit()
    return inserted


@router.post("/generate")
async def api_generate_smart_recommendations(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> dict:
    """Trigger AI Copilot smart alert generation from finance data.

    Calls anomaly detection, bill prediction, savings rate analysis,
    trend analysis, and investable surplus computation to produce
    actionable recommendations in the approval queue.

    Idempotent — skips recommendations the user already has (any status).
    """
    local_user = get_or_create_local_user(db, _current_user)
    count = generate_smart_recommendations(db, local_user.id)
    return {"inserted": count}


# ----------------------------------------------------------------------
# Phase 4 — Startup seed for demo recommendations
# ----------------------------------------------------------------------

# Realistic sample recommendations covering all priorities, categories,
# and statuses so the ApprovalQueue renders meaningful data on first load.
# The seed is idempotent: it skips insertion when the user already has
# recommendations (any status), so repeated uvicorn reloads stay clean.
#
# One resolved item is included to demonstrate the "Show all" filter
# and the resolved-row status badge in the UI.
_DEFAULT_RECOMMENDATIONS: list[dict[str, str | None]] = [
    {
        "title": "Boost Your Savings Rate",
        "description": (
            "Your savings rate dropped below 10% this month. "
            "Consider setting up an automatic transfer of $200/month "
            "to your high-yield savings account to reach your 20% target."
        ),
        "priority": "high",
        "category": "savings",
        "impact": "Could save $2,400/year",
    },
    {
        "title": "Spending Nearing Income",
        "description": (
            "Your expenses are over 90% of your income this month. "
            "Discretionary spending on dining and entertainment spiked "
            "35% compared to last month."
        ),
        "priority": "high",
        "category": "spending",
        "impact": "Risk of negative cash flow",
    },
    {
        "title": "Duplicate Subscription Detected",
        "description": (
            "Two recurring charges from streaming services appear on "
            "the same day each month ($14.99 and $15.49). Review whether "
            "both are intentional or if one can be cancelled."
        ),
        "priority": "medium",
        "category": "spending",
        "impact": "Save ~$180/year",
    },
    {
        "title": "Rebalance Portfolio Allocation",
        "description": (
            "Your equity allocation is 82%, above your target of 70%. "
            "Consider moving $5,000 from your brokerage to bonds or a "
            "money-market fund to restore your risk tolerance."
        ),
        "priority": "medium",
        "category": "general",
        "impact": "Reduce portfolio volatility",
    },
    {
        "title": "Emergency Fund Goal Almost There!",
        "description": (
            "You’re 85% towards your 6-month emergency fund target. "
            "Two more months of current contributions will fully fund it."
        ),
        "priority": "low",
        "category": "goal",
        "impact": "$1,200 remaining",
    },
]

# One pre-resolved item so the "Show all" view demonstrates the
# resolved-row status badge without the user having to act first.
_RESOLVED_RECOMMENDATION: dict[str, str | None] = {
    "title": "Review Annual Insurance Premiums",
    "description": (
        "Your auto and home insurance premiums increased 12% this year. "
        "Shopping around for competing quotes could save $300–500 annually."
    ),
    "priority": "low",
    "category": "spending",
    "impact": "Potential $400/year savings",
    "status": "approved",
    "resolved_by": "user",
}


def seed_default_recommendations(db: Session) -> int:
    """Idempotently insert demo recommendations for the local user.

    Returns the number of NEW recommendations inserted (0 on a re-run
    against a DB that already has recommendations for the first user).

    The seed only fires when the ``recommendation_logs`` table is empty
    for user_id=1 (the default local user). This keeps the demo data
    out of the way once the user starts creating their own
    recommendations via the API.

    Called from :func:`app.main._seed_default_recommendations`
    (registered as a FastAPI startup hook AFTER
    ``_seed_default_merchant_rules`` so the tables exist).
    """
    # Only seed if the table is empty for user_id=1.
    existing = (
        db.query(func.count(RecommendationLog.id))
        .filter(RecommendationLog.user_id == 1)
        .scalar()
        or 0
    )
    if existing > 0:
        return 0

    # Ensure the users table has at least one row (user_id=1).
    # If the local user doesn't exist yet, skip seeding — the
    # startup hook ordering ensures users are created first, but
    # guard defensively.
    user_exists = db.query(User).filter(User.id == 1).first()
    if not user_exists:
        return 0

    inserted = 0
    now = datetime.now(timezone.utc)

    for item in _DEFAULT_RECOMMENDATIONS:
        rec = RecommendationLog(
            user_id=1,
            title=item["title"],
            description=item.get("description", ""),
            priority=item.get("priority", "medium"),
            status="pending",
            category=item.get("category", "general"),
            impact=item.get("impact"),
        )
        db.add(rec)
        inserted += 1

    # Add one pre-resolved item for the "Show all" demo.
    resolved = _RESOLVED_RECOMMENDATION
    rec = RecommendationLog(
        user_id=1,
        title=resolved["title"],
        description=resolved.get("description", ""),
        priority=resolved.get("priority", "medium"),
        status=resolved.get("status", "approved"),
        category=resolved.get("category", "general"),
        impact=resolved.get("impact"),
        resolved_at=now,
        resolved_by=resolved.get("resolved_by", "user"),
    )
    db.add(rec)
    inserted += 1

    db.commit()
    return inserted
