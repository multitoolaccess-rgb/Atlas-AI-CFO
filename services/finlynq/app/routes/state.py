"""Finlynq /state/ + /state/summary endpoints.

Phase-F5 lifts ``/state/summary`` from a 501 stub to the real
aggregator. rules-service's ``/api/dashboard/summary`` is now a
thin httpx forwarder to this endpoint (Phase-F5 migration). The
aggregator queries the SAME shared database per Phase-F2 shared-DB
wiring. The cross-DB invariant test
``services/tests/test_state_aggregator_cross_db.py`` locks the
field set and sum semantics end-to-end.

``/state`` (the composite listing) STAYS a 501 stub — that is a
Phase-F6 deliverable per ``docs/master-plan.md`` end-state vision.
Only the summary path is in F5 scope; expanding to listings is a
follow-on.

Auth gating: F5 adds ``Depends(require_user)`` + ``Depends(get_db)``
on both endpoints so the contract test
``test_state_endpoint_contract.py::test_state_summary_auth_and_schema``
can assert 401 without JWT THEN 200 with the canonical shape with JWT.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth import require_user
from app.database import get_db
from app.models import Account, Goal, ImportBatch, Transaction
from app.routes.shared import get_or_create_local_user
from app.schemas import AccountSummary, GoalSummary, TransactionSummary

router = APIRouter(prefix="/state", tags=["state"])


# ---- /state (canonical composite) ----------------------------------------


class StateOut(BaseModel):
    """Composite read-side response — Phase F6 lands the listings.

    Phase-F5 ships the locked shape but ``/state`` continues to return
    501. The shape here is immutable per
    ``test_state_endpoint_contract.py::test_state_out_shape_is_locked``.
    """
    total_balance: float
    total_income_month: float
    total_expenses_month: float
    accounts_count: int
    transactions_count: int
    last_sync: Optional[datetime] = None
    import_batches_count: int
    last_import_at: Optional[datetime] = None
    user_goals: List[GoalSummary] = []
    accounts: List[AccountSummary] = []
    transactions: List[TransactionSummary] = []


@router.get("", response_model=StateOut)
async def get_state(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
    limit: int = 100,
) -> StateOut:
    """Phase F6 — composite state endpoint for the agent persona.

    Returns the full financial state: summary metrics + account listings
    + recent transactions + user goals. This is the ``finlynq_get_state``
    tool surface registered in ``agents/finance-copilot/TOOLS.md``.

    The summary fields mirror ``/state/summary`` exactly (same SQL,
    same rolling 60-day window). The ``accounts[]`` and
    ``transactions[]`` lists give the agent context for reasoning
    about the user's financial position.

    ``limit`` caps the transactions list (default 100, max 1000) so
    the agent's tool response stays within token budgets.
    """
    local_user = get_or_create_local_user(db, _current_user)

    # ── Summary fields (same logic as /state/summary) ─────────────
    total_balance = (
        db.query(func.coalesce(func.sum(Account.current_balance), 0.0))
        .filter(Account.user_id == local_user.id)
        .scalar()
    )

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=60)

    income_transactions = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .join(Account)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= window_start,
            Transaction.amount > 0,
        )
        .scalar()
    )
    expense_transactions = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .join(Account)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= window_start,
            Transaction.amount < 0,
        )
        .scalar()
    )

    accounts_count = (
        db.query(Account).filter(Account.user_id == local_user.id).count()
    )
    transactions_count = (
        db.query(Transaction)
        .join(Account)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= window_start,
        )
        .count()
    )

    last_sync = (
        db.query(func.max(Account.last_sync))
        .filter(Account.user_id == local_user.id)
        .scalar()
    )
    import_batches_count = (
        db.query(ImportBatch).filter(ImportBatch.user_id == local_user.id).count()
    )
    last_import_at = (
        db.query(func.max(ImportBatch.processed_at))
        .filter(ImportBatch.user_id == local_user.id)
        .scalar()
    )

    # ── Account listings ──────────────────────────────────────────
    account_rows = (
        db.query(Account)
        .filter(Account.user_id == local_user.id, Account.is_active.is_(True))
        .order_by(Account.account_name.asc())
        .all()
    )
    accounts = [
        AccountSummary.model_validate(row, from_attributes=True)
        for row in account_rows
    ]

    # ── Recent transactions ───────────────────────────────────────
    # joinedload avoids N+1: without it, accessing t.account and
    # t.category per row triggers a lazy-load query each time.
    safe_limit = max(1, min(limit, 1000))
    txn_rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.account), joinedload(Transaction.category))
        .join(Account)
        .filter(Account.user_id == local_user.id)
        .order_by(Transaction.transaction_date.desc())
        .limit(safe_limit)
        .all()
    )
    transactions = []
    for t in txn_rows:
        ts = TransactionSummary.model_validate(t, from_attributes=True)
        # Populate joinedload labels from relationships
        if t.account is not None:
            ts.account_name = t.account.account_name
            ts.account_type = t.account.account_type
        if t.category is not None:
            ts.category_name = t.category.name
        transactions.append(ts)

    # ── Goals ─────────────────────────────────────────────────────
    goals = _goal_summaries(db, local_user.id)

    return StateOut(
        total_balance=float(total_balance or 0.0),
        total_income_month=float(income_transactions or 0.0),
        total_expenses_month=abs(float(expense_transactions or 0.0)),
        accounts_count=accounts_count,
        transactions_count=transactions_count,
        last_sync=last_sync,
        import_batches_count=import_batches_count,
        last_import_at=last_import_at,
        user_goals=goals,
        accounts=accounts,
        transactions=transactions,
    )


# ---- /state/summary — Phase-F5 real implementation -----------------------


class StateSummaryOut(BaseModel):
    """Mirror of rules-service's ``DashboardSummary``. Field set is
    LOCKED — the cross-DB invariant test asserts the rules-service
    dashboard forwarder's response coerces to this Pydantic shape
    without any field-set drift.

    Reviewer #1 hardening: ``user_goals`` uses ``List[GoalSummary]`` so
    F5 cannot drift to a string list or untyped dict list silently.
    """
    total_balance: float
    total_income_month: float
    total_expenses_month: float
    accounts_count: int
    transactions_count: int
    last_sync: Optional[datetime] = None
    import_batches_count: int
    last_import_at: Optional[datetime] = None
    user_goals: List[GoalSummary] = []


def _goal_summaries(db: Session, local_user_id: int) -> List[GoalSummary]:
    """Phase-F5 aggregator helper: serialize non-archived goals for the
    local user, ordered by priority DESC then created_at ASC. Coerces
    SQLAlchemy rows to ``GoalSummary`` via ``from_attributes=True`` so
    wire-shape drift surfaces in the route layer rather than at the FE.
    """
    rows = (
        db.query(Goal)
        .filter(Goal.user_id == local_user_id, Goal.is_archived.is_(False))
        .order_by(Goal.priority.desc(), Goal.created_at.asc())
        .all()
    )
    return [GoalSummary.model_validate(row, from_attributes=True) for row in rows]


@router.get("/summary", response_model=StateSummaryOut)
async def get_summary(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> StateSummaryOut:
    """Phase-F5 real aggregator — the canonical implementation of
    ``DashboardSummary``. Verbatim SQL mirror of
    ``services/rules-service/app/routes/dashboard.py::get_dashboard_summary``
    minus the User lookup (delegated to
    ``app.routes.shared.get_or_create_local_user``).

    Every inner query is scoped to ``Account.user_id == local_user.id``
    (which comes from the JWT ``sub`` claim via ``require_user``).
    The auth gate guarantees this scope invariant even if a future
    bug accidentally drops the user_id filter on one of the inner
    queries.

    Editors of either rules-service's dashboard.py OR this file
    MUST keep them in lockstep per Phase-F2 shared-DB wiring —
    the cross-DB invariant test ``services/tests/test_state_aggregator_cross_db.py``
    locks the field set and the sum semantics end-to-end.
    """
    local_user = get_or_create_local_user(db, _current_user)

    total_balance = (
        db.query(func.coalesce(func.sum(Account.current_balance), 0.0))
        .filter(Account.user_id == local_user.id)
        .scalar()
    )

    now = datetime.now(timezone.utc)
    # Rolling 60-day window instead of calendar month. When imported
    # statements lag behind the current date (e.g. latest txn is May
    # 27 but it's July 3 — a 37-day gap), a calendar-month filter
    # returns $0 income and $0 expenses — confusing for the user.
    # A 60-day window comfortably covers typical statement lag
    # (banks export 30-45 days after period close) without drifting
    # so far that last-quarter data pollutes the "recent" view.
    #
    # Field names ``total_income_month`` / ``total_expenses_month``
    # are kept for wire-parity with ``DashboardSummary``; the
    # semantic change is internal only.
    window_start = now - timedelta(days=60)

    income_transactions = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .join(Account)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= window_start,
            Transaction.amount > 0,
        )
        .scalar()
    )
    expense_transactions = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .join(Account)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= window_start,
            Transaction.amount < 0,
        )
        .scalar()
    )

    accounts_count = (
        db.query(Account).filter(Account.user_id == local_user.id).count()
    )
    transactions_count = (
        db.query(Transaction)
        .join(Account)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= window_start,
        )
        .count()
    )

    last_sync = (
        db.query(func.max(Account.last_sync))
        .filter(Account.user_id == local_user.id)
        .scalar()
    )
    import_batches_count = (
        db.query(ImportBatch).filter(ImportBatch.user_id == local_user.id).count()
    )
    last_import_at = (
        db.query(func.max(ImportBatch.processed_at))
        .filter(ImportBatch.user_id == local_user.id)
        .scalar()
    )

    return StateSummaryOut(
        total_balance=float(total_balance or 0.0),
        total_income_month=float(income_transactions or 0.0),
        total_expenses_month=abs(float(expense_transactions or 0.0)),
        accounts_count=accounts_count,
        transactions_count=transactions_count,
        last_sync=last_sync,
        import_batches_count=import_batches_count,
        last_import_at=last_import_at,
        user_goals=_goal_summaries(db, local_user.id),
    )
