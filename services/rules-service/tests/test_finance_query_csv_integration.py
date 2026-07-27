"""Phase 30d — Integration tests using the sample CSV statements.

Uses the project's own ``checking_stmt.csv`` and ``savings_stmt.csv``
fixtures (real BofA statement formats) to verify the 30d analysis tools
work end-to-end against data imported from sample documents:

1. Parse the CSVs via the same _load_csv_transactions helper used in
   the 30b integration test.
2. Insert the transactions into the test DB.
3. Run get_trends, compare_periods, detect_anomalies,
   predict_upcoming_bills, and compute_investable_surplus against the
   imported data.
4. Assert the tools return meaningful (non-empty / non-zero) results.

This bridges the gap between the unit tests (seeded fixture data) and
the real-world statement format the user uploads.
"""
import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models import Category, Goal
from app.services.categorizer import seed_default_categories
from app.services.finance_query import (
    compare_periods,
    compute_investable_surplus,
    detect_anomalies,
    get_trends,
    predict_upcoming_bills,
)

_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "sample_statements"
)
_CHECKING_CSV = _FIXTURES_DIR / "checking_stmt.csv"
_SAVINGS_CSV = _FIXTURES_DIR / "savings_stmt.csv"


def _load_csv_transactions(csv_path: Path) -> list[dict]:
    """Load a sample CSV into raw dicts (date, description, amount).

    Handles the multi-section BofA format: a summary section followed by
    a transaction ledger with a ``Date,Description,Amount,Running Bal.``
    header. Falls back to treating the whole file as single-section if
    no ``Date,`` header is found.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()

    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Date,"):
            header_idx = i
            break
    if header_idx is None:
        header_idx = 0

    reader = csv.DictReader(io.StringIO("".join(lines[header_idx:])))
    for row in reader:
        desc = row.get("Description") or ""
        amount_str = row.get("Amount") or "0"
        date_str = row.get("Date") or ""
        try:
            amount = float(amount_str.replace(",", "").replace("$", ""))
        except (ValueError, TypeError):
            continue
        if not desc or amount == 0:
            continue
        # Parse the date (M/D/YYYY format used by BofA statements).
        try:
            dt = datetime.strptime(date_str, "%m/%d/%Y")
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)
        rows.append({
            "description": desc,
            "amount": amount,
            "date": dt.replace(tzinfo=timezone.utc),
        })
    return rows


@pytest.fixture
def seeded_csv_30d_data(client, db_session, make_account, make_transaction, make_goal):
    """Seed the DB with transactions from BOTH sample CSVs, plus a goal.

    Uses the checking_stmt.csv (which has SERVICEMAC mortgage payments,
    Zelle transfers, and various merchant transactions) and
    savings_stmt.csv (which has interest earned, transfers, and Zelle
    payments). Together they provide enough data for the 30d tools to
    produce meaningful results.
    """
    seed_default_categories(db_session)
    db_session.commit()

    # Create a checking + savings account.
    checking = make_account(
        account_name="BofA Checking",
        account_type="checking",
        current_balance=5000.0,
    )
    db_session.add(checking)
    db_session.commit()
    db_session.refresh(checking)

    # Load transactions from both CSVs.
    checking_rows = _load_csv_transactions(_CHECKING_CSV)
    savings_rows = _load_csv_transactions(_SAVINGS_CSV)

    # Insert checking transactions.
    txns = []
    for row in checking_rows:
        t = make_transaction(
            account_id=checking.id,
            description=row["description"],
            amount=row["amount"],
            transaction_date=row["date"],
            merchant_name=None,
        )
        db_session.add(t)
        txns.append(t)

    # Insert savings transactions into the same account for simplicity
    # (the 30d tools query by user_id, not account_id).
    for row in savings_rows:
        t = make_transaction(
            account_id=checking.id,
            description=row["description"],
            amount=row["amount"],
            transaction_date=row["date"],
            merchant_name=None,
        )
        db_session.add(t)
        txns.append(t)

    db_session.commit()

    # Add a goal for the surplus tool.
    goal = make_goal(
        name="Emergency Fund",
        target_amount=60000.0,
        horizon_years=5,
        priority=10,
    )
    db_session.add(goal)
    db_session.commit()

    user_id = checking.user_id
    return {
        "account": checking,
        "user_id": user_id,
        "goal": goal,
        "txn_count": len(txns),
    }


def test_csv_get_trends_returns_non_empty_series(
    client, db_session, seeded_csv_30d_data
):
    """get_trends returns a non-empty trend series from CSV-imported data."""
    uid = seeded_csv_30d_data["user_id"]
    result = get_trends(db_session, {"months": 6}, uid)

    assert "trend" in result
    assert len(result["trend"]) == 6
    # At least one month should have non-zero expenses (the CSVs span
    # multiple months of real transaction data).
    has_expenses = any(t["expenses"] > 0 for t in result["trend"])
    assert has_expenses, (
        "Expected at least one month with non-zero expenses from CSV data"
    )


def test_csv_compare_periods_returns_valid_comparison(
    client, db_session, seeded_csv_30d_data
):
    """compare_periods returns a valid side-by-side comparison from CSV data."""
    uid = seeded_csv_30d_data["user_id"]
    result = compare_periods(db_session, {"period_a": 1, "period_b": 0}, uid)

    assert "period_a" in result
    assert "period_b" in result
    assert "deltas" in result
    assert "percent_changes" in result
    # The structure should be complete even if some values are 0.
    assert "income" in result["period_a"]
    assert "expenses" in result["period_a"]
    assert "income" in result["period_b"]
    assert "expenses" in result["period_b"]


def test_csv_detect_anomalies_runs_without_error(
    client, db_session, seeded_csv_30d_data
):
    """detect_anomalies runs without error on CSV-imported data and
    returns a well-formed result (may be empty if no anomalies exist)."""
    uid = seeded_csv_30d_data["user_id"]
    result = detect_anomalies(
        db_session,
        {"lookback_days": 365, "limit": 20},
        uid,
    )

    assert "anomalies" in result
    assert "count" in result
    assert isinstance(result["anomalies"], list)
    assert result["count"] == len(result["anomalies"])


def test_csv_predict_upcoming_bills_runs_without_error(
    client, db_session, seeded_csv_30d_data
):
    """predict_upcoming_bills runs without error on CSV-imported data.
    May return 0 bills if the sample data doesn't have enough recurring
    patterns within the lookback window."""
    uid = seeded_csv_30d_data["user_id"]
    result = predict_upcoming_bills(
        db_session,
        {"lookback_days": 365, "min_hits": 3},
        uid,
    )

    assert "bills" in result
    assert "count" in result
    assert isinstance(result["bills"], list)
    assert result["count"] == len(result["bills"])
    # If any bills are found, verify the shape.
    for bill in result["bills"]:
        assert "merchant" in bill
        assert "median_amount" in bill
        assert "predicted_next_date" in bill
        assert "confidence" in bill


def test_csv_compute_investable_surplus_with_goal(
    client, db_session, seeded_csv_30d_data
):
    """compute_investable_surplus uses the Goal from the fixture and
    returns a well-formed result from CSV-imported data."""
    uid = seeded_csv_30d_data["user_id"]
    result = compute_investable_surplus(db_session, {"months_back": 0}, uid)

    assert "income" in result
    assert "expenses" in result
    assert "net_cash_flow" in result
    assert "monthly_goal_target" in result
    assert "investable_surplus" in result
    assert result["has_goals"] is True
    assert result["goal_count"] == 1

    # The goal has target_amount=60000, horizon_years=5.
    # Monthly target = 60000 / (5 * 12) = 1000.0
    assert result["monthly_goal_target"] == 1000.0


def test_csv_all_tools_work_on_real_statement_data(
    client, db_session, seeded_csv_30d_data
):
    """Smoke test: all 5 new 30d tools run without error on the combined
    CSV data from both sample statements."""
    uid = seeded_csv_30d_data["user_id"]
    assert seeded_csv_30d_data["txn_count"] > 0, (
        "Expected transactions from the sample CSVs"
    )

    # Run all 5 tools — just verify they don't raise.
    get_trends(db_session, {"months": 3}, uid)
    compare_periods(db_session, {"period_a": 1, "period_b": 0}, uid)
    detect_anomalies(db_session, {}, uid)
    predict_upcoming_bills(db_session, {}, uid)
    compute_investable_surplus(db_session, {}, uid)
    # If we reach here, all 5 tools ran without error.
