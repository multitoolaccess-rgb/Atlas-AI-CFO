"""Phase 30b — Integration test using the sample CSV statement.

Uses the project's own ``checking_stmt.csv`` fixture (which contains
SERVICEMAC mortgage payment rows observed on a real BofA statement) to
verify the categorizer fix + finance_query tools work end-to-end:

1. Parse the CSV via the real import_parser.
2. Categorize the resulting transactions.
3. Assert SERVICEMAC rows are tagged (the bug: they stayed untagged).
4. Run finance_query.get_totals + get_merchant_spend on the seeded data.
"""
import csv
from datetime import datetime
from pathlib import Path

import pytest

from app.models import Category, MerchantRule, Transaction
from app.services.categorizer import (
    build_category_lookup,
    categorize_transactions,
    seed_default_categories,
    seed_default_merchant_rules,
)
from app.services.finance_query import get_merchant_spend, get_totals

# The sample statement lives under the rules-service test fixtures dir.
_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "sample_statements"
)
_CSV_PATH = _FIXTURES_DIR / "checking_stmt.csv"


def _load_csv_transactions(csv_path: Path) -> list[dict]:
    """Load the sample CSV into raw dicts (date, description, amount).

    The sample ``checking_stmt.csv`` has a multi-section format:
      Lines 1-5: Summary section (``Description``, blank, ``Summary Amt.``)
      Line 6:   Empty delimiter
      Line 7+:  Transaction data (``Date``, ``Description``, ``Amount``, ``Running Bal.``)

    We skip the summary section and parse only the transaction rows.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()

    # Find the transaction header row (starts with "Date,").
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Date,"):
            header_idx = i
            break

    if header_idx is None:
        # Fallback: treat the whole file as a single-section CSV.
        header_idx = 0

    # Parse from the transaction header onward.
    import io
    reader = csv.DictReader(io.StringIO("".join(lines[header_idx:])))
    for row in reader:
        desc = row.get("Description") or ""
        amount_str = row.get("Amount") or "0"
        date_str = row.get("Date") or ""
        # Skip empty rows + non-numeric amounts (e.g. "Amount" header echo).
        try:
            amount = float(amount_str.replace(",", "").replace("$", ""))
        except (ValueError, TypeError):
            continue
        if not desc:
            continue
        rows.append({
            "description": desc,
            "amount": amount,
            "date_str": date_str,
        })
    return rows


@pytest.fixture
def seeded_csv_data(client, db_session, make_account, make_transaction):
    """Seed a custom Mortgage category + SERVICEMAC rule, then insert
    a subset of the sample CSV's SERVICEMAC transactions."""
    # Seed defaults.
    seed_default_categories(db_session)
    db_session.commit()
    seed_default_merchant_rules(db_session)

    # Create a custom mortgage category. "Mortgage" is now a default
    # category, so use a distinct name for the custom-category test.
    mortgage_cat = Category(
        name="Custom Mortgage",
        description="Mortgage payments",
        icon="🏠",
        color="#8b5cf6",
    )
    db_session.add(mortgage_cat)
    db_session.commit()
    db_session.refresh(mortgage_cat)

    # Add SERVICEMAC rule pointing to Mortgage.
    rule = MerchantRule(
        category_id=mortgage_cat.id,
        keyword="SERVICEMAC",
        is_archived=False,
        source="manual",
        priority=100,
    )
    db_session.add(rule)
    db_session.commit()

    # Create an account.
    account = make_account(account_name="BofA Checking", account_type="checking")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Load SERVICEMAC rows from the sample CSV.
    csv_rows = _load_csv_transactions(_CSV_PATH)
    servicemac_rows = [r for r in csv_rows if "SERVICEMAC" in r["description"].upper()]

    # Insert up to 3 SERVICEMAC transactions.
    txns = []
    for row in servicemac_rows[:3]:
        t = make_transaction(
            account_id=account.id,
            description=row["description"],
            amount=row["amount"],
            merchant_name=None,
        )
        db_session.add(t)
        txns.append(t)
    db_session.commit()

    return {
        "account": account,
        "user_id": account.user_id,
        "mortgage_cat": mortgage_cat,
        "txn_ids": [t.id for t in txns],
    }


def test_csv_servicemac_transactions_get_tagged_after_categorize(
    client, db_session, seeded_csv_data
):
    """SERVICEMAC rows from the sample CSV must be tagged with the
    custom Mortgage category after categorize_transactions runs."""
    data = seeded_csv_data
    txn_ids = data["txn_ids"]
    assert len(txn_ids) > 0, "Expected at least 1 SERVICEMAC transaction from the CSV"

    # Load the transactions from DB (they were committed in the fixture).
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.id.in_(txn_ids))
        .all()
    )
    # Pre-condition: all untagged.
    for t in txns:
        assert t.category_id is None

    categorized, skipped, _conflicts = categorize_transactions(db_session, txns)
    db_session.commit()

    # All should be categorized (the SERVICEMAC rule + Mortgage category
    # are in the lookup now).
    assert categorized == len(txns), (
        f"Expected {len(txns)} categorized, got {categorized}"
    )

    # Verify they're tagged with the custom mortgage category.
    for txn_id in txn_ids:
        updated = db_session.query(Transaction).filter(
            Transaction.id == txn_id
        ).first()
        assert updated is not None
        assert updated.category_id == data["mortgage_cat"].id, (
            f"Transaction {txn_id} should be tagged with Custom Mortgage, "
            f"got category_id={updated.category_id}"
        )


def test_csv_finance_query_get_totals_works_on_seeded_data(
    client, db_session, seeded_csv_data
):
    """get_totals returns non-zero expenses for the seeded SERVICEMAC data."""
    uid = seeded_csv_data["user_id"]
    result = get_totals(db_session, {}, uid)

    # The SERVICEMAC payments are negative (expenses).
    assert result["total_expenses_month"] > 0, (
        "Expected non-zero expenses from SERVICEMAC transactions"
    )


def test_csv_finance_query_get_merchant_spend_finds_servicemac(
    client, db_session, seeded_csv_data
):
    """get_merchant_spend for 'SERVICEMAC' returns the sum of the
    seeded transactions."""
    uid = seeded_csv_data["user_id"]
    result = get_merchant_spend(
        db_session,
        {"merchant": "SERVICEMAC", "months_back": 0},
        uid,
    )

    assert result["merchant"] == "SERVICEMAC"
    assert result["total_spend"] > 0, (
        "Expected non-zero spend for SERVICEMAC merchant"
    )
    assert result["transaction_count"] > 0
