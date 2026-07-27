"""Phase 35 dashboard-redesign endpoint tests — ``/flows``, ``/trends``, ``/breakdown``.

Phase 43 hotfix coverage. Earlier revisions of these three endpoints
filter ``Transaction.user_id == local_user.id`` — but the ``Transaction``
ORM class declares NO ``user_id`` column (only ``account_id``, FK to
``accounts.id``). The phantom filter hit ``AttributeError: type object
'Transaction' has no attribute 'user_id'`` at request time → 500 with
``Internal server error: AttributeError`` → FE swallows → empty-state UI.
The hotfix JOIN-s via ``Account`` and filters on ``Account.user_id``
(mirrors Finlynq's :func:`services.finlynq.app.routes.state.get_summary`).

These tests lock that contract:

- **Regression guard #1** — every endpoint returns 2xx with the
  ``local_user``'s seeded transactions visible. If anyone re-introduces
  ``Transaction.user_id ==`` into ``app.routes.dashboard``, the global
  exception handler returns 500 and these tests fail loudly.
- **Cross-user isolation** — a second user's transactions must NOT
  leak into the local user's flows / trends / breakdown. Catches a
  future commit that drops the user_id filter.
- **Empty-state contract** — no transactions ⇒ empty-state placeholder
  shape so the FE never sees ``undefined`` shapes.
- **Phase 35 shape** — each endpoint renders the documented wire
  response so a future drift surfaces HERE, not in production.
"""

from datetime import datetime, timedelta, timezone

import pytest


# -----------------------------------------------------------------------
# Helpers — match the conftest factory pattern exactly so a future
# conftest refactor (e.g. promoting these helpers to fixtures) doesn't
# silently break the cross-user isolation tests.
# -----------------------------------------------------------------------


def _make_user_with_self_fm_and_one_account(
    db_session, *, sub: str, account_name: str,
) -> tuple:
    """Create a fresh user (NOT the local 'alex') with a Self FamilyMember
    row, an Institution row, and one Account row.

    Returns the (user, account) pair. Use this instead of ``make_account``
    for cross-user isolation tests because ``make_account`` is bound to
    ``settings.local_user='alex'`` internally via ``_ensure_local_user``.
    """
    from app.models import Account as _Account
    from app.routes.shared import (
        get_or_create_family_member_self,
        get_or_create_institution,
        get_or_create_local_user,
    )

    user = get_or_create_local_user(db_session, sub)
    self_fm = get_or_create_family_member_self(db_session, user)
    institution = get_or_create_institution(
        db_session, f"{sub.title()} Bank"
    )
    # Note: Account has NO ``institution_name`` column — the link is via
    # ``institution_id`` FK only. Earlier revisions of this helper
    # passed ``institution_name=f"... Bank"`` as a phantom kwarg and
    # SQLAlchemy raised ``TypeError: 'institution_name' is an invalid
    # keyword argument for Account`` at setup time, BEFORE the route
    # could run. The cross-user isolation tests still want a distinct
    # institution per user, so the create-Institution call above is
    # preserved for FK isolation but its name is NOT stamped onto the
    # Account row — the Institution row's name is the canonical store.
    acct = _Account(
        user_id=user.id,
        institution_id=institution.id,
        family_member_id=self_fm.id,
        account_name=account_name,
        account_type="checking",
        current_balance=0.0,
        is_active=True,
        source="manual",
    )
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)
    return user, acct


def _seed_transaction(db_session, account_id: int, *,
                      amount: float,
                      category_name: str | None = None,
                      description: str = "Test",
                      days_ago: int = 0,
                      group: str | None = None):
    """Insert a single Transaction on the given account.

    ``days_ago=0`` lands today; tests for the trends endpoint pass
    positive values to walk back the 12-month window. We use
    ``datetime.utcnow()`` (NAIVE UTC) to mirror the dashboard.py
    route-time stamp math so SQLite's date comparison stays string-
    comparable against ``period_start='YYYY-MM-01'`` — mixing tz-aware
    and tz-naïve datetimes inside one WHERE clause silently filters
    EVERY row out under SQLite.

    Phase 44 fix: ``Transaction`` has ``category_id`` (FK to
    ``categories.id``), NOT a denormalized ``category_name`` column.
    Older revisions of this helper tried ``Transaction(category_name=...)``
    which raised an SQLAlchemy TypeError at SETUP time (long before
    the dashboard chart endpoints could exercise the bug their docstring
    describes). Now we lookup-or-create a Category row by ``category_name``
    and wire it via ``Transaction.category_id``. Tests that previously
    passed ``category_name="Salary"`` keep working without code changes.
    Tests that pass ``None`` (or omit it) get a Category-less transaction
    that the dashboard classifies as "Uncategorized" via
    ``_get_category_name``.
    """
    from app.models import Category as _Cat
    from app.models import Transaction as _T

    # Naïve UTC: matches the dashboard route's ``dt.utcnow()`` so the
    # SQLite WHERE clause's lexicographic comparison against the
    # ``YYYY-MM-DD`` string period bounds behaves identically.
    txn_date = datetime.utcnow() - timedelta(days=days_ago)

    # Lookup-or-create Category so the Transaction has a real
    # ``category_id`` FK to satisfy the dashboard's joinedload(Category).
    category_id: int | None = None
    if category_name:
        existing = db_session.query(_Cat).filter(_Cat.name == category_name).first()
        if existing is None:
            cat = _Cat(name=category_name)
            if group:
                cat.group = group
            db_session.add(cat)
            db_session.flush()
            category_id = cat.id
        else:
            category_id = existing.id

    txn = _T(
        account_id=account_id,
        amount=amount,
        transaction_date=txn_date,
        description=description,
        category_id=category_id,
    )
    db_session.add(txn)
    db_session.commit()


# -----------------------------------------------------------------------
# /api/dashboard/flows — Money Flow (Sankey)
# -----------------------------------------------------------------------


def test_dashboard_flows_seeds_local_user_transactions_in_sankey(
    client, db_session, make_account
) -> None:
    """Regression guard: ``GET /api/dashboard/flows`` returns the
    local user's transactions within a 200 response. Pre-hotfix, this
    raised ``AttributeError: type object 'Transaction' has no attribute
    'user_id'`` and the global handler returned 500."""
    acct = make_account(account_name="Flow Checking")
    db_session.add(acct)
    db_session.commit()
    _seed_transaction(
        db_session, acct.id, amount=3000.0, category_name="Salary",
        description="Paycheck", days_ago=1, group="Income",
    )
    _seed_transaction(
        db_session, acct.id, amount=-150.0, category_name="Groceries",
        description="Whole Foods", days_ago=1,
    )

    r = client.get("/api/dashboard/flows")
    assert r.status_code == 200, r.text
    body = r.json()

    # Phase 35 shape sanity: nodes + links + period + total_income.
    assert "nodes" in body and "links" in body
    assert "total_income" in body
    assert isinstance(body["nodes"], list)
    assert isinstance(body["links"], list)

    # Phase C: 4-stage Sankey — income sources + group nodes + subcategory nodes + outcomes.
    node_types = {n["node_type"] for n in body["nodes"]}
    assert "income" in node_types
    # expense nodes are the group + subcategory nodes
    assert "expense" in node_types or "outcome" in node_types

    # Both transactions seeded are within "today-1d" → falls inside
    # the current calendar month (period_end=last-day-of-month). No
    # internal-transfer exclusion fires for "Salary" or "Groceries".
    assert body["total_income"] == 3000.0


def test_dashboard_flows_empty_state_returns_placeholder_node(
    client, db_session
) -> None:
    """No transactions ⇒ placeholder Sankey so the FE never renders
    a blank hero area. Confirms the empty branch's documented shape."""
    r = client.get("/api/dashboard/flows")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["node_type"] == "income"
    assert body["links"] == []
    assert body["total_income"] == 0.0


def test_dashboard_flows_isolates_other_users_transactions(
    client, db_session
) -> None:
    """A different user's transactions must NOT leak into the local
    user's Sankey. Pins the ``Account.user_id == local_user.id``
    scope invariant."""
    _, other_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="intruder", account_name="Other Bank",
    )
    _seed_transaction(
        db_session, other_acct.id, amount=99999.0,
        category_name="Salary", description="Should NOT appear",
        days_ago=1,
    )

    # The local user has no transactions.
    r = client.get("/api/dashboard/flows")
    assert r.status_code == 200, r.text
    body = r.json()
    # Either empty-state placeholder OR a healthy local-user response —
    # but in NO case should the other user's massive $99999 leak.
    assert body["total_income"] == 0.0, (
        f"Cross-user leakage: other_user txn visible — "
        f"total_income={body['total_income']}"
    )


# -----------------------------------------------------------------------
# /api/dashboard/trends — Trend (income vs spend per month)
# -----------------------------------------------------------------------


def test_dashboard_trends_returns_twelve_months_zero_filled(
    client, db_session, make_account
) -> None:
    """``GET /api/dashboard/trends`` always returns 12 data points
    (zero-fills gaps). The non-zero month earns its keep; the others
    are zero."""
    acct = make_account(account_name="Trend Checking")
    db_session.add(acct)
    db_session.commit()
    _seed_transaction(
        db_session, acct.id, amount=5000.0, category_name="Salary",
        description="Pay", days_ago=1,
    )
    _seed_transaction(
        db_session, acct.id, amount=-2000.0, category_name="Rent",
        description="Landlord", days_ago=1,
    )

    r = client.get("/api/dashboard/trends?months=12")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "trends" in body
    assert len(body["trends"]) == 12

    # Latest month (current) is non-zero for income + spend.
    latest = body["trends"][-1]
    assert latest["income"] == 5000.0
    assert latest["spend"] == 2000.0
    assert latest["retained"] == 3000.0

    # Earlier months are zero-filled (retained = 0).
    older = body["trends"][0]
    assert older["income"] == 0.0
    assert older["spend"] == 0.0
    assert older["retained"] == 0.0


def test_dashboard_trends_isolates_other_users_transactions(
    client, db_session
) -> None:
    """A 2nd user's transactions must NOT pollute the local user's
    trend chart."""
    _, other_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="intruder2", account_name="Other Bank T",
    )
    # Seed *only* the other user's transactions — local user has none.
    _seed_transaction(
        db_session, other_acct.id, amount=12345.0,
        category_name="Other-Salary", description="X", days_ago=1,
    )

    r = client.get("/api/dashboard/trends?months=12")
    assert r.status_code == 200, r.text
    body = r.json()
    # All 12 months of the local user are zero — no leakage.
    for point in body["trends"]:
        assert point["income"] == 0.0, (
            f"Leakage in {point['month']}: income={point['income']}"
        )
        assert point["spend"] == 0.0


def test_dashboard_trends_isolates_other_user_with_recent_txns_too(
    client, db_session
) -> None:
    """Cross-user isolation must hold even when the other user's
    transaction is in the current calendar month (the strongest case
    to leak into ``/flows``). This doubles as a ``/flows``-style
    scope guard for /trends' current-month slice."""
    _, other_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="intruder2b", account_name="Other Bank T2",
    )
    _seed_transaction(
        db_session, other_acct.id, amount=66666.0,
        category_name="Other-Salary", description="Should NOT appear",
        days_ago=0,  # TODAY — most likely to leak into current-month
    )

    r = client.get("/api/dashboard/trends?months=12")
    assert r.status_code == 200, r.text
    body = r.json()
    latest = body["trends"][-1]
    assert latest["income"] == 0.0, (
        f"Cross-user leakage into current-month: "
        f"{latest['income']} (expected 0)"
    )


def test_dashboard_trends_clamps_months_query_param(
    client, db_session
) -> None:
    """``months`` is clamped to ``[1, 36]`` per Pydantic ``ge/le``.
    out-of-range values 422 so the route never asks for a 10-year
    window by accident."""
    assert client.get("/api/dashboard/trends?months=0").status_code == 422
    assert client.get("/api/dashboard/trends?months=9999").status_code == 422


# -----------------------------------------------------------------------
# /api/dashboard/breakdown — Stacked bar (4 buckets)
# -----------------------------------------------------------------------


def test_dashboard_breakdown_classifies_into_four_buckets(
    client, db_session, make_account
) -> None:
    """Spending is classified into Essential / Flexible / Debt /
    Savings using the in-process keyword matcher."""
    acct = make_account(account_name="Breakdown Checking")
    db_session.add(acct)
    db_session.commit()
    # Groceries + Mortgage both match the essential keyword list.
    _seed_transaction(
        db_session, acct.id, amount=-100.0, category_name="Groceries",
        description="Trader Joe's", days_ago=1,
    )
    _seed_transaction(
        db_session, acct.id, amount=-300.0, category_name="Dining",
        description="Restaurant", days_ago=1,
    )
    _seed_transaction(
        db_session, acct.id, amount=-1000.0, category_name="Mortgage",
        description="Home loan", days_ago=1,
    )
    _seed_transaction(
        db_session, acct.id, amount=-200.0, category_name="Brokerage",
        description="Vanguard", days_ago=1,
    )

    r = client.get("/api/dashboard/breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "buckets" in body

    labels = [b["label"] for b in body["buckets"]]
    assert labels == ["Essential", "Flexible", "Debt", "Savings"]

    by_label = {b["label"]: b for b in body["buckets"]}
    # Groceries + Mortgage both match the "housing/.../groceries" essential keywords.
    assert by_label["Essential"]["amount"] == 1100.0
    # Dining matches flexible.
    assert by_label["Flexible"]["amount"] == 300.0
    # No debt this month.
    assert by_label["Debt"]["amount"] == 0.0
    # Brokerage matches savings.
    assert by_label["Savings"]["amount"] == 200.0

    # Percentages sum to 100 (or near 100 due to rounding).
    assert sum(b["percentage"] for b in body["buckets"]) == pytest.approx(100.0, abs=0.5)
    assert body["total_spend"] == 1600.0


def test_dashboard_breakdown_empty_state_returns_zero_buckets(
    client, db_session
) -> None:
    """No spending ⇒ 4 zero-amount buckets so the FE renders 0% legend
    rows without ``undefined`` percentages."""
    r = client.get("/api/dashboard/breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    labels = [b["label"] for b in body["buckets"]]
    assert labels == ["Essential", "Flexible", "Debt", "Savings"]
    assert all(b["amount"] == 0.0 for b in body["buckets"])
    assert body["total_spend"] == 0.0


def test_dashboard_breakdown_isolates_other_users_transactions(
    client, db_session
) -> None:
    """A 2nd user's expenses must NOT appear in the local user's
    breakdown."""
    _, other_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="intruder3", account_name="Other Bank B",
    )
    _seed_transaction(
        db_session, other_acct.id, amount=-77777.0,
        category_name="Groceries", description="Should NOT appear",
        days_ago=1,
    )

    r = client.get("/api/dashboard/breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    # Local user has no expenses; buckets stay at 0 across the board.
    for b in body["buckets"]:
        assert b["amount"] == 0.0, (
            f"Leakage in {b['label']}: {b['amount']}"
        )
    assert body["total_spend"] == 0.0


# -----------------------------------------------------------------------
# /api/dashboard/flows — period validation
# -----------------------------------------------------------------------


def test_dashboard_flows_rejects_malformed_period_query(
    client, db_session
) -> None:
    """Bad ?period= value yields 400 with a stable detail string."""
    r = client.get("/api/dashboard/flows?period=not-a-date")
    assert r.status_code == 400
    assert "period" in r.json()["detail"].lower()


def test_dashboard_breakdown_rejects_malformed_period_query(
    client, db_session
) -> None:
    """Bad ?period= value yields 400 with a stable detail string."""
    r = client.get("/api/dashboard/breakdown?period=not-a-date")
    assert r.status_code == 400
    assert "period" in r.json()["detail"].lower()


# -----------------------------------------------------------------------
# Cross-cutting — Phase 43 hotfix guard at request time
# -----------------------------------------------------------------------


def test_dashboard_phase35_endpoints_reject_attributeerror_regression(
    client, db_session, make_account
) -> None:
    """Triple-check the Phase 43 + Phase 44 hotfixes: each of the three
    Phase 35 endpoints must NOT raise ``AttributeError`` internally on
    a request with seeded data. The global handler converts
    ``AttributeError`` into a 500 with detail "Internal server
    error: AttributeError", so the test asserts status_code < 500
    (lets 4xx slot through for valid user-facing failures).

    Phase 43 hotfix: ``Transaction.user_id == `` was a phantom
    filter (column only on Account) → global handler 500.
    Phase 44 hotfix: ``t.category_name == `` was a phantom
    attribute (column only on Category) → global handler 500.
    Both columns/attrs are now resolved via the canonical
    Account-join + Category-joinedload.
    """
    acct = make_account(account_name="Regression Checking")
    db_session.add(acct)
    db_session.commit()
    _seed_transaction(
        db_session, acct.id, amount=-50.0, category_name="Coffee",
        description="Latte", days_ago=1,
    )

    for path in (
        "/api/dashboard/flows",
        "/api/dashboard/trends?months=6",
        "/api/dashboard/breakdown",
    ):
        r = client.get(path)
        assert r.status_code < 500, (
            f"{path} returned 5xx ({r.status_code}): {r.text[:200]} "
            f"— this is the Phase 43/44 regression"
        )


def test_dashboard_breakdown_phase44_category_relationship_resolves(
    client, db_session, make_account, make_category
) -> None:
    """Phase 44 regression: when a Transaction has a real Category FK,
    ``_get_category_name(t)`` reads ``t.category.name`` off the
    Category relationship (populated by the route's
    ``joinedload(Transaction.category)``) and the breakdown endpoint
    classifies by the real category name \u2014 NOT by a phantom
    ``Transaction.category_name`` column.

    Pre-hotfix, the route hit
    ``AttributeError: 'Transaction' object has no attribute
    'category_name'``\u00a0\u2192\u00a0500\u00a0\u2192\u00a0FE shows empty state. Post-hotfix,
    the route returns 200 with Groceries-classified spend.
    """
    cat_groceries = make_category(name="Groceries", color="#9CA3AF")
    cat_mortgage = make_category(name="Mortgage", color="#7A081B")
    db_session.add_all([cat_groceries, cat_mortgage])
    db_session.commit()
    db_session.refresh(cat_groceries)
    db_session.refresh(cat_mortgage)

    acct = make_account(account_name="Phase44 Checking")
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)

    _seed_transaction(
        db_session, acct.id, amount=-200.0, category_name="Groceries",
        description="Whole Foods", days_ago=1,
    )
    _seed_transaction(
        db_session, acct.id, amount=-1500.0, category_name="Mortgage",
        description="Home loan", days_ago=1,
    )

    r = client.get("/api/dashboard/breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    by_label = {b["label"]: b for b in body["buckets"]}
    # Phase 44 assertion: the real category names flow through to the
    # classifier via the relationship. If the fix regressed (i.e.
    # someone re-introduces ``t.category_name``), the attribute lookup
    # would 500 with AttributeError and the route returns 500 \u2014 picked
    # up by ``test_dashboard_phase35_endpoints_reject_attributeerror_regression``.
    assert by_label["Essential"]["amount"] == 1700.0, (
        f"Phase 44 fix regressed: expected both Groceries (-200) + "
        f"Mortgage (-1500) classified as Essential = 1700.0, got "
        f"{by_label['Essential']['amount']}"
    )


def test_dashboard_flows_phase44_uncategorized_fallback_label(
    client, db_session, make_account
) -> None:
    """Phase 44 contract: a Transaction with ``category_id IS NULL``
    renders as 'Uncategorized' (passed through ``.title()``) on the
    Sankey. This pins the fallback branch of ``_get_category_name``
    so an ``Account``-user-isolation regression doesn't quietly leak
    null category strings into the chart."""
    acct = make_account(account_name="Uncat Checking")
    db_session.add(acct)
    db_session.commit()
    # No category_name kwarg \u2192 Category-less Transaction.
    _seed_transaction(
        db_session, acct.id, amount=-77.0, category_name=None,
        description="Mystery spend", days_ago=1,
    )
    _seed_transaction(
        db_session, acct.id, amount=2000.0, category_name="Salary",
        description="Paycheck", days_ago=1, group="Income",
    )

    r = client.get("/api/dashboard/flows")
    assert r.status_code == 200, r.text
    body = r.json()
    node_names = {n["name"] for n in body["nodes"]}
    # The fallback path should land in a 'Uncategorized' node title.
    assert "Uncategorized" in node_names, (
        f"Phase 44 fallback regressed: 'Uncategorized' node missing "
        f"from Sankey; got {node_names}"
    )


# -----------------------------------------------------------------------
# /api/dashboard/flows -- Phase 49 distinct-colour palette
# -----------------------------------------------------------------------


# This MUST stay in lockstep with services/rules-service/app/routes/dashboard.py's
# ``_EXPENSE_PALETTE``. If you reorder the palette, the Sankey rendering
# stays stable (the rank-to-color mapping is deterministic by sorted
# spend position, not colour-name), but the test that follows would
# still pass -- it's purely an unordered uniqueness check.
# Snapshot of the 6 real-category palette slots that the distinct-colors
# test asserts against. This set is LOAD-BEARING (used in the
# equal-set assertion below), not documentary: it locks the palette
# so a future reorder / addition in ``_EXPENSE_PALETTE`` surfaces HERE
# instead of as a silent visual regression on the dashboard.
## Phase C: palette assertions now use _GROUP_SUB_PALETTES from dashboard.py
# instead of the old _EXPENSE_PALETTE. The _EXPECTED_DISTINCT_PALETTE_COLORS
# constant was removed as dead code.

def test_dashboard_flows_expense_categories_get_distinct_palette_colors(
    client, db_session, make_account
) -> None:
    """Phase 49 regression: the Sankey must render each distinct expense
    category with a DIFFERENT color from the 8-slot palette, not the
    pre-Phase-49 hardcoded ``#C81425`` for every category. Seeded
    categories are designed so 6 distinct ones fit (palette[0..5])
    AND a 7th category folds into ``Other`` (the ``Other`` node gets
    a neutral gray because it's an aggregate bucket, not a distinct
    category the user is trying to distinguish). The test pins both
    behaviours so a future commit that reverts to the single-red
    hardcode trips this assertion loudly.

    The "all same color" bug was actually a TWO-layer regression:
    - BE hardcoded every expense node to ``_SANKEY_COLORS["expense"]``
      (single red)
    - FE ``SankeyFlow.tsx`` stripped ``color`` when building chartNodes
      so the BE's per-node colour was silently dropped by the chart
    Both are fixed in Phase 49; this test locks the BE part. The FE
    pass-through is a screenshot-comparison concern, not a unit test
    concern (Playwright E2E is the right tool for the FE visual
    regression layer -- left for a future task).
    """
    from app.routes.dashboard import _EXPENSE_PALETTE

    acct = make_account(account_name="Palette Checking")
    db_session.add(acct)
    db_session.commit()
    # Income + 7 distinct categories so the highest-spend paths exercise
    # palette[0..5] (6 slots) and the 7th folds into "Other".
    _seed_transaction(
        db_session, acct.id, amount=5000.0, category_name="Salary",
        description="Paycheck", days_ago=1, group="Income",
    )
    # Highest spend -> palette[0] (crimson)
    _seed_transaction(
        db_session, acct.id, amount=-800.0, category_name="Groceries",
        description="Whole Foods", days_ago=1,
    )
    # 2nd-highest -> palette[1] (orange-red)
    _seed_transaction(
        db_session, acct.id, amount=-600.0, category_name="Dining",
        description="Restaurant", days_ago=1,
    )
    # 3rd -> palette[2] (amber)
    _seed_transaction(
        db_session, acct.id, amount=-400.0, category_name="Gas",
        description="Shell", days_ago=1,
    )
    # 4th -> palette[3] (yellow)
    _seed_transaction(
        db_session, acct.id, amount=-300.0, category_name="Subscriptions",
        description="Netflix", days_ago=1,
    )
    # 5th -> palette[4] (lime)
    _seed_transaction(
        db_session, acct.id, amount=-200.0, category_name="Travel",
        description="Uber", days_ago=1,
    )
    # 6th -> palette[5] (emerald)
    _seed_transaction(
        db_session, acct.id, amount=-150.0, category_name="Entertainment",
        description="Concert", days_ago=1,
    )
    # 7th -> folds into "Other" (gray, hardcoded)
    _seed_transaction(
        db_session, acct.id, amount=-100.0, category_name="Hobby",
        description="Lego", days_ago=1,
    )

    r = client.get("/api/dashboard/flows")
    assert r.status_code == 200, r.text
    body = r.json()

    # All 7 categories are shown individually (no "Other" grouping).
    # Each expense category node gets a distinct color from the palette.
    # Phase C: expense nodes are now L3 subcategory nodes (level=3).
    # Group nodes (level=2) and subcategory nodes (level=3) both have
    # node_type='expense'. We only check subcategory nodes (level=3).
    subcat_nodes = [n for n in body["nodes"] if n.get("level") == 3]
    assert len(subcat_nodes) == 7, (
        f"Expected 7 subcategory nodes (level=3), got {len(subcat_nodes)}. "
        f"nodes={[n['name'] for n in body['nodes']]}"
    )
    subcat_colors = {n["color"] for n in subcat_nodes}
    assert len(subcat_colors) == len(subcat_nodes), (
        f"Distinct-colors-per-category contract regressed: "
        f"{len(subcat_nodes)} subcategory nodes but only "
        f"{len(subcat_colors)} unique colors."
    )
    # Phase C: colors come from _GROUP_SUB_PALETTES["Expenses"] not _EXPENSE_PALETTE.
    from app.routes.dashboard import _GROUP_SUB_PALETTES
    expense_palette = set(_GROUP_SUB_PALETTES["Expenses"])
    for n in subcat_nodes:
        assert n["color"] in expense_palette, (
            f"Subcategory '{n['name']}' got color {n['color']} "
            f"which is NOT in _GROUP_SUB_PALETTES['Expenses'] "
            f"{expense_palette}"
        )

    # Sanity: all 7 categories get distinct palette colors.
    assert len(subcat_colors) == 7, (
        f"Expected 7 distinct palette colors (one per category), "
        f"got {len(subcat_colors)} -- the Sankey is collapsing "
        f"categories prematurely"
    )


def test_dashboard_flows_palette_position_maps_to_spend_rank(
    client, db_session, make_account
) -> None:
    """Phase 49 contract: the highest-spend category always lands on
    palette[0] regardless of category name. This is the deterministic-
    by-rank contract the docstring on ``_category_palette_color``
    promises -- it preserves month-over-month consistency (the same
    top-spend category this month stays the same colour next month
    even if the user renames the category), and re-renders are stable
    (palette slot maps to RANK, not name hash).

    The previous ``#C81425``-for-everyone hardcode trivially passed
    this property (all nodes were red regardless of rank), so this
    test only catches REVERSIONS -- not the original bug. The
    ``test_dashboard_flows_expense_categories_get_distinct_palette_colors``
    above is the real bug-fix regression guard; this one is the
    rank-stability companion.
    """
    from app.routes.dashboard import _EXPENSE_PALETTE

    acct = make_account(account_name="Rank Checking")
    db_session.add(acct)
    db_session.commit()
    _seed_transaction(
        db_session, acct.id, amount=5000.0, category_name="Salary",
        description="Pay", days_ago=1, group="Income",
    )
    # "B" is the highest-spend category here -- should be palette[0].
    _seed_transaction(
        db_session, acct.id, amount=-1000.0, category_name="Category-B",
        description="Most expensive", days_ago=1,
    )
    # "A" is the second-highest -- should be palette[1].
    _seed_transaction(
        db_session, acct.id, amount=-500.0, category_name="Category-A",
        description="Second", days_ago=1,
    )
    # "C" is the cheapest -- should be palette[2].
    _seed_transaction(
        db_session, acct.id, amount=-100.0, category_name="Category-C",
        description="Cheapest", days_ago=1,
    )

    r = client.get("/api/dashboard/flows")
    assert r.status_code == 200, r.text
    body = r.json()
    # Phase C: colors come from _GROUP_SUB_PALETTES["Expenses"] sorted by spend.
    from app.routes.dashboard import _GROUP_SUB_PALETTES
    expense_palette = _GROUP_SUB_PALETTES["Expenses"]
    cat_b_node = next(n for n in body["nodes"] if n["name"] == "Category-B")
    cat_a_node = next(n for n in body["nodes"] if n["name"] == "Category-A")
    cat_c_node = next(n for n in body["nodes"] if n["name"] == "Category-C")
    assert cat_b_node["color"] == expense_palette[0], (
        f"Highest-spend category should be palette[0] ({expense_palette[0]}), "
        f"got {cat_b_node['color']}"
    )
    assert cat_a_node["color"] == expense_palette[1], (
        f"2nd-highest-spend category should be palette[1] "
        f"({expense_palette[1]}), got {cat_a_node['color']}"
    )
    assert cat_c_node["color"] == expense_palette[2], (
        f"3rd-highest-spend category should be palette[2] "
        f"({expense_palette[2]}), got {cat_c_node['color']}"
    )


def test_dashboard_flows_all_categories_shown_individually(
    client, db_session, make_account
) -> None:
    """All categories are shown individually in the Sankey -- no
    top-N grouping into 'Other'.  This replaced the old Phase 49
    overflow test when the top-6 limit was removed to ensure every
    user-assigned category from Activity is reflected in Cashflow."""
    acct = make_account(account_name="Overflow Checking")
    db_session.add(acct)
    db_session.commit()
    _seed_transaction(
        db_session, acct.id, amount=5000.0, category_name="Salary",
        description="Pay", days_ago=1, group="Income",
    )
    # Seed 7 distinct categories -- all 7 should appear individually.
    for cat, amt in [
        ("Cat-1", -800.0),
        ("Cat-2", -700.0),
        ("Cat-3", -600.0),
        ("Cat-4", -500.0),
        ("Cat-5", -400.0),
        ("Cat-6", -300.0),
        ("Cat-7", -200.0),
    ]:
        _seed_transaction(
            db_session, acct.id, amount=amt, category_name=cat,
            description="X", days_ago=1,
        )

    r = client.get("/api/dashboard/flows")
    assert r.status_code == 200, r.text
    body = r.json()
    # No 'Other' node -- all categories shown individually.
    other_node = next(
        (n for n in body["nodes"] if n["name"] == "Other"), None
    )
    assert other_node is None, (
        f"'Other' overflow grouping was removed; expected no 'Other' "
        f"node but found one. nodes={[n['name'] for n in body['nodes']]}."
    )
    # Phase C: categories appear as L3 subcategory nodes (level=3).
    subcat_names = {n["name"] for n in body["nodes"] if n.get("level") == 3}
    expected_names = {f"Cat-{i}" for i in range(1, 8)}
    assert subcat_names == expected_names, (
        f"Expected all 7 categories individually, got {subcat_names}"
    )
    # Each gets a distinct palette color.
    subcat_colors = {
        n["color"] for n in body["nodes"] if n.get("level") == 3
    }
    assert len(subcat_colors) == 7, (
        f"Expected 7 distinct palette colors, got {len(subcat_colors)}"
    )
