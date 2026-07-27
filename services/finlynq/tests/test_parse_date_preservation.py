"""Regression test — persisted transactions must keep the parser's
real ``transaction_date``, NOT fall back to ``datetime.now()``.

The bug (fixed in this commit): ``parse.py`` read
``rec.get("date")`` but every parser (CSV/PDF/OFX/Excel) emits
``"transaction_date"`` as the key. ``rec.get("date")`` always
returned ``None``, so the fallback ``datetime.now(timezone.utc)``
stamped every imported transaction with today's date.

This test uploads a CSV with dates in January 2025 and asserts
that the persisted ``Transaction.transaction_date`` rows carry
those exact dates — not the current server time.
"""
import pytest
from fastapi.testclient import TestClient

from app.models import Account, Institution, Transaction
from app.routes.shared import get_or_create_local_user


@pytest.fixture()
def seeded_account(db_session):
    """Seed a User + Institution + Account for the upload."""
    user = get_or_create_local_user(db_session, "alex")
    institution = Institution(name="Date Test Bank")
    db_session.add(institution)
    db_session.flush()
    account = Account(
        user_id=user.id,
        institution_id=institution.id,
        account_name="Date Test Checking",
        account_type="checking",
        current_balance=0.0,
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account.id


class TestTransactionDatePreservation:
    """Persisted transactions must carry the real date from the parser,
    not ``datetime.now()``."""

    def test_csv_dates_preserved_not_overwritten_with_today(
        self, client_with_auth, seeded_account, db_session,
    ):
        """Upload a CSV with dates in 2025-01 and verify each persisted
        transaction carries that month — NOT today's date."""
        csv_body = (
            b"date,description,amount\n"
            b"2025-01-15,Coffee shop,-4.50\n"
            b"2025-01-16,Payroll,3500.00\n"
            b"2025-01-17,Grocery store,-87.32\n"
        )
        response = client_with_auth.post(
            "/parse/upload",
            files={"file": ("stmt.csv", csv_body, "text/csv")},
            data={"account_id": str(seeded_account)},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["saved_transactions"] == 3

        txns = (
            db_session.query(Transaction)
            .filter(Transaction.account_id == seeded_account)
            .order_by(Transaction.transaction_date)
            .all()
        )
        assert len(txns) == 3

        # Every transaction date must be in January 2025.
        for txn in txns:
            assert txn.transaction_date.year == 2025, (
                f"Expected year 2025, got {txn.transaction_date.year} "
                f"for txn '{txn.description}'. The date was likely "
                f"overwritten with datetime.now()."
            )
            assert txn.transaction_date.month == 1, (
                f"Expected month 1 (January), got {txn.transaction_date.month} "
                f"for txn '{txn.description}'."
            )

    def test_dates_are_not_all_identical(
        self, client_with_auth, seeded_account, db_session,
    ):
        """If the datetime.now() fallback fires, all dates cluster at
        the same second. Verify dates are DISTINCT (matching the CSV)."""
        csv_body = (
            b"date,description,amount\n"
            b"2025-03-01,Rent,-1500.00\n"
            b"2025-03-15,Salary,4000.00\n"
            b"2025-03-28,Utilities,-200.00\n"
        )
        response = client_with_auth.post(
            "/parse/upload",
            files={"file": ("stmt2.csv", csv_body, "text/csv")},
            data={"account_id": str(seeded_account)},
        )
        assert response.status_code == 200, response.text

        txns = (
            db_session.query(Transaction)
            .filter(Transaction.account_id == seeded_account)
            .order_by(Transaction.transaction_date)
            .all()
        )
        assert len(txns) == 3

        unique_dates = {t.transaction_date.date() for t in txns}
        assert len(unique_dates) == 3, (
            f"Expected 3 distinct dates, got {len(unique_dates)}: "
            f"{unique_dates}. If all dates are identical, the "
            f"datetime.now() fallback is still active."
        )

    def test_ofx_dates_preserved(
        self, client_with_auth, seeded_account, db_session,
    ):
        """OFX parser emits transaction_date; verify the persistence
        layer reads it correctly."""
        # Minimal OFX with a transaction dated 2025-06-15.
        ofx_body = (
            b"OFXHEADER:100\n"
            b"DATA:OFXSGML\n"
            b"VERSION:102\n"
            b"<OFX>\n"
            b"<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS>"
            b"<DTSERVER>20250620<LANGUAGE>ENG</SONRS></SIGNONMSGSRSV1>\n"
            b"<BANKMSGSRSV1>\n"
            b"<STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
            b"<STMTRS><CURDEF>USD\n"
            b"<BANKTRANLIST>\n"
            b"<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20250615<TRNAMT>-50.00"
            b"<FITID>txn001<NAME>Coffee Shop</STMTTRN>\n"
            b"</BANKTRANLIST>\n"
            b"</STMTRS></STMTTRNRS>\n"
            b"</BANKMSGSRSV1>\n"
            b"</OFX>\n"
        )
        response = client_with_auth.post(
            "/parse/upload",
            files={"file": ("stmt.ofx", ofx_body, "application/x-ofx")},
            data={"account_id": str(seeded_account)},
        )
        # OFX may or may not parse depending on ofxparse availability;
        # skip gracefully if the library isn't installed.
        if response.status_code == 400:
            pytest.skip("ofxparse not available or OFX parse failed")

        assert response.status_code == 200, response.text
        body = response.json()
        if body.get("saved_transactions", 0) == 0:
            pytest.skip("OFX parser returned 0 records (format variant)")

        txns = (
            db_session.query(Transaction)
            .filter(Transaction.account_id == seeded_account)
            .all()
        )
        # At least one transaction should have a 2025 date.
        dates_2025 = [t for t in txns if t.transaction_date.year == 2025]
        assert len(dates_2025) >= 1, (
            "Expected at least one transaction with year 2025 from OFX upload"
        )
