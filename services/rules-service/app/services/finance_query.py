"""Phase 30b + 30d — Real finance query tools for the assistant orchestrator.

Replaces the 30a mock ``get_totals`` with real queries against the
user's accounts + transactions. Each function takes ``(db, params)``
and returns a dict — the same call signature the orchestrator's
``TOOLS`` registry expects.

All queries are scoped to the local user via ``user_id`` so a
multi-user future doesn't leak data across rows. The functions are
pure SELECT — no writes, no side effects, no commits.

Date scoping:
- ``get_totals`` — sums across ALL transactions (lifetime).
- ``get_category_spend`` / ``get_merchant_spend`` — accept optional
  ``months_back`` (default 1 = current month) so the LLM can ask
  "how much on dining last month" vs "this month".
- ``get_cash_flow`` — accepts ``months_back`` (default 1).
- ``compute_savings_rate`` — uses the same ``months_back`` window.
- ``get_trends`` — monthly expense totals for the last N months.
- ``compare_periods`` — side-by-side comparison of two month windows.
- ``detect_anomalies`` — flags transactions > 2× the 90-day median
  per merchant (rule-based, no ML).
- ``predict_upcoming_bills`` — detects recurring merchants (≥3 hits
  with ~30-day intervals) and predicts the next due date + amount.
- ``compute_investable_surplus`` — income minus expenses minus goal
  contributions, using the Goal model for target tracking.

The ``months_back`` parameter is an integer: 0 = current month-to-date,
1 = last full month, 2 = two months ago, etc. The helper
:func:`_month_window` resolves it to a ``(start, end)`` datetime pair.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import case, extract, func, or_
from sqlalchemy.orm import Session

from app.account_types import CREDIT_ACCOUNT_TYPES
from app.models import Account, Category, Goal, Transaction

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Date helpers.
# ---------------------------------------------------------------------

def _month_window(months_back: int = 1) -> tuple[datetime, datetime]:
    """Resolve ``months_back`` to a ``(start, end)`` UTC datetime pair.

    ``months_back=0`` → current month-to-date (start = 1st of this
    month 00:00 UTC, end = now).
    ``months_back=1`` → last full month (start = 1st of last month,
    end = 1st of this month).
    ``months_back=2`` → the month before that, etc.

    Using UTC + first-of-month keeps the window deterministic across
    timezones (the user's bank statements may carry a different TZ
    than the server; a fixed UTC window avoids edge-case mismatches
    at month boundaries).
    """
    now = datetime.now(timezone.utc)
    # Start of the current month.
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if months_back <= 0:
        return current_month_start, now
    # Walk back N months from the current month start.
    year = current_month_start.year
    month = current_month_start.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    return start, current_month_start


# ---------------------------------------------------------------------
# Tool: get_totals
# ---------------------------------------------------------------------

def get_totals(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Return the user's total balance, monthly income, and monthly expenses.

    - ``total_balance``: sum of all active account ``current_balance``.
    - ``total_income_month``: sum of positive transactions in the
      current month-to-date.
    - ``total_expenses_month``: sum of negative transactions (absolute)
      in the current month-to-date.

    Replaces the 30a mock which returned hardcoded
    ``{125000, 8500, 4200}``.
    """
    # Total balance: assets minus liabilities.
    # After the dual-column migration (Phase 52+) every
    # credit-type account (credit_card / loan / mortgage) stores
    # ``current_balance`` as a POSITIVE magnitude (depository:
    # money owned; credit: money owed). The dashboard therefore
    # SUBTRACTS every credit-type account from net worth via a
    # single SQL CASE expression — the previously split
    # ``credit_card ADD directly, loan/mortgage SUBTRACT`` logic
    # collapses into one rule keyed off CREDIT_ACCOUNT_TYPES.
    # Keep the inlined set (not the import) so a future
    # ``CREDIT_ACCOUNT_TYPES`` re-shuffling can mirror the
    # single-source-of-truth set the dashboard reads.
    total_balance = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (
                            Account.account_type.in_(list(CREDIT_ACCOUNT_TYPES)),
                            -Account.current_balance,
                        ),
                        else_=Account.current_balance,
                    )
                ),
                0.0,
            )
        )
        .filter(Account.user_id == user_id, Account.is_active.is_(True))
        .scalar()
    ) or 0.0

    # Current month income + expenses.
    start, end = _month_window(0)
    income_expense = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount > 0, Transaction.amount),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount < 0, func.abs(Transaction.amount)),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("expenses"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .one()
    )

    return {
        "total_balance": round(float(total_balance), 2),
        "total_income_month": round(float(income_expense.income or 0.0), 2),
        "total_expenses_month": round(float(income_expense.expenses or 0.0), 2),
    }


# ---------------------------------------------------------------------
# Tool: get_category_spend
# ---------------------------------------------------------------------

def get_category_spend(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Return total spend for a category in a given month window.

    Params:
    - ``category`` (str, required): the category name (e.g. "Food & Dining").
    - ``months_back`` (int, optional, default 1): 0 = current month,
      1 = last month, etc.

    Returns:
    - ``category``: the resolved category name.
    - ``total_spend``: sum of absolute negative amounts (expenses only;
      positive amounts in the same category are ignored so a refund
      doesn't inflate the "spend" number).
    - ``transaction_count``: number of expense transactions.
    - ``months_back``: the resolved window.
    """
    category_name = (params.get("category") or "").strip()
    if not category_name:
        return {"error": "Missing required param 'category'."}

    months_back = _coerce_int(params.get("months_back"), default=1)

    # Resolve category by name (case-insensitive).
    category = (
        db.query(Category)
        .filter(func.lower(Category.name) == category_name.lower())
        .first()
    )
    if category is None:
        return {
            "category": category_name,
            "total_spend": 0.0,
            "transaction_count": 0,
            "months_back": months_back,
            "note": f"Category '{category_name}' not found.",
        }

    start, end = _month_window(months_back)
    result = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount < 0, func.abs(Transaction.amount)),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("spend"),
            func.count(Transaction.id).label("count"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.category_id == category.id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .one()
    )

    return {
        "category": category.name,
        "total_spend": round(float(result.spend or 0.0), 2),
        "transaction_count": int(result.count or 0),
        "months_back": months_back,
    }


# ---------------------------------------------------------------------
# Tool: get_merchant_spend
# ---------------------------------------------------------------------

def get_merchant_spend(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Return total spend for a merchant (substring match) in a month window.

    Params:
    - ``merchant`` (str, required): the merchant name or substring
      (e.g. "STARBUCKS", "Amazon"). Matched case-insensitively against
      both ``merchant_name`` and ``description``.
    - ``months_back`` (int, optional, default 1).

    Returns:
    - ``merchant``: the search term.
    - ``total_spend``: sum of absolute negative amounts.
    - ``transaction_count``: number of matching expense transactions.
    """
    merchant = (params.get("merchant") or "").strip()
    if not merchant:
        return {"error": "Missing required param 'merchant'."}

    months_back = _coerce_int(params.get("months_back"), default=1)
    # Escape LIKE wildcards so a search for "100%" doesn't match everything.
    escaped = merchant.upper().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"

    start, end = _month_window(months_back)
    result = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount < 0, func.abs(Transaction.amount)),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("spend"),
            func.count(Transaction.id).label("count"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            or_(
                func.upper(Transaction.merchant_name).like(pattern),
                func.upper(Transaction.description).like(pattern),
            ),
        )
        .one()
    )

    return {
        "merchant": merchant,
        "total_spend": round(float(result.spend or 0.0), 2),
        "transaction_count": int(result.count or 0),
        "months_back": months_back,
    }


# ---------------------------------------------------------------------
# Tool: get_cash_flow
# ---------------------------------------------------------------------

def get_cash_flow(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Return income, expenses, and net cash flow for a month window.

    Params:
    - ``months_back`` (int, optional, default 1).

    Returns:
    - ``income``: sum of positive transactions.
    - ``expenses``: sum of absolute negative transactions.
    - ``net_cash_flow``: income - expenses.
    - ``months_back``: the resolved window.
    """
    months_back = _coerce_int(params.get("months_back"), default=1)
    start, end = _month_window(months_back)

    result = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount > 0, Transaction.amount),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount < 0, func.abs(Transaction.amount)),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("expenses"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .one()
    )

    income = float(result.income or 0.0)
    expenses = float(result.expenses or 0.0)
    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net_cash_flow": round(income - expenses, 2),
        "months_back": months_back,
    }


# ---------------------------------------------------------------------
# Tool: compute_savings_rate
# ---------------------------------------------------------------------

def compute_savings_rate(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Return the savings rate for a month window.

    Savings rate = (income - expenses) / income × 100, clamped to 0–100.
    If income is 0, returns ``savings_rate=0`` with a note.

    Params:
    - ``months_back`` (int, optional, default 1).

    Returns:
    - ``income``, ``expenses``, ``net``: the raw numbers.
    - ``savings_rate``: percentage (0–100).
    - ``months_back``: the resolved window.
    """
    months_back = _coerce_int(params.get("months_back"), default=1)
    start, end = _month_window(months_back)

    result = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount > 0, Transaction.amount),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.amount < 0, func.abs(Transaction.amount)),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("expenses"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .one()
    )

    income = float(result.income or 0.0)
    expenses = float(result.expenses or 0.0)
    net = income - expenses
    if income > 0:
        rate = max(0.0, min(100.0, (net / income) * 100.0))
    else:
        rate = 0.0

    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net": round(net, 2),
        "savings_rate": round(rate, 1),
        "months_back": months_back,
    }


# ---------------------------------------------------------------------
# Tool: get_trends (Phase 30d)
# ---------------------------------------------------------------------

def get_trends(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Return monthly expense totals for the last N months.

    Produces a trend series the FE can render as a bar/line chart so
    the user can visually see whether spending is increasing or
    decreasing over time.

    Params:
    - ``months`` (int, optional, default 6): how many months to include
      in the trend, counting back from the current month. ``months=6``
      → the current month + 5 prior months.

    Returns:
    - ``trend``: list of ``{"month": "2026-07", "expenses": float,
      "income": float, "net": float}`` ordered oldest → newest.
    - ``direction``: ``"increasing"``, ``"decreasing"``, or ``"stable"``
      based on the slope of the expense line (a simple sign check on
      ``last - first``). Stable = flat within ±5%.
    - ``months``: the number of months returned.
    """
    months = max(1, min(24, _coerce_int(params.get("months"), default=6)))
    now = datetime.now(timezone.utc)

    # Build the list of (start, end, label) for each month.
    windows: list[tuple[datetime, datetime, str]] = []
    for i in range(months - 1, -1, -1):
        start, end = _month_window(i)
        label = start.strftime("%Y-%m")
        # For the current month (i=0), end = now; for others, end = start of next month.
        if i == 0:
            end = now
        windows.append((start, end, label))

    trend: list[dict[str, Any]] = []
    for start, end, label in windows:
        result = (
            db.query(
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount > 0, Transaction.amount),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("income"),
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount < 0, func.abs(Transaction.amount)),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("expenses"),
            )
            .join(Account, Account.id == Transaction.account_id)
            .filter(
                Account.user_id == user_id,
                Transaction.transaction_date >= start,
                Transaction.transaction_date <= end,
            )
            .one()
        )
        income = float(result.income or 0.0)
        expenses = float(result.expenses or 0.0)
        trend.append({
            "month": label,
            "expenses": round(expenses, 2),
            "income": round(income, 2),
            "net": round(income - expenses, 2),
        })

    # Determine direction from the expense series.
    if len(trend) >= 2:
        first = trend[0]["expenses"]
        last = trend[-1]["expenses"]
        if first > 0:
            pct_change = ((last - first) / first) * 100
        else:
            pct_change = 0.0 if last == 0 else 100.0
        if pct_change > 5:
            direction = "increasing"
        elif pct_change < -5:
            direction = "decreasing"
        else:
            direction = "stable"
    else:
        direction = "stable"

    return {
        "trend": trend,
        "direction": direction,
        "months": months,
    }


# ---------------------------------------------------------------------
# Tool: compare_periods (Phase 30d)
# ---------------------------------------------------------------------

def compare_periods(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Compare two month windows side-by-side.

    Useful for "how does this month compare to last month?" — returns
    income, expenses, and net for both periods plus deltas and
    percentage changes.

    Params:
    - ``period_a`` (int, optional, default 1): months_back for period A.
    - ``period_b`` (int, optional, default 0): months_back for period B
      (0 = current month-to-date).

    Returns:
    - ``period_a``: ``{"months_back": int, "income": float,
      "expenses": float, "net": float}``
    - ``period_b``: same shape.
    - ``deltas``: ``{"income": float, "expenses": float, "net": float}``
      (B - A).
    - "`percent_changes``: ``{"income": float|None, "expenses": float|None,
      "net": float|None}`` (None when the base is 0).
    """
    pa = _coerce_int(params.get("period_a"), default=1)
    pb = _coerce_int(params.get("period_b"), default=0)

    def _period_summary(months_back: int) -> dict[str, Any]:
        # Use a SINGLE-MONTH window, not the cumulative _month_window
        # which spans from N months ago to now. For compare_periods we
        # want to compare one month vs another, not overlapping ranges.
        start, _ = _month_window(months_back)
        if months_back <= 0:
            # Current month: end = now.
            end = datetime.now(timezone.utc)
        else:
            # The end is the start of the next month toward now.
            # _month_window(months_back - 1) gives us the start of the
            # month that is months_back-1 ago, which is the end boundary.
            end, _ = _month_window(months_back - 1)
        result = (
            db.query(
                func.coalesce(
                    func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0.0)),
                    0.0,
                ).label("income"),
                func.coalesce(
                    func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0.0)),
                    0.0,
                ).label("expenses"),
            )
            .join(Account, Account.id == Transaction.account_id)
            .filter(
                Account.user_id == user_id,
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
            .one()
        )
        income = float(result.income or 0.0)
        expenses = float(result.expenses or 0.0)
        return {
            "months_back": months_back,
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
        }

    a = _period_summary(pa)
    b = _period_summary(pb)

    def _pct(base: float, new: float) -> Optional[float]:
        if base == 0:
            return None
        return round(((new - base) / base) * 100, 1)

    return {
        "period_a": a,
        "period_b": b,
        "deltas": {
            "income": round(b["income"] - a["income"], 2),
            "expenses": round(b["expenses"] - a["expenses"], 2),
            "net": round(b["net"] - a["net"], 2),
        },
        "percent_changes": {
            "income": _pct(a["income"], b["income"]),
            "expenses": _pct(a["expenses"], b["expenses"]),
            "net": _pct(a["net"], b["net"]),
        },
    }


# ---------------------------------------------------------------------
# Tool: detect_anomalies (Phase 30d)
# ---------------------------------------------------------------------

def detect_anomalies(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Flag transactions that exceed 2× the 90-day median for the same
    merchant.

    Locked decision #2 (``docs/phase-30-plan.md``): rule-based anomaly
    detection, no ML. A transaction is flagged if its absolute amount
    exceeds 2× the median of all transactions for the same merchant in
    the trailing 90 days. Simple, deterministic, explainable.

    Params:
    - ``lookback_days`` (int, optional, default 90): the trailing window
      for computing the median.
    - ``threshold_multiplier`` (float, optional, default 2.0): the
      multiplier above which a transaction is flagged.
    - ``limit`` (int, optional, default 20): max anomalies to return.

    Returns:
    - ``anomalies``: list of ``{"transaction_id": int, "merchant": str,
      "amount": float, "median": float, "multiplier": float,
      "date": str}`` sorted by amount DESC.
    - ``count``: number of anomalies found.
    """
    lookback_days = max(7, min(365, _coerce_int(params.get("lookback_days"), default=90)))
    threshold = _coerce_float(params.get("threshold_multiplier"), default=2.0)
    limit = max(1, min(100, _coerce_int(params.get("limit"), default=20)))

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    # Step 1: compute the median abs-amount per merchant in the lookback window.
    # SQLAlchemy doesn't have a portable MEDIAN function; we use the
    # ``func.percentile_cont(0.5)`` with ``WITHIN GROUP`` on Postgres,
    # and fall back to a Python-side median on SQLite (the test/dev
    # path). The query below fetches all transactions in the window;
    # we group + compute the median in Python so the code is portable
    # across both dialects without a dialect switch.
    rows = (
        db.query(
            Transaction.id,
            Transaction.merchant_name,
            Transaction.description,
            Transaction.amount,
            Transaction.transaction_date,
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= cutoff,
            Transaction.transaction_date <= now,
            Transaction.amount < 0,  # expenses only (anomalies = unexpected spend)
        )
        .all()
    )

    if not rows:
        return {"anomalies": [], "count": 0}

    # Group by merchant (fall back to description prefix if merchant_name is null).
    merchant_txns: dict[str, list[tuple[int, float, datetime]]] = defaultdict(list)
    for row in rows:
        merchant = (row.merchant_name or _extract_merchant(row.description) or "Unknown").upper()
        # SQLite may return timezone-naive datetimes; normalise to UTC
        # so the comparison with ``now`` doesn't raise TypeError.
        txn_date = row.transaction_date
        if txn_date.tzinfo is None:
            txn_date = txn_date.replace(tzinfo=timezone.utc)
        merchant_txns[merchant].append((row.id, abs(row.amount), txn_date))

    # Compute median per merchant and flag anomalies.
    anomalies: list[dict[str, Any]] = []
    for merchant, txns in merchant_txns.items():
        if len(txns) < 2:
            # Need at least 2 transactions to establish a baseline.
            continue
        amounts = sorted(t[1] for t in txns)
        median = _median(amounts)
        if median <= 0:
            continue
        for txn_id, amount, date in txns:
            multiplier = amount / median
            if multiplier >= threshold:
                anomalies.append({
                    "transaction_id": txn_id,
                    "merchant": merchant,
                    "amount": round(amount, 2),
                    "median": round(median, 2),
                    "multiplier": round(multiplier, 1),
                    "date": date.isoformat() if date else None,
                })

    # Sort by amount descending, cap to limit.
    anomalies.sort(key=lambda a: a["amount"], reverse=True)
    anomalies = anomalies[:limit]

    return {
        "anomalies": anomalies,
        "count": len(anomalies),
        "lookback_days": lookback_days,
        "threshold_multiplier": threshold,
    }


# ---------------------------------------------------------------------
# Tool: predict_upcoming_bills (Phase 30d)
# ---------------------------------------------------------------------

def predict_upcoming_bills(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Detect recurring merchants and predict the next bill.

    Locked decision #3 (``docs/phase-30-plan.md``): group by merchant,
    require ≥3 historical hits with an interval of approximately 30 days
    (±5 days tolerance). The prediction uses the median interval + median
    amount; the next due date is the last transaction date + the median
    interval. No new table — detection runs on the existing ``transactions``
    table at query time.

    Params:
    - ``lookback_days`` (int, optional, default 180): trailing window for
      detecting recurring patterns.
    - ``min_hits`` (int, optional, default 3): minimum transactions for
      a merchant to be considered recurring.

    Returns:
    - ``bills``: list of ``{"merchant": str, "median_amount": float,
      "median_interval_days": int, "last_date": str,
      "predicted_next_date": str, "confidence": float,
      "hit_count": int}``.
      ``confidence`` is 0.0–1.0 based on interval consistency.
      ``hit_count`` is the number of historical transactions found.
    - ``count``: number of predicted bills.
    """
    lookback_days = max(30, min(365, _coerce_int(params.get("lookback_days"), default=180)))
    min_hits = max(2, min(20, _coerce_int(params.get("min_hits"), default=3)))

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    # Fetch all expense transactions in the window.
    rows = (
        db.query(
            Transaction.id,
            Transaction.merchant_name,
            Transaction.description,
            Transaction.amount,
            Transaction.transaction_date,
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= cutoff,
            Transaction.transaction_date <= now,
            Transaction.amount < 0,
        )
        .order_by(Transaction.transaction_date.asc())
        .all()
    )

    if not rows:
        return {"bills": [], "count": 0}

    # Group by merchant.
    merchant_txns: dict[str, list[tuple[float, datetime]]] = defaultdict(list)
    for row in rows:
        merchant = (row.merchant_name or _extract_merchant(row.description) or "Unknown").upper()
        # SQLite may return timezone-naive datetimes; normalise to UTC
        # so sorting + comparison with ``now`` don't raise TypeError.
        txn_date = row.transaction_date
        if txn_date.tzinfo is None:
            txn_date = txn_date.replace(tzinfo=timezone.utc)
        merchant_txns[merchant].append((abs(row.amount), txn_date))

    bills: list[dict[str, Any]] = []
    for merchant, txns in merchant_txns.items():
        if len(txns) < min_hits:
            continue

        # Sort by date ascending.
        txns.sort(key=lambda t: t[1])

        # Compute intervals between consecutive transactions.
        intervals: list[int] = []
        for i in range(1, len(txns)):
            delta = (txns[i][1] - txns[i - 1][1]).days
            intervals.append(delta)

        if not intervals:
            continue

        median_interval = _median([float(x) for x in intervals])
        median_amount = _median([t[0] for t in txns])

        # Check if intervals are approximately 30 days (±5 tolerance) OR
        # if the intervals are consistently the same value (e.g. weekly).
        # We accept merchants whose median interval is 7±3, 14±3, 30±5,
        # or any consistent interval with low variance.
        is_recurring = _is_recurring_interval(intervals)
        if not is_recurring:
            continue

        last_date = txns[-1][1]
        # SQLite may return timezone-naive datetimes; ensure we compare
        # against the timezone-aware ``now`` without a TypeError.
        if last_date.tzinfo is None:
            last_date = last_date.replace(tzinfo=timezone.utc)
        predicted_next = last_date + timedelta(days=int(round(median_interval)))

        # Confidence: how consistent are the intervals?
        if len(intervals) > 0:
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval > 0:
                variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
                std_dev = variance ** 0.5
                cv = std_dev / avg_interval  # coefficient of variation
                confidence = max(0.0, min(1.0, 1.0 - cv))
            else:
                confidence = 0.5
        else:
            confidence = 0.0

        # Only include bills that are upcoming (predicted_next >= now) or
        # recently due (predicted_next within the last 7 days).
        if predicted_next < now - timedelta(days=7):
            continue

        bills.append({
            "merchant": merchant,
            "median_amount": round(median_amount, 2),
            "median_interval_days": int(round(median_interval)),
            "last_date": last_date.date().isoformat() if last_date else None,
            "predicted_next_date": predicted_next.date().isoformat() if predicted_next else None,
            "confidence": round(confidence, 2),
            "hit_count": len(txns),
        })

    # Sort by predicted_next_date ascending.
    bills.sort(key=lambda b: b["predicted_next_date"] or "9999")

    return {
        "bills": bills,
        "count": len(bills),
    }


# ---------------------------------------------------------------------
# Tool: compute_investable_surplus (Phase 30d)
# ---------------------------------------------------------------------

def compute_investable_surplus(db: Session, params: dict, user_id: int) -> dict[str, Any]:
    """Compute the investable surplus after expenses and goal contributions.

    Uses the Goal model to determine how much the user is targeting per
    month for their goals, then subtracts that from the net cash flow
    to arrive at the surplus available for additional investments.

    Params:
    - ``months_back`` (int, optional, default 0): the month window for
      income/expenses (0 = current month-to-date).

    Returns:
    - ``income``, ``expenses``, "`net_cash_flow``: the month's cash flow.
    - ``monthly_goal_target``: sum of the user's non-archived goals'
      target_amount divided by their horizon_years (converted to a
      monthly figure). 0 if no goals or no horizon.
    - "`investable_surplus``: net_cash_flow - monthly_goal_target.
    - "`has_goals``: whether the user has any non-archived goals.
    """
    months_back = _coerce_int(params.get("months_back"), default=0)

    # Get the cash flow for the month.
    start, end = _month_window(months_back)
    cf_result = (
        db.query(
            func.coalesce(
                func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0.0)),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0.0)),
                0.0,
            ).label("expenses"),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .one()
    )

    income = float(cf_result.income or 0.0)
    expenses = float(cf_result.expenses or 0.0)
    net_cash_flow = income - expenses

    # Compute the monthly goal target from non-archived goals.
    goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == user_id,
            Goal.is_archived.is_(False),
        )
        .all()
    )

    monthly_goal_target = 0.0
    has_goals = len(goals) > 0
    for goal in goals:
        if goal.target_amount and goal.target_amount > 0 and goal.horizon_years and goal.horizon_years > 0:
            monthly_goal_target += goal.target_amount / (goal.horizon_years * 12)
        elif goal.target_amount and goal.target_amount > 0:
            # No horizon — assume a default 10-year horizon so the surplus
            # calculation still produces a meaningful monthly target.
            monthly_goal_target += goal.target_amount / (10 * 12)

    investable_surplus = net_cash_flow - monthly_goal_target

    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net_cash_flow": round(net_cash_flow, 2),
        "monthly_goal_target": round(monthly_goal_target, 2),
        "investable_surplus": round(investable_surplus, 2),
        "has_goals": has_goals,
        "goal_count": len(goals),
        "months_back": months_back,
    }


# ---------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------

def _coerce_int(value: Any, *, default: int) -> int:
    """Safely coerce an LLM-supplied param to int, falling back to default."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _coerce_float(value: Any, *, default: float) -> float:
    """Safely coerce an LLM-supplied param to float, falling back to default."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _median(values: list[float]) -> float:
    """Compute the median of a list of floats. The list must be sorted
    by the caller or this function sorts it internally."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
    return sorted_vals[mid]


def _extract_merchant(description: str | None) -> str | None:
    """Extract a merchant-like key from a transaction description.

    For transactions where ``merchant_name`` is NULL, we use the first
    3 words of the description as a grouping key. This is a simple
    heuristic — not a full merchant parser — but it's sufficient for
    anomaly detection and recurring bill prediction.
    """
    if not description:
        return None
    parts = description.strip().split()
    if not parts:
        return None
    return " ".join(parts[:3]).upper()


def _is_recurring_interval(intervals: list[int]) -> bool:
    """Check if a list of day-intervals looks like a recurring pattern.

    Accepts patterns where:
    - The median interval is near 7 (weekly ±3), 14 (biweekly ±3),
      30 (monthly ±5), or 90 (quarterly ±10).
    - OR the coefficient of variation is < 0.2 (very consistent intervals
      of any length, e.g. a fixed-day monthly debit).

    Rejects patterns where the intervals are wildly irregular (high
    coefficient of variation AND not near any known billing cycle).
    """
    if not intervals:
        return False
    median_int = _median([float(x) for x in intervals])
    # Check against known billing cycles.
    known_cycles = [
        (7, 3),    # weekly
        (14, 3),   # biweekly
        (30, 5),   # monthly
        (90, 10),  # quarterly
    ]
    for target, tolerance in known_cycles:
        if abs(median_int - target) <= tolerance:
            return True
    # Check coefficient of variation for any consistent interval.
    # Only accept if the intervals are very consistent (cv < 0.2) AND
    # the median is at least 5 days. This catches fixed-interval debits
    # that don't match the known cycles but are still clearly recurring.
    avg = sum(intervals) / len(intervals)
    if avg > 0:
        variance = sum((i - avg) ** 2 for i in intervals) / len(intervals)
        std_dev = variance ** 0.5
        cv = std_dev / avg
        # For the CV check, also require that ALL intervals are within
        # 50% of the average (no single outlier should be 3× the avg).
        max_ratio = max(abs(i - avg) / avg for i in intervals) if avg > 0 else 1.0
        if cv < 0.2 and median_int >= 5 and max_ratio < 0.5:
            return True
    return False
