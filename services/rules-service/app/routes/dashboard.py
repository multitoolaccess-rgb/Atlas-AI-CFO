"""Phase F5 -- ``/api/dashboard/summary`` is a thin httpx forwarder.

Phase F5 lift moved the dashboard aggregator from rules-service into
Finlynq (per Phase F2 shared-DB wiring + ``docs/master-plan.md``
end-state vision: Finlynq is the canonical store). rules-service's
``/api/dashboard/summary`` re-emits Finlynq's ``GET /state/summary``
response verbatim under the same JWT cookie.

Cross-service invariant locked by
``services/tests/test_state_aggregator_cross_db.py``: a request
through rules-service's dashboard forwarder reaches Finlynq's
``/state/summary`` aggregator, which queries the SAME shared DB
on a third independent ``create_engine`` round-trip. If Phase F2
wiring ever drifts, the third-engine seeded aggregates diverge
and this test goes red.

**Forwarder error envelope -- Phase F2 #1 + Phase F2 #2 contract:**
this route delegates to
:func:`app.routes.shared.forward_to_finlynq` so the cross-service
4xx policy is enforced in ONE place across dashboard, imports,
categories, and analyst-ratings:

- 401 / 403 from Finlynq -> OUR 502 Bad Gateway (downstream
  config drift; the FE shows "Downstream service is unavailable.
  Your session is fine...").
- 400 / 409 / 422 / 429 -> upstream verbatim (user-fixable
  errors propagate so the FE shows the actionable detail).
- 5xx -> 502 Bad Gateway.
- 3xx -> 502 Bad Gateway (3xx is meaningless on a GET round-trip).
- 2xx with non-JSON body -> 502 Bad Gateway.
- httpx TimeoutException / ConnectError / RequestError -> 502
  Bad Gateway (network-layer failures land in the same envelope
  bucket so the FE never shows them as a generic 5xx).
- 2xx with JSON that fails a downstream Pydantic -> 502 Bad
  Gateway (catches ``StateSummaryOut`` schema drift end-to-end).
"""

import calendar
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from sqlalchemy import case as sa_case, func
from sqlalchemy.orm import Session, joinedload

from app.auth import require_user
from app.account_types import classify_cashflow, CREDIT_ACCOUNT_TYPES, INVESTMENT_ACCOUNT_TYPES
from app.database import get_db
from app.models import Account, Transaction


def _get_category_name(t: Transaction) -> str:
    """Phase 44 — Transaction carries ``category_id`` (FK), not a
    denormalized ``category_name`` column. The Phase 35 chart
    endpoints read ``t.category_name`` directly, which hit
    ``AttributeError: 'Transaction' object has no attribute
    'category_name'`` and 500'd the whole dashboard. Resolve the
    name off the ``category`` ORM relationship (declared in
    ``app.models.transaction``) — falls back to ``"Uncategorized"``
    for ``category_id IS NULL`` (untagged txn from a fresh import)
    AND for a stale FK (``category_id`` set but Category row gone
    after a hard delete). Both cases paint the same picture on the
    Sankey / breakdown. The query that fetched ``t`` must include
    ``.options(joinedload(Transaction.category))`` — without it we
    fall back to lazy loading (one round-trip per row, N+1).
    """
    return t.category.name if t.category else "Uncategorized"


def _get_txn_account_type(t: Transaction) -> str:
    """Phase 52 — resolve the account type for a transaction.

    Uses the ``account`` relationship (populated by ``joinedload``
    on the parent query). Falls back to ``"checking"`` when the
    relationship isn't loaded — the safest default (no credit-card
    exclusions fire, standard income/expense logic applies).

    This helper is called per-row in the Sankey, trends, and
    breakdown endpoints. The N+1 protection comes from the caller's
    ``joinedload(Transaction.account)`` on the base query.
    """
    if t.account is not None:
        return (t.account.account_type or "checking").lower()
    return "checking"
from app.routes.shared import (
    forward_detail,
    forward_to_finlynq,
    get_or_create_local_user,
)
from app.schemas import (
    AnomaliesResponse,
    AnomalyItem,
    BreakdownBucket,
    BreakdownByCategory,
    BreakdownByGroup,
    BreakdownTrendPoint,
    DashboardBreakdownResponse,
    DashboardFlowsResponse,
    DashboardSummary,
    DashboardTrendsResponse,
    ExpenseBreakdownResponse,
    IncomeBreakdownResponse,
    InsightItem,
    InsightsResponse,
    SankeyLink,
    SankeyNode,
    TrendDataPoint,
    UpcomingBillItem,
    UpcomingBillsResponse,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Exposed for pytest stubbing in forwarder contract tests.
# The actual implementation uses the shared forwarding helper.
async def _forward(method: str, path: str, *, json: dict | None = None,
                   fc_session: str | None = None,
                   authorization: str | None = None):
    return await forward_to_finlynq(
        method, path, json=json, fc_session=fc_session,
        authorization=authorization,
    )


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    fc_session: str | None = Cookie(default=None, alias="fc_session"),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> DashboardSummary:
    """Forward to Finlynq's ``GET /state/summary``; apply the
    Phase F2 #2 drift-safe envelope on the way back.

    Path was ``/api/dashboard/summary`` pre-F5 (Phase-3 wealthiq lift).
    Path is unchanged post-F5; the implementation is a forwarder.

    The helper (:func:`forward_to_finlynq`) returns a
    :class:`ForwardResult` typed dict; on 2xx it carries the parsed
    JSON body so this route can hand it to ``DashboardSummary(**body)``
    for Pydantic validation. A Pydantic ValidationError surfaces here
    as 502 Bad Gateway -- our own envelope escalator
    (the route is wrapped by ``@app.exception_handler`` for unhandled
    ValidationError at the app level, so a real bug still fails
    loudly with a stable contract on the FE).

    The local user's profile anchor (``target_net_worth`` + ``time_horizon_years``)
    is merged into the response: Finlynq doesn't know about the
    profile row, so the FE's FinancialPlans fallback honors the user's
    in-DB anchor instead of the hardcoded $15M / 20y constant.
    """
    result = await _forward(
        "GET", "/state/summary", fc_session=fc_session,
        authorization=authorization,
    )

    if isinstance(result, httpx.Response):
        r = result
        if r.status_code >= 400:
            status_code = r.status_code
            if 500 <= status_code < 600 or 300 <= status_code < 400 or status_code in {401, 403}:
                status_code = 502
            raise HTTPException(
                status_code=status_code,
                detail=forward_detail(r),
            )
        try:
            body = r.json()
        except ValueError:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Finlynq upstream returned HTTP {r.status_code} but body "
                    f"is not JSON. Upstream response: {forward_detail(r)}"
                ),
            )
    else:
        if result["status_code"] >= 400:
            raise HTTPException(
                status_code=result["status_code"],
                detail=result["detail"],
            )
        body = result["body"]
    try:
        summary = DashboardSummary(**body)
    except Exception as _exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream schema drift on /state/summary: {_exc}",
        )

    # Phase 52 — override Finlynq's income/expense with account-type-aware
    # + payment-pattern-aware calculation using the shared classify_cashflow()
    # function. This mirrors the frontend's classifyCashflow() exactly.
    #
    # Phase 52+ — override total_balance: assets minus liabilities.
    # Credit-card balances are already negative after the Phase 52 sign
    # flip (purchases → negative, payments → positive), so adding them
    # directly reduces net worth. Loans/mortgages carry positive balances
    # (amount owed), so they are subtracted.
    # COALESCE(SUM(...), 0.0) returns 0.0 for an empty DB, so forwarder
    # tests with no accounts seeded still get 0.0 through.
    local_user = get_or_create_local_user(db, _current_user)
    _bal = (
        db.query(
            func.coalesce(
                func.sum(
                    sa_case(
                        (
                            Account.account_type.in_(set(CREDIT_ACCOUNT_TYPES)),
                            -Account.current_balance,
                        ),
                        else_=Account.current_balance,
                    )
                ),
                0.0,
            )
        )
        .filter(Account.user_id == local_user.id, Account.is_active.is_(True))
        .scalar()
    ) or 0.0
    summary.total_balance = round(float(_bal), 2)
    from datetime import datetime as dt
    import calendar
    # Phase 1 cert fix -- use proper datetime arithmetic with a HALF-OPEN
    # [start_of_month, start_of_next_month) interval. This eliminates the
    # UTC second-level boundary race where ``datetime.utcnow()`` at the
    # seed call and ``dt.utcnow()`` at the route call could land in
    # different months, causing ``_rows`` to come back empty.
    _now = dt.utcnow()
    _start = datetime.combine(date(_now.year, _now.month, 1), datetime.min.time())
    _next_month_first = date(_now.year + (_now.month // 12), (_now.month % 12) + 1, 1)
    _end_exclusive = datetime.combine(_next_month_first, datetime.min.time())
    _rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= _start,
            Transaction.transaction_date < _end_exclusive,
        )
        .all()
    )
    _income = 0.0
    _expenses = 0.0
    for t in _rows:
        at = _get_txn_account_type(t)
        cr = classify_cashflow(t.amount, at, t.description)
        _income += cr.income_effect
        _expenses += max(0.0, cr.expense_effect)  # refunds produce negative

    summary.total_income_month = round(_income, 2)
    summary.total_expenses_month = round(_expenses, 2)
    return summary


# ---------------------------------------------------------------------------
# Phase 35 — Dashboard Redesign: Money Flow endpoints
# ---------------------------------------------------------------------------

# Phase 52+ -- financial effects that count as outflows for
# the Sankey category aggregation.  Includes all effects that represent
# money leaving the user's control: consumer spending (expense/fee),
# wealth-building allocations (contribution/investment_buy), and
# debt reduction (principal_payment).  Excludes pure internal transfers
# (bill payments between owned accounts), income, reversals, and
# transactions with unclear semantics (ignored/needs_review).
# NOTE: "interest" is NOT here -- the interest effect always maps
# to income_effect (credit card interest charges use the fee effect).
_SPEND_EFFECTS: frozenset[str] = frozenset({
    "expense", "fee",
    "contribution", "investment_buy", "principal_payment",
})

_SANKEY_COLORS: dict[str, str] = {
    "income": "#A2D8F0",
    "expense": "#C81425",  # FALLBACK only -- used when the category palette is exhausted
    "allocation": "#0EA5E9",
    "outcome": "#059669",
}

# Phase 49 -- per-category expense palette. Each expense category gets a
# distinct color from this list (selected deterministically by its
# sorted-index position so the highest-spend category gets palette[0]).
# The previous contract hardcoded every expense node to a single
# `_SANKEY_COLORS["expense"]` red, which made "Groceries", "Dining",
# "Gas", "Other", etc. ALL render the same color on the Sankey hero.
# The FE Trust-but-verify corollary: the FE was ALSO stripping the
# `color` field when building chartNodes in ``SankeyFlow.tsx`` so even
# a backend fix was no-op'd by the FE. Both layers fixed here; the FE
# pass-through lands in the same Phase 49 + a regression test in
# ``test_routes_dashboard_phase35.py::test_expense_categories_get_distinct_colors``.
_EXPENSE_PALETTE: list[str] = [
    "#DC2626",  # crimson
    "#EA580C",  # orange-red
    "#F59E0B",  # amber
    "#EAB308",  # yellow
    "#84CC16",  # lime
    "#10B981",  # emerald
    "#0EA5E9",  # sky
    "#8B5CF6",  # violet
]


def _category_palette_color(sorted_index: int) -> str:
    """Deterministic palette slot for an expense category based on its
    sorted position (highest-spend gets palette[0]). Cycles through
    the palette so a >8-category portfolio still gets distinct colors.

    ``sorted_index`` is the position AFTER sorting by spend DESC,
    the same order the Sankey builds its expense stage. This makes
    the highest-spend category visually the most prominent color
    (red/crimson), month-over-month consistency is preserved (same
    category at the same rank gets the same color), and re-renders
    are stable (palette slot maps to rank, not name hash).
    """
    return _EXPENSE_PALETTE[sorted_index % len(_EXPENSE_PALETTE)]


# NOTE: ``_is_internal_inbound`` is defined FURTHER DOWN (it depends on
# ``_get_category_name`` reading ``t.category.id``). The Sankey flow
# endpoint below calls it via module-level name lookup (resolved at
# call-time, not import-time) so the forward reference works fine. The
# rest of the file follows.


# Phase C — group-aware color palette for the hierarchical Sankey.
# Each top-level group gets a distinct hue; subcategories within
# a group share the same hue at varying saturations.
_GROUP_COLORS: dict[str, str] = {
    "Income": "#059669",       # emerald
    "Expenses": "#DC2626",     # crimson
    "Debt": "#F59E0B",         # amber
    "Investments": "#0EA5E9",  # sky
    "Transfer": "#64748b",     # slate
}

_GROUP_SUB_PALETTES: dict[str, list[str]] = {
    "Income": ["#059669", "#10b981", "#34d399", "#6ee7b7", "#a7f3d9"],
    "Expenses": ["#DC2626", "#ea580c", "#f97316", "#a855f7", "#ec4899",
                  "#eab308", "#0ea5e9", "#3b82f6", "#ef4444", "#6366f1",
                  "#f59e0b", "#94a3b8", "#10b981", "#8b5cf6"],
    "Debt": ["#F59E0B", "#dc2626", "#b91c1c", "#991b1b", "#f87171"],
    "Investments": ["#0EA5E9", "#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6"],
    "Transfer": ["#64748b"],
}


def _group_sub_color(group: str, sorted_index: int) -> str:
    """Deterministic color for a subcategory within its group."""
    palette = _GROUP_SUB_PALETTES.get(group, _GROUP_SUB_PALETTES["Expenses"])
    return palette[sorted_index % len(palette)]


@router.get("/flows", response_model=DashboardFlowsResponse)
async def get_dashboard_flows(
    from_date: str | None = Query(default=None, description="ISO date start (YYYY-MM-DD)"),
    to_date: str | None = Query(default=None, description="ISO date end (YYYY-MM-DD)"),
    period: str | None = Query(default=None, description="YYYY-MM; legacy — use from_date/to_date for range"),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> DashboardFlowsResponse:
    """Phase C — 4-stage hierarchical Sankey money-flow chart.

    Aggregates transactions into a four-stage flow:
      Income Sources → Total Income → Groups (Expenses/Debt/Investments) → Subcategories

    Stage 0 (L0): Per-income-subcategory source nodes (Base Salary, Dividends, etc.)
    Stage 1 (L1): "Total Income" pool node
    Stage 2 (L2): Group nodes (Expenses, Debt, Investments) + Retained/Overspend
    Stage 3 (L3): Subcategory leaf nodes within each group

    Accepts either ``from_date``/``to_date`` (full range) or legacy
    ``period`` (single month YYYY-MM). When neither is provided,
    defaults to the current calendar month.
    """
    local_user = get_or_create_local_user(db, _current_user)

    # Derive period bounds
    if from_date and to_date:
        period_start = from_date[:10]
        period_end = to_date[:10]
    elif period:
        try:
            year, month = int(period[:4]), int(period[5:7])
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Period must be YYYY-MM")
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        period_start = f"{year:04d}-{month:02d}-01"
        period_end = f"{year:04d}-{month:02d}-{last_day:02d}"
    else:
        from datetime import datetime as dt
        now = dt.utcnow()
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        period_start = f"{now.year:04d}-{now.month:02d}-01"
        period_end = f"{now.year:04d}-{now.month:02d}-{last_day:02d}"

    txn_rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
        )
        .all()
    )

    if not txn_rows:
        return DashboardFlowsResponse(
            nodes=[SankeyNode(name="No transactions this month", node_type="income", color="#9CA3AF")],
            links=[],
            period_start=period_start,
            period_end=period_end,
            total_income=0.0,
        )

    # ── Single-pass aggregation ──────────────────────────────────────
    # income_by_cat: {category_name: total_income_effect}
    # spend_by_group_cat: {(group, category_name): total_spend}
    income_by_cat: dict[str, float] = {}
    spend_by_group_cat: dict[tuple[str, str], float] = {}
    income_total = 0.0
    expense_total = 0.0

    for t in txn_rows:
        at = _get_txn_account_type(t)
        cr = classify_cashflow(t.amount, at, t.description)

        # Income aggregation (L0 sources)
        if cr.income_effect > 0:
            cat_name = _get_category_name(t)
            group = t.category.group if t.category and t.category.group else "Income"
            # Only count Income-group transactions as income sources
            if group == "Income":
                income_by_cat[cat_name] = income_by_cat.get(cat_name, 0.0) + cr.income_effect
                income_total += cr.income_effect

        # Spending aggregation (L2 groups + L3 subcategories)
        if cr.effect in _SPEND_EFFECTS and t.amount < 0:
            spend_amt = abs(t.amount)
            expense_total += spend_amt
            cat_name = _get_category_name(t)
            group = t.category.group if t.category and t.category.group else "Expenses"
            key = (group, cat_name)
            spend_by_group_cat[key] = spend_by_group_cat.get(key, 0.0) + spend_amt

    # ── Build 4-stage Sankey ─────────────────────────────────────────
    nodes: list[SankeyNode] = []
    links: list[SankeyLink] = []

    # L0: Income source nodes (sorted by amount DESC)
    sorted_income = sorted(income_by_cat.items(), key=lambda x: -x[1])
    l0_indices: dict[str, int] = {}
    for idx, (cat_name, amount) in enumerate(sorted_income):
        l0_indices[cat_name] = len(nodes)
        nodes.append(SankeyNode(
            name=cat_name,
            node_type="income",
            color=_GROUP_COLORS["Income"],
            role="earn",
            group="Income",
            level=0,
        ))

    # L1: Total Income pool node
    l1_idx = len(nodes)
    nodes.append(SankeyNode(
        name="Total Income",
        node_type="income",
        color=_GROUP_COLORS["Income"],
        role="earn",
        group="Income",
        level=1,
    ))

    # L0 → L1 links
    for cat_name, idx in l0_indices.items():
        links.append(SankeyLink(source=idx, target=l1_idx, value=income_by_cat[cat_name]))

    # If no income but there is spending, create a virtual income node
    # so the Sankey isn't empty
    if income_total <= 0 and expense_total > 0:
        income_total = expense_total  # balance the diagram

    # L2: Group nodes (Expenses, Debt, Investments) + Retained
    # Aggregate spending by group
    group_totals: dict[str, float] = {}
    for (group, _cat), amount in spend_by_group_cat.items():
        group_totals[group] = group_totals.get(group, 0.0) + amount

    l2_indices: dict[str, int] = {}
    for group_name in ["Expenses", "Debt", "Investments"]:
        group_total = group_totals.get(group_name, 0.0)
        if group_total <= 0:
            continue
        l2_indices[group_name] = len(nodes)
        nodes.append(SankeyNode(
            name=group_name,
            node_type="expense",
            color=_GROUP_COLORS.get(group_name, "#94a3b8"),
            role="spend",
            group=group_name,
            level=2,
        ))

    # L1 → L2 links
    for group_name, idx in l2_indices.items():
        links.append(SankeyLink(source=l1_idx, target=idx, value=group_totals[group_name]))

    # Retained node (outcome)
    retained = income_total - expense_total
    retained_idx = len(nodes)
    nodes.append(SankeyNode(
        name="Retained",
        node_type="outcome",
        color=_SANKEY_COLORS["outcome"],
        role="save",
        level=2,
    ))
    links.append(SankeyLink(source=l1_idx, target=retained_idx, value=max(0, retained)))

    # Overspend node (if spending > income)
    if retained < 0:
        overspend_idx = len(nodes)
        nodes.append(SankeyNode(
            name="Overspend",
            node_type="outcome",
            color="#F59E0B",
            role="spend",
            level=0,
        ))
        # Overspend flows INTO Total Income to balance the diagram
        links.append(SankeyLink(source=overspend_idx, target=l1_idx, value=abs(retained)))

    # L3: Subcategory leaf nodes within each group
    # Sort subcategories by amount DESC within each group
    sorted_spend = sorted(spend_by_group_cat.items(), key=lambda x: (-x[1]))
    l3_indices: dict[str, int] = {}  # cat_name -> node index
    group_sub_counters: dict[str, int] = {}  # group -> count for palette

    for (group, cat_name), amount in sorted_spend:
        if group not in l2_indices:
            continue  # skip groups with no L2 node
        if cat_name in l3_indices:
            continue  # already added (shouldn't happen with tuple keys)

        sub_idx = group_sub_counters.get(group, 0)
        group_sub_counters[group] = sub_idx + 1

        node_idx = len(nodes)
        l3_indices[cat_name] = node_idx
        nodes.append(SankeyNode(
            name=cat_name,
            node_type="expense",
            color=_group_sub_color(group, sub_idx),
            role="spend",
            group=group,
            level=3,
        ))
        links.append(SankeyLink(source=l2_indices[group], target=node_idx, value=amount))

    return DashboardFlowsResponse(
        nodes=nodes,
        links=links,
        period_start=period_start,
        period_end=period_end,
        total_income=income_total,
    )


@router.get("/trends", response_model=DashboardTrendsResponse)
async def get_dashboard_trends(
    months: int = Query(default=12, ge=1, le=36, description="Number of months to return"),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> DashboardTrendsResponse:
    """Phase 35 — returns monthly income/spend/retained for the trend chart.

    Groups transactions by YYYY-MM, summing positive amounts as income
    and absolute negative amounts as spend. Retained = income - spend.
    Always returns exactly ``months`` data points (zero-fills gaps).
    """
    local_user = get_or_create_local_user(db, _current_user)

    from datetime import datetime as dt

    now = dt.utcnow()
    # Build list of the last N months (YYYY-MM)
    month_labels: list[str] = []
    y, m = now.year, now.month
    for _ in range(months):
        month_labels.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_labels.reverse()

    # Fetch all transactions across the window
    start_label = month_labels[0]
    end_label = month_labels[-1]
    import calendar

    end_last_day = calendar.monthrange(int(end_label[:4]), int(end_label[5:7]))[1]
    start_date = f"{start_label}-01"
    end_date = f"{end_label}-{end_last_day:02d}"

    txn_rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
        )
        .all()
    )

    # Phase 52 — use classify_cashflow() for consistent classification.
    month_data: dict[str, dict[str, float]] = {label: {"income": 0.0, "spend": 0.0} for label in month_labels}
    for t in txn_rows:
        label = t.transaction_date.strftime("%Y-%m")
        if label not in month_data:
            continue
        at = _get_txn_account_type(t)
        cr = classify_cashflow(t.amount, at, t.description)
        month_data[label]["income"] += cr.income_effect
        month_data[label]["spend"] += max(0.0, cr.expense_effect)

    trends = [
        TrendDataPoint(
            month=label,
            income=round(data["income"], 2),
            spend=round(data["spend"], 2),
            retained=round(data["income"] - data["spend"], 2),
        )
        for label, data in month_data.items()
    ]

    return DashboardTrendsResponse(trends=trends)


# ---------------------------------------------------------------------------
# Phase 35 (Phase 2) — Dashboard Breakdown
# ---------------------------------------------------------------------------

# Category → bucket classification. The categorizer has canonical human-
# readable names (seeded in ``app.services.categorizer`` + user-created
# via the Settings page). We classify permissive-substring so "Groceries"
# and "Groceries & Dining" both hit the essential bucket without requiring
# an exact match list that drifts every time the user adds a category.
_ESSENTIAL_KEYWORDS = [
    "housing", "rent", "mortgage", "utilities", "electric", "water", "gas",
    "groceries", "insurance", "healthcare", "medical", "phone", "internet",
    "childcare", "education", "tuition", "transportation", "fuel", "tax",
]
_FLEXIBLE_KEYWORDS = [
    "dining", "restaurant", "entertainment", "shopping", "travel",
    "subscription", "streaming", "hobby", "clothing", "gift", "charity",
]
_DEBT_KEYWORDS = [
    "credit card", "loan", "debt", "interest",
]
_SAVINGS_KEYWORDS = [
    "savings", "invest", "brokerage", "retirement", "ira", "401k",
    "deposit", "contribution",
]

_BREAKDOWN_COLORS = {
    "Essential": "#C81425",
    "Flexible": "#F59E0B",
    "Debt": "#7A081B",
    "Savings": "#059669",
}


def _classify_category(category_name: str | None) -> str:
    """Classify a category name into one of the four breakdown buckets."""
    if not category_name:
        return "Flexible"  # uncategorized → flexible (safe default)
    lower = category_name.lower()
    # Check savings FIRST (retirement accounts / investment transfers are
    # the highest-fidelity bucket — misclassifying a brokerage contribution
    # as "Flexible" would dramatically undercount the user's wealth-building).
    if any(kw in lower for kw in _SAVINGS_KEYWORDS):
        return "Savings"
    if any(kw in lower for kw in _DEBT_KEYWORDS):
        return "Debt"
    if any(kw in lower for kw in _ESSENTIAL_KEYWORDS):
        return "Essential"
    if any(kw in lower for kw in _FLEXIBLE_KEYWORDS):
        return "Flexible"
    return "Flexible"  # default fallback


@router.get("/breakdown", response_model=DashboardBreakdownResponse)
async def get_dashboard_breakdown(
    from_date: str | None = Query(default=None, description="ISO date start (YYYY-MM-DD)"),
    to_date: str | None = Query(default=None, description="ISO date end (YYYY-MM-DD)"),
    period: str | None = Query(default=None, description="YYYY-MM; legacy — use from_date/to_date for range"),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> DashboardBreakdownResponse:
    """Phase 35 (Phase 2) — returns spending broken into four buckets for
    the stacked bar breakdown panel.

    Aggregates negative-amount transactions and classifies them into
    Essential / Flexible / Debt / Savings using permissive category-name
    keyword matching.  Accepts ``from_date``/``to_date`` range or legacy
    ``period`` (single month). Defaults to current calendar month.
    """
    local_user = get_or_create_local_user(db, _current_user)

    if from_date and to_date:
        period_start = from_date[:10]
        period_end = to_date[:10]
        period_label = f"{period_start} to {period_end}"
    elif period:
        try:
            year, month = int(period[:4]), int(period[5:7])
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Period must be YYYY-MM")
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        period_start = f"{year:04d}-{month:02d}-01"
        period_end = f"{year:04d}-{month:02d}-{last_day:02d}"
        period_label = f"{year:04d}-{month:02d}"
    else:
        from datetime import datetime as dt
        now = dt.utcnow()
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        period_start = f"{now.year:04d}-{now.month:02d}-01"
        period_end = f"{now.year:04d}-{now.month:02d}-{last_day:02d}"
        period_label = f"{now.year:04d}-{now.month:02d}"

    # Phase 52 — exclude credit and investment account types from
    # the simple breakdown (they're capital flows, not spending).
    # Also filter by the breakdown's existing amount < 0 guard.
    txn_rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == local_user.id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.amount < 0,
            Account.account_type.notin_(set(INVESTMENT_ACCOUNT_TYPES)),
        )
        .all()
    )

    # Phase 52 — skip credit-card bill payments (internal transfers,
    # not spending). Credit card purchases (default) ARE counted. Uses
    # classify_cashflow() for consistent detection across all endpoints.
    bucket_totals: dict[str, float] = {"Essential": 0.0, "Flexible": 0.0, "Debt": 0.0, "Savings": 0.0}
    for t in txn_rows:
        cr = classify_cashflow(t.amount, _get_txn_account_type(t), t.description)
        if cr.effect == "transfer":
            continue  # bill payment → internal transfer, not spending
        bucket = _classify_category(_get_category_name(t))
        bucket_totals[bucket] += abs(t.amount)

    total_spend = sum(bucket_totals.values())

    buckets = [
        BreakdownBucket(
            label=label,
            amount=round(amount, 2),
            color=_BREAKDOWN_COLORS[label],
            percentage=round((amount / total_spend * 100) if total_spend > 0 else 0, 1),
        )
        for label, amount in bucket_totals.items()
    ]

    return DashboardBreakdownResponse(
        buckets=buckets,
        total_spend=round(total_spend, 2),
        period=period_label,
    )


# ---------------------------------------------------------------------------
# Atlas Phase 2 — Income / Expense Breakdown endpoints
# ---------------------------------------------------------------------------

def _parse_calendar_date(value: str, *, parameter: str) -> date:
    """Validate the date-only breakdown API contract without accepting instants."""

    if len(value) != 10:
        raise HTTPException(status_code=400, detail=f"{parameter} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{parameter} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=400, detail=f"{parameter} must be YYYY-MM-DD")
    return parsed


def _date_only_period_bounds(
    period_start: date, period_end: date
) -> tuple[str, str, datetime, datetime]:
    """Return display labels and UTC-naive half-open DB bounds for calendar dates.

    Transactions are stored using the service's existing ``datetime.utcnow()``
    convention.  Comparing bound ``datetime`` values keeps SQLite and
    PostgreSQL on the same timestamp comparison path while avoiding a fragile
    ``23:59:59`` upper bound that would lose fractional-second transactions.
    """

    if period_end < period_start:
        raise HTTPException(status_code=400, detail="to_date must not precede from_date")
    if period_end == date.max:
        raise HTTPException(
            status_code=400,
            detail="to_date must allow an exclusive next-day bound",
        )
    return (
        period_start.isoformat(),
        period_end.isoformat(),
        datetime.combine(period_start, datetime.min.time()),
        datetime.combine(period_end + timedelta(days=1), datetime.min.time()),
    )


def _resolve_period(
    from_date: str | None, to_date: str | None, period: str | None
) -> tuple[str, str, datetime, datetime]:
    """Resolve ISO calendar-date controls into display labels and [start, end) bounds."""

    # Preserve the established precedence for a fully explicit range: an
    # optional period selector has no effect when both calendar dates exist.
    if from_date is not None and to_date is not None:
        return _date_only_period_bounds(
            _parse_calendar_date(from_date, parameter="from_date"),
            _parse_calendar_date(to_date, parameter="to_date"),
        )

    # A one-sided control is bounded by the same selected/current-month range
    # used when no explicit dates are supplied.  This maintains the historic
    # bounded-query behavior while making the supplied date meaningful.
    if period:
        try:
            if len(period) != 7 or period[4] != "-":
                raise ValueError
            year, month = int(period[:4]), int(period[5:7])
            default_start = date(year, month, 1)
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Period must be YYYY-MM")
        last_day = calendar.monthrange(year, month)[1]
        default_end = date(year, month, last_day)
    else:
        now = datetime.utcnow()
        default_start = date(now.year, now.month, 1)
        default_end = date(now.year, now.month, calendar.monthrange(now.year, now.month)[1])

    return _date_only_period_bounds(
        _parse_calendar_date(from_date, parameter="from_date")
        if from_date is not None
        else default_start,
        _parse_calendar_date(to_date, parameter="to_date")
        if to_date is not None
        else default_end,
    )


def _build_breakdown(
    db: Session,
    user_id: int,
    period_start: datetime,
    period_end_exclusive: datetime,
    is_income: bool,
):
    """Shared aggregation for income/expense breakdown.

    Returns (total, by_group, by_category, trend) tuples.
    """
    from app.models import Category

    filters = [
        Account.user_id == user_id,
        Transaction.transaction_date >= period_start,
        Transaction.transaction_date < period_end_exclusive,
    ]
    # Expense breakdown excludes investment account types (401k, IRA, HSA,
    # etc.) to match the existing /api/dashboard/breakdown convention.
    if not is_income:
        filters.append(Account.account_type.notin_(set(INVESTMENT_ACCOUNT_TYPES)))

    txn_rows = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .join(Account, Account.id == Transaction.account_id)
        .filter(*filters)
        .all()
    )

    group_totals: dict[str, float] = {}
    cat_totals: dict[tuple[int, str, str], float] = {}  # (cat_id, cat_name, budget_group) -> amount
    month_totals: dict[str, float] = {}
    total = 0.0

    for t in txn_rows:
        at = _get_txn_account_type(t)
        cr = classify_cashflow(t.amount, at, t.description)
        effect = cr.income_effect if is_income else max(0.0, cr.expense_effect)
        if effect <= 0:
            continue

        total += effect

        cat_name = _get_category_name(t)
        budget_group = "other"
        cat_id = 0
        if t.category is not None:
            budget_group = t.category.budget_group or "other"
            cat_id = t.category.id

        group_totals[budget_group] = group_totals.get(budget_group, 0.0) + effect
        key = (cat_id, cat_name, budget_group)
        cat_totals[key] = cat_totals.get(key, 0.0) + effect

        month_label = t.transaction_date.strftime("%Y-%m")
        month_totals[month_label] = month_totals.get(month_label, 0.0) + effect

    by_group = sorted(
        [
            BreakdownByGroup(
                group=g,
                amount=round(amt, 2),
                percentage=round((amt / total * 100) if total > 0 else 0, 1),
            )
            for g, amt in group_totals.items()
        ],
        key=lambda x: -x.amount,
    )

    by_category = sorted(
        [
            BreakdownByCategory(
                category_id=cid,
                category_name=cname,
                budget_group=bg,
                amount=round(amt, 2),
            )
            for (cid, cname, bg), amt in cat_totals.items()
        ],
        key=lambda x: -x.amount,
    )

    # Build trend (last 12 months, zero-filled)
    from datetime import datetime as dt
    now = dt.utcnow()
    trend_months: list[str] = []
    y, m = now.year, now.month
    for _ in range(12):
        trend_months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    trend_months.reverse()

    trend = [
        BreakdownTrendPoint(month=label, amount=round(month_totals.get(label, 0.0), 2))
        for label in trend_months
    ]

    return total, by_group, by_category, trend


@router.get("/income-breakdown", response_model=IncomeBreakdownResponse)
async def get_income_breakdown(
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> IncomeBreakdownResponse:
    """Income grouped by budget_group + category with monthly trend."""
    local_user = get_or_create_local_user(db, _current_user)
    period_start, period_end, query_start, query_end_exclusive = _resolve_period(
        from_date, to_date, period
    )
    total, by_group, by_category, trend = _build_breakdown(
        db, local_user.id, query_start, query_end_exclusive, is_income=True
    )
    return IncomeBreakdownResponse(
        period_start=period_start,
        period_end=period_end,
        total_income=round(total, 2),
        by_group=by_group,
        by_category=by_category,
        trend=trend,
    )


@router.get("/expense-breakdown", response_model=ExpenseBreakdownResponse)
async def get_expense_breakdown(
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> ExpenseBreakdownResponse:
    """Expenses grouped by budget_group + category with monthly trend."""
    local_user = get_or_create_local_user(db, _current_user)
    period_start, period_end, query_start, query_end_exclusive = _resolve_period(
        from_date, to_date, period
    )
    total, by_group, by_category, trend = _build_breakdown(
        db, local_user.id, query_start, query_end_exclusive, is_income=False
    )
    return ExpenseBreakdownResponse(
        period_start=period_start,
        period_end=period_end,
        total_expenses=round(total, 2),
        by_group=by_group,
        by_category=by_category,
        trend=trend,
    )


@router.get("/insights", response_model=InsightsResponse)
async def get_dashboard_insights(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> InsightsResponse:
    """Anomaly detection — compare current month vs previous month spending
    by category. Flags categories with >30% increase as warnings."""
    from datetime import datetime as dt
    import calendar

    local_user = get_or_create_local_user(db, _current_user)
    now = dt.utcnow()

    # Current month
    cur_last = calendar.monthrange(now.year, now.month)[1]
    cur_start = f"{now.year:04d}-{now.month:02d}-01"
    cur_end = f"{now.year:04d}-{now.month:02d}-{cur_last:02d}"

    # Previous month
    prev_month = now.month - 1 if now.month > 1 else 12
    prev_year = now.year if now.month > 1 else now.year - 1
    prev_last = calendar.monthrange(prev_year, prev_month)[1]
    prev_start = f"{prev_year:04d}-{prev_month:02d}-01"
    prev_end = f"{prev_year:04d}-{prev_month:02d}-{prev_last:02d}"

    def _spend_by_category(start: str, end: str) -> dict[str, float]:
        rows = (
            db.query(Transaction)
            .options(joinedload(Transaction.category), joinedload(Transaction.account))
            .join(Account, Account.id == Transaction.account_id)
            .filter(
                Account.user_id == local_user.id,
                Transaction.transaction_date >= start,
                Transaction.transaction_date <= end,
            )
            .all()
        )
        totals: dict[str, float] = {}
        for t in rows:
            cr = classify_cashflow(t.amount, _get_txn_account_type(t), t.description)
            if cr.expense_effect > 0:
                cat_name = _get_category_name(t)
                totals[cat_name] = totals.get(cat_name, 0.0) + cr.expense_effect
        return totals

    current_spend = _spend_by_category(cur_start, cur_end)
    previous_spend = _spend_by_category(prev_start, prev_end)

    insights: list[InsightItem] = []
    all_categories = set(current_spend.keys()) | set(previous_spend.keys())

    for cat in sorted(all_categories):
        cur = current_spend.get(cat, 0.0)
        prev = previous_spend.get(cat, 0.0)

        if prev < 1.0 and cur < 1.0:
            continue  # Skip negligible categories

        if prev < 1.0:
            # New category this month
            insights.append(InsightItem(
                type="info",
                category=cat,
                message=f"{cat}: new spending this month (${cur:,.0f})",
                current=round(cur, 2),
                previous=0.0,
                change_pct=100.0,
            ))
            continue

        change_pct = ((cur - prev) / prev) * 100

        if change_pct > 30:
            insights.append(InsightItem(
                type="warning",
                category=cat,
                message=f"{cat} spend up {change_pct:.0f}% vs last month",
                current=round(cur, 2),
                previous=round(prev, 2),
                change_pct=round(change_pct, 1),
            ))
        elif change_pct < -30:
            insights.append(InsightItem(
                type="success",
                category=cat,
                message=f"{cat} spend down {abs(change_pct):.0f}% vs last month",
                current=round(cur, 2),
                previous=round(prev, 2),
                change_pct=round(change_pct, 1),
            ))

    # Sort by absolute change descending (most significant first)
    insights.sort(key=lambda x: abs(x.change_pct), reverse=True)

    return InsightsResponse(insights=insights)


# ---------------------------------------------------------------------------
# Phase 3 (Alerts) — Anomaly detection + Upcoming bills endpoints
# ---------------------------------------------------------------------------


@router.get("/anomalies", response_model=AnomaliesResponse)
async def get_dashboard_anomalies(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> AnomaliesResponse:
    """Flag transactions exceeding 2× the 90-day merchant median.

    Thin HTTP wrapper around :func:`finance_query.detect_anomalies`.
    Returns the top 20 anomalies sorted by amount DESC.
    """
    from app.services.finance_query import detect_anomalies

    local_user = get_or_create_local_user(db, _current_user)
    result = detect_anomalies(db, {}, local_user.id)
    return AnomaliesResponse(
        anomalies=[
            AnomalyItem(
                transaction_id=a["transaction_id"],
                merchant=a["merchant"],
                amount=a["amount"],
                median=a["median"],
                multiplier=a["multiplier"],
                date=a.get("date"),
            )
            for a in result["anomalies"]
        ],
        count=result["count"],
    )


@router.get("/upcoming-bills", response_model=UpcomingBillsResponse)
async def get_dashboard_upcoming_bills(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> UpcomingBillsResponse:
    """Detect recurring merchants and predict the next bill.

    Thin HTTP wrapper around :func:`finance_query.predict_upcoming_bills`.
    """
    from app.services.finance_query import predict_upcoming_bills

    local_user = get_or_create_local_user(db, _current_user)
    result = predict_upcoming_bills(db, {}, local_user.id)
    return UpcomingBillsResponse(
        bills=[
            UpcomingBillItem(
                merchant=b["merchant"],
                median_amount=b["median_amount"],
                median_interval_days=b["median_interval_days"],
                last_date=b.get("last_date"),
                predicted_next_date=b.get("predicted_next_date"),
                confidence=b["confidence"],
                hit_count=b["hit_count"],
            )
            for b in result["bills"]
        ],
        count=result["count"],
    )
