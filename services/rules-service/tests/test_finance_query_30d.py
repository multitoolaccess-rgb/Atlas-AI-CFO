"""Phase 30d — Unit tests for the 5 new analysis tools.

Each test seeds accounts + transactions + categories + goals via the
conftest fixtures, then calls a ``finance_query`` function and asserts
the returned dict has the expected shape + values.

Tools tested:
- get_trends — monthly expense trend over N months
- compare_periods — side-by-side comparison of two month windows
- detect_anomalies — flags transactions > 2× the 90-day median per merchant
- predict_upcoming_bills — detects recurring merchants and predicts next due date
- compute_investable_surplus — income - expenses - goal contributions
"""
from datetime import datetime, timedelta, timezone
import sys

import pytest

from app.models import Category, Goal
from app.services import finance_query
from app.services.finance_query import (
    _coerce_float,
    _extract_merchant,
    _is_recurring_interval,
    _median,
    compare_periods,
    compute_investable_surplus,
    detect_anomalies,
    get_trends,
    predict_upcoming_bills,
)
from app.services.categorizer import seed_default_categories


_TEST_NOW = datetime(2026, 8, 1, 18, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def seeded_30d_data(
    client, db_session, make_account, make_transaction, make_goal, monkeypatch
):
    """Seed a user with an account, categories, transactions across
    multiple months, and a goal for the surplus tool.

    Transaction layout:
    - Month 0 (current): +5000 payroll, -200 Starbucks, -800 Amazon, -300 SERVICEMAC
    - Month 1 (last): +5000 payroll, -150 Starbucks, -600 Amazon, -300 SERVICEMAC
    - Month 2: +5000 payroll, -100 Starbucks, -400 Amazon, -300 SERVICEMAC
    - Anomaly: -1500 Starbucks (7.5× the normal ~$150-$200) in month 0

    Recurring merchants:
    - SERVICEMAC: 3 hits, ~30-day intervals → predicted as upcoming bill
    - STARBUCKS: 3+ hits, ~30-day intervals → predicted as upcoming bill
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

    food_cat = db_session.query(Category).filter(Category.name == "Food & Dining").first()
    shopping_cat = db_session.query(Category).filter(Category.name == "Shopping").first()
    bills_cat = db_session.query(Category).filter(Category.name == "Bills & Utilities").first()

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return _TEST_NOW

    # Keep the fixture and finance-query window on one deterministic clock;
    # monkeypatch restores both imported bindings after the test.
    monkeypatch.setattr(finance_query, "datetime", _FrozenDateTime)
    monkeypatch.setattr(sys.modules[__name__], "datetime", _FrozenDateTime)
    now = datetime.now(timezone.utc)
    # Use the 1st of the current month as the anchor for deterministic
    # date placement. All "month 0" transactions are placed on days 2-28
    # of the current month so they're guaranteed to fall within the
    # _month_window(0) range (1st of this month to now).
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Helper to create a date on day N of the month that is M months ago.
    #
    # Phase 2 cert-cycle corrective (branch codex/phase-2-cert-date-boundary-fix):
    # clamp the day so month-0 timestamps are never FUTURE-tense relative
    # to ``now``. Without this clamp the day-2 / day-3 noon-UTC placements
    # were filtered out by ``finance_query._month_window(0)`` whenever
    # ``now.day == 1`` and ``now`` was before noon UTC, collapsing
    # ``compare_periods(period_a=1, period_b=0)``'s ``period_b expenses``
    # to $300 (just the SERVICEMAC on day 1) vs. period_a's $1050 and
    # failing the ``period_b expenses > period_a expenses`` assertion.
    # ``max(1, now.day)`` (NOT ``now.day - 1``) floors the clamp at day 1
    # — it can never become the invalid day 0 — on the first of the month.
    def month_date(months_back, day):
        year = current_month_start.year
        month = current_month_start.month - months_back
        while month <= 0:
            month += 12
            year -= 1
        actual_day = min(day, max(1, now.day))
        return datetime(year, month, actual_day, 12, 0, 0, tzinfo=timezone.utc)

    txns = []

    # Month 0 (current month) — days 1-3 ONLY, guaranteed in the past
    # regardless of what day of the month the test runs on.
    txns.append(make_transaction(
        account_id=account.id, description="MORTGAGE PAYMENT SERVICEMAC", amount=-300.0,
        merchant_name="SERVICEMAC", category_id=bills_cat.id if bills_cat else None,
        transaction_date=month_date(0, 1),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="PAYROLL DEPOSIT", amount=5000.0,
        merchant_name="EMPLOYER", transaction_date=month_date(0, 2),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="STARBUCKS COFFEE", amount=-200.0,
        merchant_name="STARBUCKS", category_id=food_cat.id if food_cat else None,
        transaction_date=month_date(0, 2),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="AMAZON.COM PURCHASE", amount=-800.0,
        merchant_name="AMAZON", category_id=shopping_cat.id if shopping_cat else None,
        transaction_date=month_date(0, 3),
    ))
    # Anomaly: a huge Starbucks charge
    txns.append(make_transaction(
        account_id=account.id, description="STARBUCKS CATERING ORDER", amount=-1500.0,
        merchant_name="STARBUCKS", category_id=food_cat.id if food_cat else None,
        transaction_date=month_date(0, 3),
    ))

    # Month 1 (last month) — SERVICEMAC on day 1 for consistent ~30-day intervals
    txns.append(make_transaction(
        account_id=account.id, description="MORTGAGE PAYMENT SERVICEMAC", amount=-300.0,
        merchant_name="SERVICEMAC", category_id=bills_cat.id if bills_cat else None,
        transaction_date=month_date(1, 1),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="PAYROLL DEPOSIT", amount=5000.0,
        merchant_name="EMPLOYER", transaction_date=month_date(1, 5),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="STARBUCKS COFFEE", amount=-150.0,
        merchant_name="STARBUCKS", category_id=food_cat.id if food_cat else None,
        transaction_date=month_date(1, 10),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="AMAZON.COM PURCHASE", amount=-600.0,
        merchant_name="AMAZON", category_id=shopping_cat.id if shopping_cat else None,
        transaction_date=month_date(1, 15),
    ))

    # Month 2 — SERVICEMAC on day 1 for consistent ~30-day intervals
    txns.append(make_transaction(
        account_id=account.id, description="MORTGAGE PAYMENT SERVICEMAC", amount=-300.0,
        merchant_name="SERVICEMAC", category_id=bills_cat.id if bills_cat else None,
        transaction_date=month_date(2, 1),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="PAYROLL DEPOSIT", amount=5000.0,
        merchant_name="EMPLOYER", transaction_date=month_date(2, 5),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="STARBUCKS COFFEE", amount=-100.0,
        merchant_name="STARBUCKS", category_id=food_cat.id if food_cat else None,
        transaction_date=month_date(2, 10),
    ))
    txns.append(make_transaction(
        account_id=account.id, description="AMAZON.COM PURCHASE", amount=-400.0,
        merchant_name="AMAZON", category_id=shopping_cat.id if shopping_cat else None,
        transaction_date=month_date(2, 15),
    ))

    for t in txns:
        db_session.add(t)
    db_session.commit()

    # Add a goal for the surplus tool.
    goal = make_goal(
        name="Retirement",
        target_amount=120000.0,
        horizon_years=10,
        priority=10,
    )
    db_session.add(goal)
    db_session.commit()

    user_id = account.user_id
    return {"account": account, "user_id": user_id, "goal": goal}


# ---------------------------------------------------------------------
# get_trends
# ---------------------------------------------------------------------

def test_get_trends_returns_monthly_expense_series(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    result = get_trends(db_session, {"months": 3}, uid)

    assert "trend" in result
    assert len(result["trend"]) == 3
    assert "month" in result["trend"][0]
    assert "expenses" in result["trend"][0]
    assert "income" in result["trend"][0]
    assert "net" in result["trend"][0]
    assert result["months"] == 3
    assert result["direction"] in ("increasing", "decreasing", "stable")


def test_get_trends_with_no_data_returns_zeros(client, db_session):
    result = get_trends(db_session, {"months": 6}, 99999)
    assert len(result["trend"]) == 6
    assert all(t["expenses"] == 0.0 for t in result["trend"])
    assert result["direction"] == "stable"


def test_get_trends_clamps_months(client, db_session, seeded_30d_data):
    uid = seeded_30d_data["user_id"]
    # Requesting 100 months should be clamped to 24.
    result = get_trends(db_session, {"months": 100}, uid)
    assert result["months"] == 24
    assert len(result["trend"]) == 24


# ---------------------------------------------------------------------
# compare_periods
# ---------------------------------------------------------------------

def test_compare_periods_returns_both_periods_with_deltas(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    result = compare_periods(db_session, {"period_a": 1, "period_b": 0}, uid)

    assert "period_a" in result
    assert "period_b" in result
    assert "deltas" in result
    assert "percent_changes" in result

    assert result["period_a"]["months_back"] == 1
    assert result["period_b"]["months_back"] == 0

    # Period B (current month) should have higher expenses due to the anomaly.
    assert result["period_b"]["expenses"] > result["period_a"]["expenses"]
    assert result["deltas"]["expenses"] > 0


def test_compare_periods_with_no_data_returns_zeros(client, db_session):
    result = compare_periods(db_session, {}, 99999)
    assert result["period_a"]["income"] == 0.0
    assert result["period_b"]["income"] == 0.0
    assert result["deltas"]["income"] == 0.0
    # Percent change is None when base is 0.
    assert result["percent_changes"]["income"] is None


def test_compare_periods_percent_change_calculation(client, db_session, seeded_30d_data):
    uid = seeded_30d_data["user_id"]
    result = compare_periods(db_session, {"period_a": 2, "period_b": 1}, uid)

    # Month 2 expenses: 100 + 400 + 300 = 800
    # Month 1 expenses: 150 + 600 + 300 = 1050
    # Delta = 1050 - 800 = 250
    # Pct = (1050 - 800) / 800 * 100 = 31.25 → rounded to 31.3
    assert result["deltas"]["expenses"] == 250.0
    assert result["percent_changes"]["expenses"] is not None


# ---------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------

def test_detect_anomalies_flags_large_transactions(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    result = detect_anomalies(db_session, {"lookback_days": 90, "limit": 10}, uid)

    assert "anomalies" in result
    assert "count" in result
    assert result["count"] > 0

    # The -1500 Starbucks should be flagged (it's > 2× the median of
    # the other Starbucks charges which are ~$100-$200).
    starbucks_anomaly = [a for a in result["anomalies"] if "STARBUCKS" in a["merchant"]]
    assert len(starbucks_anomaly) > 0
    assert starbucks_anomaly[0]["amount"] == 1500.0
    assert starbucks_anomaly[0]["multiplier"] >= 2.0


def test_detect_anomalies_with_no_data_returns_empty(client, db_session):
    result = detect_anomalies(db_session, {}, 99999)
    assert result["anomalies"] == []
    assert result["count"] == 0


def test_detect_anomalies_respects_limit(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    result = detect_anomalies(db_session, {"limit": 1}, uid)
    assert len(result["anomalies"]) <= 1


def test_detect_anomalies_respects_threshold(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    # With a very high threshold (10×), the -1500 Starbucks may not be flagged.
    result = detect_anomalies(db_session, {"threshold_multiplier": 100.0}, uid)
    # The -1500 is 7.5× the median of ~$175, so with 100× it should NOT be flagged.
    assert all(a["multiplier"] >= 100.0 for a in result["anomalies"])


# ---------------------------------------------------------------------
# predict_upcoming_bills
# ---------------------------------------------------------------------

def test_predict_upcoming_bills_detects_recurring_merchants(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    result = predict_upcoming_bills(db_session, {"lookback_days": 180, "min_hits": 3}, uid)

    assert "bills" in result
    assert "count" in result
    assert result["count"] > 0

    # SERVICEMAC appears 3 times at ~30-day intervals → should be predicted.
    servicemac_bills = [b for b in result["bills"] if "SERVICEMAC" in b["merchant"]]
    assert len(servicemac_bills) > 0
    assert servicemac_bills[0]["median_amount"] == 300.0
    assert "predicted_next_date" in servicemac_bills[0]
    assert "confidence" in servicemac_bills[0]


def test_predict_upcoming_bills_with_no_data_returns_empty(client, db_session):
    result = predict_upcoming_bills(db_session, {}, 99999)
    assert result["bills"] == []
    assert result["count"] == 0


def test_predict_upcoming_bills_respects_min_hits(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    # With min_hits=10, no merchant has enough hits.
    result = predict_upcoming_bills(db_session, {"min_hits": 10}, uid)
    assert result["count"] == 0


# ---------------------------------------------------------------------
# compute_investable_surplus
# ---------------------------------------------------------------------

def test_compute_investable_surplus_with_goal(
    client, db_session, seeded_30d_data
):
    uid = seeded_30d_data["user_id"]
    result = compute_investable_surplus(db_session, {"months_back": 0}, uid)

    assert "income" in result
    assert "expenses" in result
    assert "net_cash_flow" in result
    assert "monthly_goal_target" in result
    assert "investable_surplus" in result
    assert result["has_goals"] is True
    assert result["goal_count"] == 1

    # The goal has target_amount=120000, horizon_years=10.
    # Monthly target = 120000 / (10 * 12) = 1000.0
    assert result["monthly_goal_target"] == 1000.0

    # Income = 5000, Expenses = 200 + 800 + 300 + 1500 = 2800
    # Net = 5000 - 2800 = 2200
    # Surplus = 2200 - 1000 = 1200
    assert result["income"] == 5000.0
    assert result["expenses"] == 2800.0
    assert result["net_cash_flow"] == 2200.0
    assert result["investable_surplus"] == 1200.0


def test_compute_investable_surplus_without_goals(
    client, db_session, make_account, make_transaction
):
    """Without goals, monthly_goal_target is 0 and surplus = net cash flow."""
    seed_default_categories(db_session)
    db_session.commit()
    account = make_account(account_name="Test", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    t = make_transaction(
        account_id=account.id, description="PAYROLL", amount=3000.0,
        transaction_date=datetime.now(timezone.utc),
    )
    db_session.add(t)
    db_session.commit()

    result = compute_investable_surplus(db_session, {"months_back": 0}, account.user_id)
    assert result["has_goals"] is False
    assert result["goal_count"] == 0
    assert result["monthly_goal_target"] == 0.0
    assert result["investable_surplus"] == result["net_cash_flow"]


def test_compute_investable_surplus_with_no_data_returns_zeros(client, db_session):
    result = compute_investable_surplus(db_session, {}, 99999)
    assert result["income"] == 0.0
    assert result["expenses"] == 0.0
    assert result["net_cash_flow"] == 0.0
    assert result["monthly_goal_target"] == 0.0
    assert result["investable_surplus"] == 0.0
    assert result["has_goals"] is False


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------

def test_median_odd_length():
    assert _median([1.0, 3.0, 5.0]) == 3.0


def test_median_even_length():
    assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_median_empty_returns_zero():
    assert _median([]) == 0.0


def test_median_single_element():
    assert _median([42.0]) == 42.0


def test_extract_merchant_from_description():
    # _extract_merchant takes the first 3 words as a grouping key.
    assert _extract_merchant("STARBUCKS STORE #123") == "STARBUCKS STORE #123"
    assert _extract_merchant("AMAZON") == "AMAZON"
    assert _extract_merchant(None) is None
    assert _extract_merchant("") is None
    assert _extract_merchant("  ") is None


def test_is_recurring_interval_monthly():
    # ~30 day intervals
    assert _is_recurring_interval([30, 31, 29, 30]) is True


def test_is_recurring_interval_weekly():
    # ~7 day intervals
    assert _is_recurring_interval([7, 7, 8, 6]) is True


def test_is_recurring_interval_irregular():
    # Wildly varying intervals → not recurring.
    # Use intervals whose median doesn't match any known cycle.
    # median of [3, 50, 100, 120] = 75, not near 7/14/30/90.
    # CV is high and max_ratio is high → rejected.
    assert _is_recurring_interval([3, 50, 100, 120]) is False


def test_is_recurring_interval_empty():
    assert _is_recurring_interval([]) is False


def test_is_recurring_interval_consistent_non_standard():
    # Consistent 20-day intervals (not a known cycle but very consistent)
    assert _is_recurring_interval([20, 20, 20, 20]) is True


def test_coerce_float_returns_default_for_none():
    assert _coerce_float(None, default=2.0) == 2.0


def test_coerce_float_returns_default_for_invalid():
    assert _coerce_float("abc", default=2.0) == 2.0


def test_coerce_float_parses_valid_string():
    assert _coerce_float("3.5", default=2.0) == 3.5


def test_coerce_float_parses_int():
    assert _coerce_float(5, default=2.0) == 5.0


# ---------------------------------------------------------------------
# Phase 2 cert-cycle corrective regression: 1st-of-month date boundary.
#
# PR #22 cheap CI failed on 2026-08-01 because ``seeded_30d_data``
# placed month-0 transactions at noon UTC on day 2 / day 3 of the
# current month — future-tense whenever pytest's now() was on day 1
# of the month before noon UTC — and ``finance_query._month_window(0)``
# filtered them out as ``transaction_date > now``. The corrected clamp
# above (``actual_day = min(day, max(1, now.day))``) keeps the day
# placements unchanged for any now.day >= the requested day, and
# folds them to day 1 specifically on the first of the month. The
# regression below proves the boundary cannot recur.
# ---------------------------------------------------------------------
def test_seeded_30d_first_of_month_determinism(
    db_session, client, make_account, make_transaction, make_goal, monkeypatch
):
    """Simulate 2026-08-01 18:00 UTC — past noon UTC so the noon-UTC
    day-1 timestamp is in the past under the corrected clamp — and
    prove the date-boundary wedge cannot recur.

    Controls the clock by patching ``datetime.datetime.now`` (the
    canonical Python clock) so BOTH the fixture helper ``month_date``
    AND the production ``app.services.finance_query._month_window``
    read the SAME simulated instant in time. Asserts:

    1. Every month-0 ``transaction_date`` is no later than the
       simulated now — a TIMESTAMP assertion, not a count-only check;
       the expected five month-0 rows are also counted explicitly.
    2. The financial totals match the existing pre-fix contract
       pinned by ``test_compute_investable_surplus_with_goal``
       (income 5000.0, expenses 2800.0, net 2200.0, monthly goal
       target 1000.0, investable surplus 1200.0).
    3. The previously failing complete-suite assertion in
       ``test_compare_periods_returns_both_periods_with_deltas``
       — ``period_b expenses > period_a expenses`` — PASSES under
       the patched clock without any change to production code.

    Note: ``client`` is requested solely so its fixture body invokes
    ``_reset_test_db()`` — the TestClient itself is unused. ``Transaction``
    is imported locally (rather than added at module level) so the
    regression stays self-contained and doesn't widen the file's
    surface area beyond what the existing tests required.
    """
    from app.models import Transaction
    from app.services import finance_query

    # 2026-08-01 18:00 UTC — past noon UTC so the noon-UTC day-1
    # timestamp is strictly in the past on the first of the month.
    # 2026-08-01 18:00 UTC — past noon UTC so the noon-UTC day-1
    # timestamp is strictly in the past on the first of the month
    # under the corrected clamp above.
    fake_now = datetime(2026, 8, 1, 18, 0, 0, tzinfo=timezone.utc)

    # CPython's built-in ``datetime.datetime`` is C-implemented and
    # immutable, so ``unittest.mock.patch.object(datetime, "now", ...)``
    # raises ``TypeError: cannot set 'now' attribute of immutable type``.
    # We subclass instead and substitute the imported ``datetime``
    # binding in BOTH consumer modules' namespaces — both consumers'
    # ``datetime.now(timezone.utc)`` calls then route through the
    # subclass and return ``fake_now``. pytest's ``monkeypatch.context``
    # reverts both bindings on context exit.
    with monkeypatch.context() as _mp:
        class _FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now

        _mp.setattr(finance_query, "datetime", _FrozenDateTime)
        # Patch the test module's own ``datetime`` binding so the
        # inline-shadowed ``month_date`` inside this test reads the
        # same clock as ``finance_query._month_window``.
        import sys as _sys
        _mp.setattr(_sys.modules[__name__], "datetime", _FrozenDateTime)

        seed_default_categories(db_session)
        db_session.commit()
        account = make_account(
            account_name="Regression-Day-1",
            account_type="checking",
            current_balance=10000.0,
        )
        db_session.add(account)
        db_session.commit()
        db_session.refresh(account)
        food_cat = db_session.query(Category).filter(
            Category.name == "Food & Dining"
        ).first()
        shopping_cat = db_session.query(Category).filter(
            Category.name == "Shopping"
        ).first()
        bills_cat = db_session.query(Category).filter(
            Category.name == "Bills & Utilities"
        ).first()

        # Mirror ``seeded_30d_data``'s date construction under the
        # patched clock so the assertions live one level down from
        # a count-only check. The clamp below is the SAME one the
        # @pytest.fixture applies — the two MUST stay in lockstep.
        now = datetime.now(timezone.utc)  # patched → fake_now
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        def month_date(months_back, day):
            year = current_month_start.year
            month = current_month_start.month - months_back
            while month <= 0:
                month += 12
                year -= 1
            actual_day = min(day, max(1, now.day))
            return datetime(
                year, month, actual_day, 12, 0, 0, tzinfo=timezone.utc
            )

        txns = []
        txns.append(make_transaction(
            account_id=account.id,
            description="MORTGAGE PAYMENT SERVICEMAC",
            amount=-300.0,
            merchant_name="SERVICEMAC",
            category_id=bills_cat.id if bills_cat else None,
            transaction_date=month_date(0, 1),
        ))
        txns.append(make_transaction(
            account_id=account.id,
            description="PAYROLL DEPOSIT",
            amount=5000.0,
            merchant_name="EMPLOYER",
            transaction_date=month_date(0, 2),
        ))
        txns.append(make_transaction(
            account_id=account.id,
            description="STARBUCKS COFFEE",
            amount=-200.0,
            merchant_name="STARBUCKS",
            category_id=food_cat.id if food_cat else None,
            transaction_date=month_date(0, 2),
        ))
        txns.append(make_transaction(
            account_id=account.id,
            description="AMAZON.COM PURCHASE",
            amount=-800.0,
            merchant_name="AMAZON",
            category_id=shopping_cat.id if shopping_cat else None,
            transaction_date=month_date(0, 3),
        ))
        txns.append(make_transaction(
            account_id=account.id,
            description="STARBUCKS CATERING ORDER",
            amount=-1500.0,
            merchant_name="STARBUCKS",
            category_id=food_cat.id if food_cat else None,
            transaction_date=month_date(0, 3),
        ))
        for t in txns:
            db_session.add(t)
        db_session.commit()

        # RETRIEVE the freshly-persisted timestamps (not the
        # in-memory ones above) so the assertion is on what the
        # database actually stored. SQLite may return tz-naive
        # datetimes; normalise to UTC before comparing to fake_now.
        stored = (
            db_session.query(Transaction)
            .filter(Transaction.account_id == account.id)
            .all()
        )
        # (1) TIMESTAMP ASSERTION — all five expected month-0 rows are
        # present, and every transaction_date is no later than fake_now.
        assert len(stored) == 5
        for t in stored:
            txn_date = t.transaction_date
            if txn_date.tzinfo is None:
                txn_date = txn_date.replace(tzinfo=timezone.utc)
            assert txn_date <= fake_now, (
                f"month-0 tx at {txn_date.isoformat()} is FUTURE-tense "
                f"relative to fake_now={fake_now.isoformat()}"
            )

        # (2) FINANCIAL TOTALS — match the pre-fix contract pinned
        # by test_compute_investable_surplus_with_goal.
        goal = make_goal(
            name="Retirement",
            target_amount=120000.0,
            horizon_years=10,
            priority=10,
        )
        db_session.add(goal)
        db_session.commit()
        surplus_result = finance_query.compute_investable_surplus(
            db_session, {"months_back": 0}, account.user_id
        )
        assert surplus_result["income"] == 5000.0, (
            f"income drifted from 5000.0 to {surplus_result['income']!r}"
        )
        assert surplus_result["expenses"] == 2800.0, (
            f"expenses drifted from 2800.0 to {surplus_result['expenses']!r}"
        )
        assert surplus_result["net_cash_flow"] == 2200.0
        assert surplus_result["monthly_goal_target"] == 1000.0
        assert surplus_result["investable_surplus"] == 1200.0

        # (3) PREVIOUSLY FAILING COMPLETE-SUITE TEST — the exact
        # assertion ``test_compare_periods_returns_both_periods_with_deltas``
        # made on 2026-08-01 in cheap CI. It now PASSES under the
        # patched clock without any production-code change.
        cp = finance_query.compare_periods(
            db_session, {"period_a": 1, "period_b": 0}, account.user_id
        )
        assert cp["period_a"]["months_back"] == 1
        assert cp["period_b"]["months_back"] == 0
        assert cp["period_b"]["expenses"] > cp["period_a"]["expenses"], (
            f"date-flake regressed: period_b expenses "
            f"{cp['period_b']['expenses']!r} <= period_a expenses "
            f"{cp['period_a']['expenses']!r}"
        )
        assert cp["deltas"]["expenses"] > 0
