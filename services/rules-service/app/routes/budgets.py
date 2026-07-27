"""Budget CRUD + status endpoint.

Atlas Phase 1 — provides planned-budget management and budget-vs-actual
comparison for the Budgeting page.

Endpoints:
- GET    /api/budgets/              — list all budgets (optionally by period)
- POST   /api/budgets/              — create a budget for category + period
- PUT    /api/budgets/{id}          — update budget amount
- DELETE /api/budgets/{id}          — delete a budget
- GET    /api/budgets/status        — budget vs actual for a period
"""
import calendar
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Budget, Category, Transaction
from app.routes.shared import get_or_create_local_user
from app.schemas import BudgetCreate, BudgetResponse, BudgetUpdate

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


@router.get("/", response_model=list[BudgetResponse])
async def list_budgets(
    period: Optional[str] = Query(default=None, description="YYYY-MM"),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """List all budgets for the local user, optionally filtered by period."""
    user = get_or_create_local_user(db, _current_user)
    q = db.query(Budget).filter(Budget.user_id == user.id)
    if period:
        q = q.filter(Budget.period == period)
    budgets = q.order_by(Budget.period.desc(), Budget.category_id).all()
    result = []
    for b in budgets:
        cat_name = None
        if b.category_id:
            cat = db.query(Category).filter(Category.id == b.category_id).first()
            cat_name = cat.name if cat else None
        result.append(
            BudgetResponse(
                id=b.id,
                user_id=b.user_id,
                category_id=b.category_id,
                category_name=cat_name,
                amount=b.amount,
                period=b.period,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
        )
    return result


@router.post("/", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create a budget for a category + period.

    Enforces at most one Global budget (category_id is None) per user
    and period so a second attempt returns a clear 409 Conflict.
    """
    user = get_or_create_local_user(db, _current_user)

    if payload.category_id is None:
        existing_global = (
            db.query(Budget)
            .filter(
                Budget.user_id == user.id,
                Budget.period == payload.period,
                Budget.category_id.is_(None),
            )
            .first()
        )
        if existing_global:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A Global budget already exists for {payload.period}. "
                "You can only have one Global budget per period.",
            )

    now = datetime.utcnow().isoformat()
    budget = Budget(
        user_id=user.id,
        category_id=payload.category_id,
        amount=payload.amount,
        period=payload.period,
        created_at=now,
        updated_at=now,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    cat_name = None
    if budget.category_id:
        cat = db.query(Category).filter(Category.id == budget.category_id).first()
        cat_name = cat.name if cat else None
    return BudgetResponse(
        id=budget.id,
        user_id=budget.user_id,
        category_id=budget.category_id,
        category_name=cat_name,
        amount=budget.amount,
        period=budget.period,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


@router.put("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Partial update of a budget amount."""
    user = get_or_create_local_user(db, _current_user)
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == user.id)
        .first()
    )
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    if payload.amount is not None:
        budget.amount = payload.amount
    budget.updated_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(budget)
    cat_name = None
    if budget.category_id:
        cat = db.query(Category).filter(Category.id == budget.category_id).first()
        cat_name = cat.name if cat else None
    return BudgetResponse(
        id=budget.id,
        user_id=budget.user_id,
        category_id=budget.category_id,
        category_name=cat_name,
        amount=budget.amount,
        period=budget.period,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Delete a budget."""
    user = get_or_create_local_user(db, _current_user)
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == user.id)
        .first()
    )
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()


def _parse_budget_period(period: str) -> tuple[int, int]:
    """Validate and parse a YYYY-MM budget period string."""
    if not period or not isinstance(period, str):
        raise HTTPException(status_code=400, detail="Period is required (YYYY-MM)")
    parts = period.split("-")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Period must be YYYY-MM")
    try:
        year, month = int(parts[0]), int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Period must be YYYY-MM")
    if not (1 <= year <= 9999 and 1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Period must be a valid YYYY-MM")
    return year, month


@router.get("/status")
async def get_budget_status(
    period: str = Query(..., description="YYYY-MM"),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Budget vs actual comparison for a given period.

    Compares planned budgets against aggregated actual spending
    using classify_cashflow for account-type-aware normalization.
    """
    from app.account_types import classify_cashflow

    user = get_or_create_local_user(db, _current_user)

    from sqlalchemy.orm import joinedload
    from app.models import Account

    year, month = _parse_budget_period(period)

    # Get budgets for this period with category eagerly loaded (avoids N+1)
    budgets = (
        db.query(Budget)
        .options(joinedload(Budget.category))
        .filter(Budget.user_id == user.id, Budget.period == period)
        .all()
    )

    # Parse period to date range
    last_day = calendar.monthrange(year, month)[1]
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month:02d}-{last_day:02d}"

    # Get actual spending per category for this period.
    # Join Account to get account_type for classify_cashflow.
    txns = (
        db.query(Transaction, Account.account_type)
        .join(Account, Transaction.account_id == Account.id, isouter=True)
        .filter(
            Account.user_id == user.id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
        )
        .all()
    )

    actual_by_cat: dict[int | None, float] = {}
    for txn, acct_type in txns:
        cr = classify_cashflow(
            txn.amount, acct_type or "", txn.description or ""
        )
        if cr.expense_effect > 0:
            cid = txn.category_id
            actual_by_cat[cid] = actual_by_cat.get(cid, 0.0) + cr.expense_effect

    # Total actual spending across all categories (used by Global budgets).
    total_expense_actual = sum(actual_by_cat.values())

    categories = []
    total_planned = 0.0
    total_actual = 0.0
    for b in budgets:
        cat = b.category
        if b.category_id is None:
            # Global budget: actual = all spending in the period.
            actual = total_expense_actual
        else:
            actual = actual_by_cat.get(b.category_id, 0.0)
        remaining = b.amount - actual
        pct = (actual / b.amount * 100) if b.amount > 0 else 0.0
        categories.append(
            {
                "category_id": b.category_id or 0,
                "category_name": cat.name if cat else "Global",
                "budget_group": cat.budget_group if cat else "other",
                "planned": b.amount,
                "actual": round(actual, 2),
                "remaining": round(remaining, 2),
                "percent_used": round(pct, 2),
            }
        )
        total_planned += b.amount
        total_actual += actual

    return {
        "period": period,
        "categories": categories,
        "totals": {
            "planned": total_planned,
            "actual": round(total_actual, 2),
            "remaining": round(total_planned - total_actual, 2),
            "percent_used": round(
                (total_actual / total_planned * 100) if total_planned > 0 else 0,
                2,
            ),
        },
    }
