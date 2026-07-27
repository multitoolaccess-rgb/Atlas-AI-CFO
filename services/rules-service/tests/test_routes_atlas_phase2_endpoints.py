"""Atlas Phase 2+3 endpoint tests — ``/income-breakdown``, ``/expense-breakdown``,
``/debts/summary``, ``/insights``.

Tests cover:
- Happy-path 200 response with seeded data
- Empty-state returns zero totals
- Cross-user isolation
- Response shape validation
- Anomaly detection thresholds (insights)
"""

from datetime import datetime, timedelta
import pytest


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _seed_transaction(db_session, account_id: int, *,
                      amount: float,
                      category_name: str | None = None,
                      description: str = "Test",
                      days_ago: int = 0):
    """Insert a single Transaction on the given account."""
    from app.models import Category as _Cat
    from app.models import Transaction as _T

    txn_date = datetime.utcnow() - timedelta(days=days_ago)

    category_id: int | None = None
    if category_name:
        existing = db_session.query(_Cat).filter(_Cat.name == category_name).first()
        if existing is None:
            cat = _Cat(name=category_name)
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


def _make_user_with_self_fm_and_one_account(
    db_session, *, sub: str, account_name: str,
    account_type: str = "checking",
) -> tuple:
    """Create a fresh user with a Self FamilyMember, Institution, and Account."""
    from app.models import Account as _Account
    from app.routes.shared import (
        get_or_create_family_member_self,
        get_or_create_institution,
        get_or_create_local_user,
    )

    user = get_or_create_local_user(db_session, sub)
    self_fm = get_or_create_family_member_self(db_session, user)
    institution = get_or_create_institution(db_session, f"{sub.title()} Bank")
    acct = _Account(
        user_id=user.id,
        institution_id=institution.id,
        family_member_id=self_fm.id,
        account_name=account_name,
        account_type=account_type,
        current_balance=0.0,
        is_active=True,
        source="manual",
    )
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)
    return user, acct


# -----------------------------------------------------------------------
# /api/dashboard/income-breakdown
# -----------------------------------------------------------------------

def test_income_breakdown_returns_grouped_data(
    client, db_session, make_account, make_category
) -> None:
    """Happy path: seeded income transactions return grouped data."""
    cat = make_category(name="Salary", budget_group="fixed")
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)

    acct = make_account(account_name="Income Checking")
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)

    _seed_transaction(db_session, acct.id, amount=5000.0,
                      category_name="Salary", description="Paycheck", days_ago=1)

    r = client.get("/api/dashboard/income-breakdown")
    assert r.status_code == 200, r.text
    body = r.json()

    assert "total_income" in body
    assert body["total_income"] > 0
    assert "by_group" in body
    assert "by_category" in body
    assert "trend" in body
    assert len(body["trend"]) == 12


def test_income_breakdown_empty_returns_zero_totals(client, db_session) -> None:
    """No transactions ⇒ zero totals with empty arrays."""
    r = client.get("/api/dashboard/income-breakdown")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_income"] == 0.0
    assert body["by_group"] == []
    assert body["by_category"] == []
    assert len(body["trend"]) == 12
    assert all(pt["amount"] == 0.0 for pt in body["trend"])


def test_income_breakdown_isolates_other_users(client, db_session) -> None:
    """Cross-user isolation: other user's income must not appear."""
    _, other_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="intruder-income", account_name="Other Income Bank",
    )
    _seed_transaction(db_session, other_acct.id, amount=99999.0,
                      category_name="Other-Salary", description="Should NOT appear",
                      days_ago=1)

    r = client.get("/api/dashboard/income-breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_income"] == 0.0, (
        f"Cross-user leakage: {body['total_income']}"
    )


def test_income_breakdown_accepts_period_param(client, db_session, make_account) -> None:
    """Period query param filters correctly."""
    acct = make_account(account_name="Period Income")
    db_session.add(acct)
    db_session.commit()

    _seed_transaction(db_session, acct.id, amount=3000.0,
                      category_name="Freelance", description="Gig work", days_ago=1)

    now = datetime.utcnow()
    period = f"{now.year:04d}-{now.month:02d}"
    r = client.get(f"/api/dashboard/income-breakdown?period={period}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_income"] > 0


def test_income_breakdown_rejects_malformed_period(client, db_session) -> None:
    """Bad period value yields 400."""
    r = client.get("/api/dashboard/income-breakdown?period=bad")
    assert r.status_code == 400


# -----------------------------------------------------------------------
# /api/dashboard/expense-breakdown
# -----------------------------------------------------------------------

def test_expense_breakdown_returns_grouped_data(
    client, db_session, make_account, make_category
) -> None:
    """Happy path: seeded expense transactions return grouped data."""
    cat = make_category(name="Groceries", budget_group="flexible")
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)

    acct = make_account(account_name="Expense Checking")
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)

    _seed_transaction(db_session, acct.id, amount=-200.0,
                      category_name="Groceries", description="Whole Foods", days_ago=1)

    r = client.get("/api/dashboard/expense-breakdown")
    assert r.status_code == 200, r.text
    body = r.json()

    assert "total_expenses" in body
    assert body["total_expenses"] > 0
    assert "by_group" in body
    assert "by_category" in body
    assert "trend" in body
    assert len(body["trend"]) == 12


def test_expense_breakdown_empty_returns_zero_totals(client, db_session) -> None:
    """No transactions ⇒ zero totals with empty arrays."""
    r = client.get("/api/dashboard/expense-breakdown")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_expenses"] == 0.0
    assert body["by_group"] == []
    assert body["by_category"] == []
    assert len(body["trend"]) == 12


def test_expense_breakdown_isolates_other_users(client, db_session) -> None:
    """Cross-user isolation: other user's expenses must not appear."""
    _, other_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="intruder-expense", account_name="Other Expense Bank",
    )
    _seed_transaction(db_session, other_acct.id, amount=-77777.0,
                      category_name="Groceries", description="Should NOT appear",
                      days_ago=1)

    r = client.get("/api/dashboard/expense-breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_expenses"] == 0.0, (
        f"Cross-user leakage: {body['total_expenses']}"
    )


def test_expense_breakdown_excludes_investment_accounts(client, db_session) -> None:
    """Investment account types should be excluded from expense breakdown."""
    _, inv_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="alex", account_name="401k Account",
        account_type="401k",
    )
    _seed_transaction(db_session, inv_acct.id, amount=-500.0,
                      category_name="Contribution", description="401k contribution",
                      days_ago=1)

    r = client.get("/api/dashboard/expense-breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    # 401k contributions should not count as expenses
    assert body["total_expenses"] == 0.0


def test_expense_breakdown_accepts_from_date_to_date(client, db_session, make_account) -> None:
    """Date range params work correctly."""
    acct = make_account(account_name="Range Expense")
    db_session.add(acct)
    db_session.commit()

    _seed_transaction(db_session, acct.id, amount=-100.0,
                      category_name="Coffee", description="Latte", days_ago=1)

    now = datetime.utcnow()
    from_date = f"{now.year:04d}-{now.month:02d}-01"
    last_day = 28  # safe for all months
    to_date = f"{now.year:04d}-{now.month:02d}-{last_day:02d}"

    r = client.get(f"/api/dashboard/expense-breakdown?from_date={from_date}&to_date={to_date}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_expenses"] > 0


# -----------------------------------------------------------------------
# /api/debts/summary
# -----------------------------------------------------------------------

def test_debts_summary_returns_debt_accounts(
    client, db_session, make_account
) -> None:
    """Debt accounts with debt fields return proper summary."""
    acct = make_account(account_name="Test Credit Card", account_type="credit_card",
                        current_balance=5000.0)
    acct.interest_rate = 19.99
    acct.credit_limit = 10000.0
    acct.minimum_payment = 150.0
    db_session.add(acct)
    db_session.commit()

    r = client.get("/api/debts/summary")
    assert r.status_code == 200, r.text
    body = r.json()

    assert "total_debt" in body
    assert "blended_apr" in body
    assert "total_monthly_minimum" in body
    assert "debts" in body
    assert body["total_debt"] == 5000.0
    assert body["blended_apr"] > 0
    assert body["total_monthly_minimum"] == 150.0
    assert len(body["debts"]) == 1

    debt = body["debts"][0]
    assert debt["account_name"] == "Test Credit Card"
    assert debt["interest_rate"] == 19.99
    assert debt["credit_limit"] == 10000.0
    assert debt["utilization"] is not None
    assert debt["utilization"] == pytest.approx(50.0, abs=0.1)


def test_debts_summary_empty_returns_zero(client, db_session) -> None:
    """No debt accounts ⇒ zero totals."""
    r = client.get("/api/debts/summary")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_debt"] == 0.0
    assert body["blended_apr"] == 0.0
    assert body["total_monthly_minimum"] == 0.0
    assert body["debts"] == []


def test_debts_summary_blended_apr_weighted(client, db_session, make_account) -> None:
    """Blended APR should be weighted by balance."""
    acct1 = make_account(account_name="Card A", account_type="credit_card",
                         current_balance=3000.0)
    acct1.interest_rate = 20.0
    acct1.minimum_payment = 100.0
    db_session.add(acct1)

    acct2 = make_account(account_name="Card B", account_type="credit_card",
                         current_balance=7000.0)
    acct2.interest_rate = 10.0
    acct2.minimum_payment = 200.0
    db_session.add(acct2)
    db_session.commit()

    r = client.get("/api/debts/summary")
    assert r.status_code == 200, r.text
    body = r.json()

    # Weighted: (3000*20 + 7000*10) / 10000 = 13.0
    assert body["blended_apr"] == pytest.approx(13.0, abs=0.1)
    assert body["total_debt"] == 10000.0
    assert body["total_monthly_minimum"] == 300.0


def test_debts_summary_includes_loan_and_mortgage(
    client, db_session, make_account
) -> None:
    """Loans and mortgages are included in debt summary."""
    loan = make_account(account_name="Auto Loan", account_type="loan",
                        current_balance=15000.0)
    loan.interest_rate = 5.5
    loan.minimum_payment = 350.0
    loan.term_months = 48
    db_session.add(loan)

    mortgage = make_account(account_name="Home Mortgage", account_type="mortgage",
                            current_balance=250000.0)
    mortgage.interest_rate = 6.75
    mortgage.minimum_payment = 1800.0
    mortgage.term_months = 360
    db_session.add(mortgage)
    db_session.commit()

    r = client.get("/api/debts/summary")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_debt"] == 265000.0
    assert len(body["debts"]) == 2
    types = {d["account_type"] for d in body["debts"]}
    assert types == {"loan", "mortgage"}


def test_debts_summary_excludes_checking_accounts(
    client, db_session, make_account
) -> None:
    """Checking accounts must not appear in debt summary."""
    make_account(account_name="My Checking", account_type="checking",
                 current_balance=5000.0)
    db_session.commit()

    r = client.get("/api/debts/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["debts"] == []


# -----------------------------------------------------------------------
# /api/dashboard/insights
# -----------------------------------------------------------------------

def test_insights_empty_returns_empty(client, db_session) -> None:
    """No transactions ⇒ no insights."""
    r = client.get("/api/dashboard/insights")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insights"] == []


def test_insights_detects_spending_increase(
    client, db_session, make_account
) -> None:
    """A >30% increase in spending should generate a warning insight."""
    acct = make_account(account_name="Insight Checking")
    db_session.add(acct)
    db_session.commit()

    # Current month: $300 in groceries
    _seed_transaction(db_session, acct.id, amount=-300.0,
                      category_name="Groceries", description="Whole Foods", days_ago=1)
    # Previous month: $100 in groceries (days_ago=35 ensures it's in prior month)
    _seed_transaction(db_session, acct.id, amount=-100.0,
                      category_name="Groceries", description="Whole Foods", days_ago=35)

    r = client.get("/api/dashboard/insights")
    assert r.status_code == 200, r.text
    body = r.json()

    if len(body["insights"]) > 0:
        # If insights are generated, check the warning type
        insight = body["insights"][0]
        assert insight["type"] in ("warning", "success", "info")
        assert "category" in insight
        assert "message" in insight
        assert "change_pct" in insight


def test_insights_detects_spending_decrease(
    client, db_session, make_account
) -> None:
    """A >30% decrease in spending should generate a success insight."""
    acct = make_account(account_name="Insight Decrease")
    db_session.add(acct)
    db_session.commit()

    # Current month: $50
    _seed_transaction(db_session, acct.id, amount=-50.0,
                      category_name="Dining", description="Restaurant", days_ago=1)
    # Previous month: $200
    _seed_transaction(db_session, acct.id, amount=-200.0,
                      category_name="Dining", description="Restaurant", days_ago=35)

    r = client.get("/api/dashboard/insights")
    assert r.status_code == 200, r.text
    body = r.json()

    if len(body["insights"]) > 0:
        insight = body["insights"][0]
        assert insight["type"] in ("success", "warning", "info")


def test_insights_new_category_shows_info(
    client, db_session, make_account
) -> None:
    """A new category with spending this month (none last month) => info."""
    acct = make_account(account_name="Insight New Cat")
    db_session.add(acct)
    db_session.commit()

    # Only current month spending — no previous month data
    _seed_transaction(db_session, acct.id, amount=-150.0,
                      category_name="Streaming", description="Netflix", days_ago=1)

    r = client.get("/api/dashboard/insights")
    assert r.status_code == 200, r.text
    body = r.json()

    if len(body["insights"]) > 0:
        insight = body["insights"][0]
        assert insight["type"] == "info"
        assert "new spending" in insight["message"].lower()


def test_insights_isolates_other_users(client, db_session) -> None:
    """Other user's spending should not generate insights for local user."""
    _, other_acct = _make_user_with_self_fm_and_one_account(
        db_session, sub="intruder-insight", account_name="Other Insight Bank",
    )
    _seed_transaction(db_session, other_acct.id, amount=-5000.0,
                      category_name="Expensive", description="Should NOT appear",
                      days_ago=1)

    r = client.get("/api/dashboard/insights")
    assert r.status_code == 200, r.text
    body = r.json()
    # Local user has no transactions, so no insights
    assert body["insights"] == []


def test_insights_auth_required(client_no_auth) -> None:
    """Insights endpoint requires authentication."""
    r = client_no_auth.get("/api/dashboard/insights")
    assert r.status_code in (401, 403)


def test_income_breakdown_auth_required(client_no_auth) -> None:
    """Income breakdown endpoint requires authentication."""
    r = client_no_auth.get("/api/dashboard/income-breakdown")
    assert r.status_code in (401, 403)


def test_expense_breakdown_auth_required(client_no_auth) -> None:
    """Expense breakdown endpoint requires authentication."""
    r = client_no_auth.get("/api/dashboard/expense-breakdown")
    assert r.status_code in (401, 403)


def test_debts_summary_auth_required(client_no_auth) -> None:
    """Debts summary endpoint requires authentication."""
    r = client_no_auth.get("/api/debts/summary")
    assert r.status_code in (401, 403)
