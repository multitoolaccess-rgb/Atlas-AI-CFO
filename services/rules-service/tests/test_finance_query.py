"""Phase 30b — Unit tests for the real finance query tools.

Each test seeds accounts + transactions + categories via the conftest
fixtures, then calls a ``finance_query`` function and asserts the
returned dict has the expected shape + values.

The tests mirror the patterns in ``test_services_categorizer_v2.py``:
use ``client`` + ``db_session`` fixtures, seed via the helper
functions, and assert on the dict return value (not the HTTP layer —
that's covered by ``test_routes_assistant.py``).
"""
from datetime import datetime, timezone

import pytest

from app.models import Category
from app.services.finance_query import (
    _coerce_int,
    _month_window,
    compute_savings_rate,
    get_cash_flow,
    get_category_spend,
    get_merchant_spend,
    get_totals,
)
from app.services.categorizer import seed_default_categories


@pytest.fixture
def seeded_finance_data(client, db_session, make_account, make_transaction):
    """Seed a user with 1 account, categories, and transactions.

    Layout (all in the current month so get_totals/month-0 queries see them):
    - Account: "Checking", balance 10000
    - Categories: defaults (seeded) + explicit refs
    - Transactions:
      * +5000 payroll (Income)
      * -200 Starbucks (Food & Dining)
      * -800 Amazon (Shopping)
      * -300 SERVICEMAC (Bills & Utilities, via MORTGAGE keyword)
    """
    seed_default_categories(db_session)
    db_session.commit()

    account = make_account(
        account_name="Checking",
        account_type="checking",
        current_balance=10000.0,
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Expenses — tagged
    food_cat = db_session.query(Category).filter(Category.name == "Food & Dining").first()
    shopping_cat = db_session.query(Category).filter(Category.name == "Shopping").first()
    bills_cat = db_session.query(Category).filter(Category.name == "Bills & Utilities").first()

    txns = [
        make_transaction(
            account_id=account.id,
            description="PAYROLL DEPOSIT",
            amount=5000.0,
            merchant_name="EMPLOYER",
        ),
        make_transaction(
            account_id=account.id,
            description="STARBUCKS COFFEE",
            amount=-200.0,
            merchant_name="STARBUCKS",
            category_id=food_cat.id if food_cat else None,
        ),
        make_transaction(
            account_id=account.id,
            description="AMAZON.COM PURCHASE",
            amount=-800.0,
            merchant_name="AMAZON",
            category_id=shopping_cat.id if shopping_cat else None,
        ),
        make_transaction(
            account_id=account.id,
            description="MORTGAGE PAYMENT SERVICEMAC",
            amount=-300.0,
            merchant_name="SERVICEMAC",
            category_id=bills_cat.id if bills_cat else None,
        ),
    ]
    for t in txns:
        db_session.add(t)
    db_session.commit()

    # Resolve the user_id from the account.
    user_id = account.user_id
    return {"account": account, "user_id": user_id}


# ---------------------------------------------------------------------
# get_totals
# ---------------------------------------------------------------------

def test_get_totals_returns_balance_and_monthly_income_expenses(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = get_totals(db_session, {}, uid)

    assert "total_balance" in result
    assert "total_income_month" in result
    assert "total_expenses_month" in result
    assert result["total_balance"] == 10000.0
    assert result["total_income_month"] == 5000.0
    assert result["total_expenses_month"] == 1300.0  # 200 + 800 + 300


def test_get_totals_with_no_accounts_returns_zeros(client, db_session):
    """A user with no accounts should get zeros, not an error."""
    # Use a non-existent user_id.
    result = get_totals(db_session, {}, 99999)
    assert result["total_balance"] == 0.0
    assert result["total_income_month"] == 0.0
    assert result["total_expenses_month"] == 0.0


# ---------------------------------------------------------------------
# get_category_spend
# ---------------------------------------------------------------------

def test_get_category_spend_returns_spend_for_named_category(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = get_category_spend(db_session, {"category": "Food & Dining", "months_back": 0}, uid)

    assert result["category"] == "Food & Dining"
    assert result["total_spend"] == 200.0
    assert result["transaction_count"] == 1
    assert result["months_back"] == 0


def test_get_category_spend_case_insensitive(client, db_session, seeded_finance_data):
    uid = seeded_finance_data["user_id"]
    result = get_category_spend(db_session, {"category": "food & dining", "months_back": 0}, uid)
    assert result["category"] == "Food & Dining"
    assert result["total_spend"] == 200.0


def test_get_category_spend_missing_category_returns_note(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = get_category_spend(db_session, {"category": "Nonexistent"}, uid)
    assert result["total_spend"] == 0.0
    assert result["transaction_count"] == 0
    assert "not found" in result.get("note", "").lower()


def test_get_category_spend_resolves_dining_alias(
    client, db_session, seeded_finance_data
):
    """Phase 30f — the LLM passes "dining" but the canonical category
    is "Food & Dining". The alias map must resolve it so the user sees
    real spend instead of a silent 0."""
    uid = seeded_finance_data["user_id"]
    result = get_category_spend(db_session, {"category": "dining", "months_back": 0}, uid)
    assert result["category"] == "Food & Dining"
    assert result["total_spend"] == 200.0
    assert result["transaction_count"] == 1


def test_get_category_spend_resolves_food_alias(
    client, db_session, seeded_finance_data
):
    """"food" resolves to "Food & Dining" via the alias map."""
    uid = seeded_finance_data["user_id"]
    result = get_category_spend(db_session, {"category": "food", "months_back": 0}, uid)
    assert result["category"] == "Food & Dining"
    assert result["total_spend"] == 200.0


def test_get_category_spend_resolves_substring_match(
    client, db_session, seeded_finance_data
):
    """A query not in the alias map still resolves via substring match
    against canonical names ("shopp" is a prefix of "Shopping")."""
    uid = seeded_finance_data["user_id"]
    result = get_category_spend(db_session, {"category": "shopp", "months_back": 0}, uid)
    assert result["category"] == "Shopping"
    assert result["total_spend"] == 800.0
    assert result["transaction_count"] == 1


def test_get_category_spend_missing_param_returns_error(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = get_category_spend(db_session, {}, uid)
    assert "error" in result


# ---------------------------------------------------------------------
# get_merchant_spend
# ---------------------------------------------------------------------

def test_get_merchant_spend_matches_merchant_name(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = get_merchant_spend(db_session, {"merchant": "STARBUCKS", "months_back": 0}, uid)

    assert result["merchant"] == "STARBUCKS"
    assert result["total_spend"] == 200.0
    assert result["transaction_count"] == 1


def test_get_merchant_spend_matches_description(
    client, db_session, seeded_finance_data
):
    """Merchant search also matches description text (SERVICEMAC is in
    the description, not the merchant_name for some bank statement rows)."""
    uid = seeded_finance_data["user_id"]
    result = get_merchant_spend(db_session, {"merchant": "SERVICEMAC", "months_back": 0}, uid)
    assert result["total_spend"] == 300.0
    assert result["transaction_count"] == 1


def test_get_merchant_spend_case_insensitive(client, db_session, seeded_finance_data):
    uid = seeded_finance_data["user_id"]
    result = get_merchant_spend(db_session, {"merchant": "amazon", "months_back": 0}, uid)
    assert result["total_spend"] == 800.0


def test_get_merchant_spend_no_match_returns_zeros(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = get_merchant_spend(db_session, {"merchant": "NONEXISTENT"}, uid)
    assert result["total_spend"] == 0.0
    assert result["transaction_count"] == 0


# ---------------------------------------------------------------------
# get_cash_flow
# ---------------------------------------------------------------------

def test_get_cash_flow_returns_income_expenses_net(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = get_cash_flow(db_session, {"months_back": 0}, uid)

    assert result["income"] == 5000.0
    assert result["expenses"] == 1300.0
    assert result["net_cash_flow"] == 3700.0
    assert result["months_back"] == 0


def test_get_cash_flow_with_no_transactions_returns_zeros(client, db_session):
    result = get_cash_flow(db_session, {"months_back": 0}, 99999)
    assert result["income"] == 0.0
    assert result["expenses"] == 0.0
    assert result["net_cash_flow"] == 0.0


# ---------------------------------------------------------------------
# compute_savings_rate
# ---------------------------------------------------------------------

def test_compute_savings_rate_returns_percentage(
    client, db_session, seeded_finance_data
):
    uid = seeded_finance_data["user_id"]
    result = compute_savings_rate(db_session, {"months_back": 0}, uid)

    assert result["income"] == 5000.0
    assert result["expenses"] == 1300.0
    assert result["net"] == 3700.0
    # (5000 - 1300) / 5000 * 100 = 74.0
    assert result["savings_rate"] == 74.0


def test_compute_savings_rate_zero_income_returns_zero(
    client, db_session
):
    """When income is 0, savings_rate must be 0 (not a division error)."""
    result = compute_savings_rate(db_session, {"months_back": 0}, 99999)
    assert result["savings_rate"] == 0.0
    assert result["income"] == 0.0


def test_compute_savings_rate_negative_net_clamped_to_zero(
    client, db_session, make_account, make_transaction
):
    """When expenses exceed income, savings_rate is clamped to 0 (not negative)."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Test", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    for t in [
        make_transaction(account_id=account.id, description="SMALL PAY", amount=100.0),
        make_transaction(account_id=account.id, description="BIG BILL", amount=-500.0),
    ]:
        db_session.add(t)
    db_session.commit()

    result = compute_savings_rate(db_session, {"months_back": 0}, account.user_id)
    assert result["savings_rate"] == 0.0  # clamped from -400%


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def test_coerce_int_returns_default_for_none():
    assert _coerce_int(None, default=1) == 1


def test_coerce_int_returns_default_for_invalid():
    assert _coerce_int("abc", default=1) == 1


def test_coerce_int_parses_valid_string():
    assert _coerce_int("3", default=1) == 3


def test_month_window_current_month():
    start, end = _month_window(0)
    now = datetime.now(timezone.utc)
    assert start.day == 1
    assert start.month == now.month
    # Compare without microseconds (the two datetime.now() calls are
    # a few microseconds apart, which is fine for a month-window helper).
    assert end.replace(microsecond=0) == now.replace(microsecond=0)


def test_month_window_last_month():
    start, end = _month_window(1)
    now = datetime.now(timezone.utc)
    # end should be the 1st of the current month.
    assert end.day == 1
    assert end.month == now.month
    # start should be the 1st of last month.
    assert start.day == 1
