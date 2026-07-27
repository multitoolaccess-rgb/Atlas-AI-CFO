"""Regression test for the HTTP 500 on POST /parse/upload caused by
non-string tokens reaching the regex matchers in
``extract_pdf_transactions`` / ``_harvest_statement_year``.

Root cause (observed in ``.run/finlynq.log``):

    File ".../import_parser.py", line 1508, in _harvest_statement_year
        m = pattern.search(line)
    TypeError: expected string or bytes-like object, got 'int'

A ``text_lines`` list handed to ``extract_pdf_transactions`` contained
a non-string element (an ``int``), so ``re.Pattern.search`` raised
``TypeError``. The exception bubbled out of the parser, Finlynq
returned HTTP 500, and the rules-service forwarder mapped 5xx → 502
Bad Gateway (the user-visible "Upload error").

Fix: coerce every element to ``str`` before calling ``.strip()`` /
``re.search`` so a stray numeric token from pdfplumber / OCR / a
forwarder can't crash the whole upload.

These tests pin the fix by feeding ``extract_pdf_transactions`` a
``text_lines`` list that contains an ``int`` and a ``float`` and
asserting the function returns normally (no ``TypeError``) and still
extracts the legitimate transaction row.
"""
from app.services.import_parser import (
    _harvest_statement_year,
    extract_pdf_transactions,
)


def test_harvest_statement_year_tolerates_non_string_lines():
    """``_harvest_statement_year`` must not raise when ``text_lines``
    contains non-string tokens; it should coerce and still find the
    statement-period year."""
    text_lines = [
        2026,  # noqa: E501 — non-string token (the regression trigger)
        "Statement Period: April 1, 2026 - April 30, 2026",
        "Some other line",
    ]
    # Must not raise TypeError; should still harvest "2026".
    year = _harvest_statement_year(text_lines)
    assert year == "2026"


def test_extract_pdf_transactions_tolerates_non_string_lines():
    """``extract_pdf_transactions`` must not raise when ``text_lines``
    contains non-string tokens; the legitimate transaction row must
    still be extracted."""
    text_lines = [
        2026,  # non-string token (regression trigger)
        3.14,  # another non-string token
        "04/15 Coffee shop -4.50",
    ]
    records = extract_pdf_transactions(text_lines)
    # Must not raise; the one legitimate line should produce a record.
    assert isinstance(records, list)
    # At least one record with the Coffee description and -4.50 amount.
    coffee = [r for r in records if "Coffee" in (r.get("description") or "")]
    assert coffee, f"expected Coffee record, got {records!r}"
    assert float(coffee[0]["amount"]) == -4.50
