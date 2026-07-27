"""Regression test for comma-separated and dollar-sign formatted amounts.

The root cause of 34 missing payroll deposit rows was that
``_drop_malformed_rows`` used ``pd.to_numeric(errors='coerce')`` which
returns NaN for amounts like ``$2,500.00`` or ``2,500.00``, while the
per-row ``_parse_amount`` strips commas (and now also ``$``) before
parsing. This test locks the fix so the bulk filter and the per-row
parser stay in sync.
"""

import io

import pandas as pd
import pytest
from fastapi import UploadFile

from app.services.import_parser import (
    _coerce_amount_or_zero,
    _drop_malformed_rows,
    _parse_amount,
    parse_csv_transactions,
)


# ── _parse_amount ──────────────────────────────────────────────────


class TestParseAmountDollarAndComma:
    """_parse_amount must strip both commas and $ before float()."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("$2,500.00", 2500.0),
            ("1,234.56", 1234.56),
            ("$500", 500.0),
            ("-$1,000.50", -1000.50),
            ("$0.99", 0.99),
            ("1234", 1234.0),
            (2500, 2500.0),
            (2500.50, 2500.50),
        ],
    )
    def test_parses_cleanly(self, raw, expected):
        assert _parse_amount(raw) == pytest.approx(expected)

    def test_blank_raises(self):
        with pytest.raises(ValueError, match="blank"):
            _parse_amount("")

    def test_dollar_only_raises(self):
        with pytest.raises(ValueError):
            _parse_amount("$")


# ── _coerce_amount_or_zero ─────────────────────────────────────────


class TestCoerceDollarAndComma:
    """_coerce_amount_or_zero must also strip $ and commas."""

    def test_dollar_comma(self):
        assert _coerce_amount_or_zero("$3,000.00") == pytest.approx(3000.0)

    def test_comma_only(self):
        assert _coerce_amount_or_zero("1,234") == pytest.approx(1234.0)

    def test_none_is_zero(self):
        assert _coerce_amount_or_zero(None) == 0.0

    def test_nan_is_zero(self):
        assert _coerce_amount_or_zero(pd.na if hasattr(pd, "na") else float("nan")) == 0.0


# ── _drop_malformed_rows ───────────────────────────────────────────


class TestDropMalformedRowsDollarSign:
    """_drop_malformed_rows must NOT drop rows whose amounts contain
    commas or dollar signs (the exact bug that killed 34 payroll rows)."""

    def test_single_amount_column_with_dollar_commas(self):
        df = pd.DataFrame(
            {
                "date": ["01/15/2025", "01/16/2025", "01/17/2025"],
                "description": ["Payroll", "Coffee", "Rent"],
                "amount": ["$2,500.00", "4.50", "-$1,500.00"],
            }
        )
        column_map = {"date": "date", "description": "description", "amount": "amount"}
        filtered, dropped = _drop_malformed_rows(df, column_map)
        assert len(filtered) == 3, f"Expected 3 rows, got {len(filtered)} (dropped={dropped})"
        assert dropped == 0

    def test_split_amount_with_dollar_commas(self):
        df = pd.DataFrame(
            {
                "date": ["01/15/2025", "01/16/2025", "01/17/2025"],
                "description": ["Payroll", "Coffee", "Rent"],
                "credit": ["$2,500.00", "", ""],
                "debit": ["", "$4.50", "$1,500.00"],
            }
        )
        column_map = {
            "date": "date",
            "description": "description",
            "credit": "credit",
            "debit": "debit",
        }
        filtered, dropped = _drop_malformed_rows(df, column_map)
        assert len(filtered) == 3
        assert dropped == 0

    def test_garbage_still_dropped(self):
        """Rows with truly unparseable amounts (not just formatted) must still drop."""
        df = pd.DataFrame(
            {
                "date": ["01/15/2025", "01/16/2025"],
                "description": ["A", "B"],
                "amount": ["abc", "N/A"],
            }
        )
        column_map = {"date": "date", "description": "description", "amount": "amount"}
        filtered, dropped = _drop_malformed_rows(df, column_map)
        assert len(filtered) == 0
        assert dropped == 2


# ── End-to-end: parse_csv_transactions ─────────────────────────────


def _make_upload(csv_text: str, filename: str = "test.csv") -> UploadFile:
    """Build a minimal UploadFile from a CSV string."""
    return UploadFile(
        filename=filename,
        file=io.BytesIO(csv_text.encode("utf-8")),
    )


class TestParseCsvTransactionsDollarSigns:
    """End-to-end: parse_csv_transactions must persist all rows
    including those with $2,500.00-style amounts."""

    def test_payroll_deposits_not_dropped(self):
        # Amounts with commas MUST be quoted in CSV — otherwise pandas
        # splits on the comma inside "$2,500.00" and misaligns columns.
        csv_text = (
            'Date,Description,Amount\n'
            '01/15/2025,AT&T SERVICES DES:PAYROLL ID,"$2,500.00"\n'
            '01/16/2025,AT&T SERVICES DES:PAYROLL ID,"$2,500.00"\n'
            '01/17/2025,STARBUCKS,4.50\n'
            '01/18/2025,RENT PAYMENT,"-$1,500.00"\n'
        )
        upload = _make_upload(csv_text)
        records = parse_csv_transactions(upload)
        assert len(records) == 4, f"Expected 4, got {len(records)}"

        # Payroll deposits should parse as positive $2,500
        payrolls = [r for r in records if "PAYROLL" in r["description"]]
        assert len(payrolls) == 2
        for r in payrolls:
            assert r["amount"] == pytest.approx(2500.0)

        # Rent should parse as negative
        rent = [r for r in records if "RENT" in r["description"]]
        assert len(rent) == 1
        assert rent[0]["amount"] == pytest.approx(-1500.0)

    def test_split_amount_with_dollar_commas_e2e(self):
        # Commas inside amounts MUST be quoted so pandas doesn't split on them.
        csv_text = (
            'Date,Description,Credit,Debit\n'
            '01/15/2025,AT&T PAYROLL,"$2,500.00",\n'
            '01/16/2025,COFFEE,,"$4.50"\n'
        )
        upload = _make_upload(csv_text)
        records = parse_csv_transactions(upload)
        assert len(records) == 2
        assert records[0]["amount"] == pytest.approx(2500.0)
        assert records[1]["amount"] == pytest.approx(-4.50)
