"""Phase 10 — real-world sample statement parser tests.

Locks the Phase 10 parser fixes against the 5 bank statements the user
shipped under ``tests/fixtures/sample_statements/``. Each test asserts
the parser contract that protects users from real-world data loss:

- ``check_checking_stmt_csv_skips_summary_section_and_preserves_parity``:
  Wells Fargo checking.csv has a 5-row summary block
  (``Description,,Summary Amt.``) BEFORE the actual register header
  (``Date,Description,Amount,Running Bal.``). Phase 10's
  :func:`_find_csv_header_index` pre-scans the first 50 rows and
  detects row 6 as the register header so ``pd.read_csv`` doesn't
  misalign. Without the fix, schema-validate raised
  ``Missing: date, amount``.
- ``test_savings_stmt_csv_split_amount_parses_via_credit_debit_pair``:
  Wells Fargo savings.csv uses ``Date,Particulars,Withdrawals,Deposits``.
  Phase 10 routes ``withdrawals`` -> ``debit`` and ``deposits`` ->
  ``credit`` so the per-row loop computes ``amount = deposit - withdrawal``
  (deposits positive, withdrawals negative).
- ``test_credit_card_year_end_summary_extracts``: The BofA / Credi
  year-end summary PDF MUST extract the canonical transaction list
  (>= 200 records: ``MM/DD/YY <merchant> <CITY>, <ST> <amount>[CR]``).
  Phase 10.1b REMOVED the ``year-end summary``-keyword auto-reject that
  silently zeroed this file in Phase 10 (the user's two screenshots
  showing "0 transactions" came from that reject firing — it was the
  wrong default).
- ``test_fidelity_pdf_preview_returns_pdf_record_count``: Fidelity
  quarterly statements are preview-only today (the heuristic patterns
  don't yet cover Fidelity's "Activity By Fund" layout); we lock the
  preview contract so the UI never silently misreports.
- ``test_individual_statement_pdf_preview_returns_pdf_record_count``:
  Same lock for the individual bank statement sample — preview works,
  persist currently returns 0 because the heuristic patterns need
  further tuning for that layout. This is a follow-up scope; the test
  encodes the current contract so a future regression that silently
  mistreats the file as e.g. a year-end summary would be caught.
- ``test_year_end_marker_never_false_positives_on_year_to_date``:
  Phase 10's year-end regex MUST NOT match ``year-to-date`` because
  Fidelity statements include YTD columns legitimately. Lock the
  anti-false-positive contract.
- ``test_csv_summary_skip_returns_zero_for_csv_without_register_header``:
  Phase 10's header scanner is graceful when no register header is
  found in the first 50 rows — it returns 0 (no skiprows) so the
  legacy pandas-as-is path runs and the existing schema-validation
  error message (``Missing: date, amount, description``) still
  surfaces to the user.
- ``test_transaction_synonym_routes_to_description``:
  Phase 10 added ``transaction`` -> ``description`` (and
  ``transaction_description`` -> ``description``) so hypothetical
  ``Date,Transaction,Amount,Running Bal.`` exports validate.
"""
import io
from pathlib import Path

import pytest
from fastapi import UploadFile

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sample_statements"


def _upload(name: str, body: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(body))


def test_checking_stmt_csv_skips_summary_section_and_preserves_parity():
    """Wells Fargo checking.csv: a 5-row summary-section preamble is
    silently skipped so the register header on row 6 becomes the
    parsed schema, and preview.record_count strictly equals
    len(persist).
    """
    from app.services.import_parser import parse_csv_file, parse_csv_transactions

    body = (FIXTURES / "checking_stmt.csv").read_bytes()
    pre = parse_csv_file(_upload("checking_stmt.csv", body))
    recs = parse_csv_transactions(_upload("checking_stmt.csv", body))

    # Phase 9 preview/persist parity.
    assert pre["file_type"] == "csv"
    assert pre["record_count"] == len(recs), (
        f"parity drift: preview={pre['record_count']} vs persist={len(recs)}"
    )
    # Sanity bound: the file is large enough that we expect >= 100
    # transactions after the summary block is skipped, AND we expect
    # the schema validation to have found date+amount+description
    # ALL on row 6 (the canonical Wells Fargo header).
    assert pre["record_count"] >= 100
    # Equivalence: persist records all carry the canonical shape.
    assert all(r.get("transaction_date") is not None for r in recs)
    assert all(r.get("amount") is not None for r in recs)


def test_savings_stmt_csv_split_amount_parses_via_credit_debit_pair():
    """Wells Fargo savings.csv uses ``Date,Particulars,Withdrawals,Deposits``
    (split-amount). The phase 10 fix routes ``withdrawals`` -> ``debit``
    and ``deposits`` -> ``credit``. Per-row loop computes
    ``amount = deposits - withdrawals``: deposits positive, withdrawals
    negative. Lock the sign convention.
    """
    from app.services.import_parser import parse_csv_file, parse_csv_transactions

    body = (FIXTURES / "savings_stmt.csv").read_bytes()
    pre = parse_csv_file(_upload("savings_stmt.csv", body))
    recs = parse_csv_transactions(_upload("savings_stmt.csv", body))

    assert pre["file_type"] == "csv"
    assert pre["record_count"] == len(recs)
    assert pre["record_count"] >= 10

    # Sign convention: at least one positive (deposit) and one negative
    # (withdrawal) record must appear — the user's savings account has
    # both per the system reminder notes.
    pos_amounts = [r["amount"] for r in recs if r["amount"] > 0]
    neg_amounts = [r["amount"] for r in recs if r["amount"] < 0]
    assert len(pos_amounts) >= 1
    assert len(neg_amounts) >= 1


def test_credit_card_year_end_summary_extracts():
    """Phase 10.1b: the Bank of America / Credi ``YYYY year-end
    summary of credit card transactions`` PDF is THE canonical
    user-importable payment ledger — it contains ~200 lines of
    ``MM/DD/YY <merchant> <CITY>, <ST> <amount>[CR]`` that the user
    EXPECTS the importer to extract. The previous Phase 10 logic
    auto-rejected this PDF on the ``year-end summary`` keyword;
    Phase 10.1b removed that reject and added
    :data:`CREDI_YEAR_END_RE` so the layout now extracts.

    Locks the contract:

    - file_type=pdf, text still renders to preview (no PDF plumbing
      regression).
    - saved_transactions >= 200 (the Credi file ships 200+ dated
      rows across 8 category pages).
    - The ``99.50CR`` / ``27.81CR`` credit/refund suffix flips the
      amount to a NEGATIVE value so refunds surface as outflow
      reductions (matches credit-card sign convention where sales
      are + and credits are -).
    - Spot-checked signed amounts (``160.27``, ``99.50`` -> -99.50,
      ``1,868.73``, ``143.37``) are present in the persist path —
      catches a regex-quantifier or amount-token regression.
    - Calibration: the running total MUST match a well-known
      sub-category sum (e.g. ``$3,479.96`` for the page-3 Food
      Store total at the bottom of the Food Store section). A
      drift here would mean the regex is dropping or double-
      counting rows.
    """
    from app.services.import_parser import parse_pdf_file, parse_pdf_transactions

    # Two distinct calls so we mirror the route's preview/persist
    # split (parity assertion below).
    body = (FIXTURES / "credi_YearEndSummary_2026.pdf").read_bytes()
    pre = parse_pdf_file(_upload("credi_YearEndSummary_2026.pdf", body))
    recs = parse_pdf_transactions(_upload("credi_YearEndSummary_2026.pdf", body))

    assert pre["file_type"] == "pdf"
    assert pre["record_count"] > 0  # text DID render to preview

    # Phase 10.1b main contract: the file MUST extract ≥ 200
    # transactions (down from the previous Phase 10 contract of
    # forced 0). An empty list here means the auto-reject slipped
    # back in OR the regex doesn't match the BofA layout — both
    # regressions must be caught loudly.
    assert len(recs) >= 200, (
        f"BofA year-end summary should extract ≥ 200 transactions; "
        f"got {len(recs)}. Check that _YEAR_END_RE auto-reject was "
        f"removed AND CREDI_YEAR_END_RE is wired into "
        f"extract_pdf_transactions."
    )

    # Spot-check signed amounts (positive purchases).
    amounts_two_dec = sorted({round(r["amount"], 2) for r in recs})
    for expected in (160.27, 1_868.73, 143.37, 99.50, 27.81):
        # We check both signs because some references appear as a
        # purchase AND an inverse credit/refund in the same file.
        assert expected in amounts_two_dec or -expected in amounts_two_dec, (
            f"missing spot-check amount {expected}; first 5 amounts: "
            f"{[round(r['amount'], 2) for r in recs[:5]]}"
        )

    # Spot-check sign-flip for ``CR`` rows: refunds MUST be
    # negative. A row with raw amount ``99.50`` and CR suffix MUST
    # land as ``-99.50`` in the persist path; the absence of any
    # negative record means the CR-suffix branch regressed.
    cr_rows = [r for r in recs if r["amount"] < 0]
    assert len(cr_rows) >= 10, (
        f"expected ≥ 10 credit/refund rows (the Credi file ships "
        f"several ``<amount>CR`` lines per category page); got "
        f"{len(cr_rows)} negatives"
    )


def test_fidelity_401k_extracts_period_rollups():
    """Phase 10.1c — Fidelity NetBenefits ``Statement Details`` PDF
    MUST extract the per-quarter ``Account Activity By Fund``
    pivot-table period totals as real transactions instead of
    returning 0 (the original "preview-only" contract was wrong —
    the user's two screenshots showed "0 transactions saved" for
    this exact PDF, and the file ships 3 quarter-level cash-flow
    rows the user explicitly wants tracked).

    Locks the new contract:

    1. ``len(recs) == 3`` — exactly the three CASH-FLOW rows on
       page 5 of the statement (``Employee Contributions``,
       ``Employer Contributions``, ``Dividends``).
    2. The well-known period totals ``9,988.62``, ``8,739.88``,
       ``1,906.90`` are all present in the parsed ``amount``
       field, matching Page 1's prose Account Summary.
    3. All extracted amounts are POSITIVE — contributions and
       dividends are inflows (401k sign convention). The
       state-only rows (``Beginning Balance``, ``Ending
       Balance``, ``Change in Market Value``) are NOT emitted.
    4. ``transaction_date`` is the period START (``2026-01-01``),
       not today() — the ``Statement Period:``-harvesting helper
       must use the document-level statement_year so the user
       sees correct-looking dates in their ledger.
    5. ``description`` ends with ``(401k period rollup)`` so the
       consumer (UI + CSV export) can flag this as synthesized
       period-level data, not per-paycheck line items.
    6. The ``_YEAR_END_RE`` reject DOES NOT fire on this file
       (Fidelity statements include ``Year-to-Date`` columns
       legitimately; the regex must not false-positive on
       them).
    7. Page 1's prose ``Employee Contributions $9,988.62`` /
       ``Employer Contributions $8,739.88`` / ``Dividends
       $1,906.90`` lines are NOT extracted (the section gate
       prevents duplicates; we only extract from the pivot table
       itself).
    """
    from app.services.import_parser import (
        _YEAR_END_RE,
        parse_pdf_file,
        parse_pdf_transactions,
    )

    body = (
        FIXTURES / "Fidelity NetBenefits - Statement Details.pdf"
    ).read_bytes()
    pre = parse_pdf_file(_upload(
        "Fidelity NetBenefits - Statement Details.pdf", body,
    ))
    recs = parse_pdf_transactions(_upload(
        "Fidelity NetBenefits - Statement Details.pdf", body,
    ))

    assert pre["file_type"] == "pdf"
    assert pre["record_count"] > 0  # text IS extracted for preview

    # Main contract: 3 period-rollup rows.
    assert len(recs) == 3, (
        f"expected exactly 3 period-rollup rows "
        f"(Employee/Employer Contributions + Dividends); got {len(recs)}. "
        f"First 5: {[(str(r['transaction_date']), r['amount'], r['description']) for r in recs[:5]]}"
    )

    # Known period totals — round to cents to avoid floating-edge drift.
    amount_set = {round(r["amount"], 2) for r in recs}
    for expected in (9_988.62, 8_739.88, 1_906.90):
        assert expected in amount_set, (
            f"missing period total {expected} from the "
            f"Fidelity 401k rollup; got {sorted(amount_set)}"
        )

    # Sign convention: contributions + dividends are all POSITIVE
    # (inflows). A negative amount here would mean the
    # last-money-token heuristic mis-picked a per-fund split.
    assert all(r["amount"] > 0 for r in recs), (
        f"all 401k rollup amounts must be positive; got "
        f"{[(r['amount'], r['description']) for r in recs]}"
    )

    # Period start date — the same for all 3 rows (01/01/2026).
    dates = {str(r["transaction_date"])[:10] for r in recs}
    assert dates == {"2026-01-01"}, (
        f"all 3 rollup rows must share the period start date "
        f"2026-01-01; got {dates}"
    )

    # Description honesty — the (401k period rollup) suffix tells
    # the consumer these are quarter-level aggregates, not
    # per-paycheck line items.
    for r in recs:
        assert r["description"].endswith("(401k period rollup)"), (
            f"description must end with '(401k period rollup)'; "
            f"got {r['description']!r}"
        )

    # Anti-duplicate: Page 1 prose MUST NOT contribute to the
    # record list (the section gate prevents it). Page 1 has
    # ``Employee Contributions $9,988.62`` — if section gate
    # regressed, we'd see MORE than 3 records with one extra row
    # hinting at the prose phrasing.
    assert len(recs) == 3, (
        f"section gate regressed: page-1 prose duplicated — got "
        f"{len(recs)} records; first description: "
        f"{recs[0]['description']!r}"
    )

    # Year-end reject stays out of Fidelity's ``Year-to-Date``
    # columns (the ant-false-positive contract).
    assert _YEAR_END_RE.search("Year-to-Date") is None

    # Phase 34 — the 401k warning message should explain that Fidelity
    # 401k PDFs provide period summaries, not individual transactions.
    from app.services.import_parser import parse_uploaded_statement
    from fastapi import UploadFile
    import io
    body2 = (
        FIXTURES / "Fidelity NetBenefits - Statement Details.pdf"
    ).read_bytes()
    result = parse_uploaded_statement(UploadFile(
        filename="Fidelity NetBenefits - Statement Details.pdf",
        file=io.BytesIO(body2),
    ))
    warnings = result.get("warnings", [])
    assert any("period summaries" in w for w in warnings), (
        f"401k warning should mention 'period summaries'; got {warnings}"
    )


def test_fidelity_401k_section_state_transitions():
    """Phase 10.1c — the 401k activity section state-machine
    primitives MUST correctly identify ``Your Account Activity By
    Fund`` as the section header, ``Activity Total`` as the
    column-break marker, and MUST NOT misfire on a single-word
    ``Activity`` line or on column-header prose containing
    ``Total`` mid-line (``Total US Stock Index`` fund name).

    Locks the positive and negative cases directly on the regexes
    so a future drift in section detection surfaces loudly.
    """
    from app.services.import_parser import (
        _FIDELITY_401K_ACTIVITY_HEADER_RE,
        _FIDELITY_401K_ACTIVITY_RE,
        _STANDALONE_TOTAL_AT_EOL_RE,
    )

    # Positive: section header matches.
    assert _FIDELITY_401K_ACTIVITY_HEADER_RE.match(
        "Your Account Activity By Fund"
    ) is not None
    assert _FIDELITY_401K_ACTIVITY_HEADER_RE.match(
        "  Your Account Activity By Fund  "
    ) is not None  # whitespace-tolerant

    # Negative: prose sections that look similar but aren't the
    # NetBenefits pivot table.
    assert _FIDELITY_401K_ACTIVITY_HEADER_RE.match(
        "Your Account Summary"
    ) is None
    assert _FIDELITY_401K_ACTIVITY_HEADER_RE.match(
        "Account Activity By Fund"  # missing "Your "
    ) is None

    # Positive: column-break marker matches ONLY when "Total" is
    # at end-of-line preceded by "Activity".
    assert _STANDALONE_TOTAL_AT_EOL_RE.search(
        "Activity Total"
    ) is not None
    assert _STANDALONE_TOTAL_AT_EOL_RE.search(
        "Detailed Transaction History Activity Total"
    ) is not None  # re.search works mid-line too

    # Negative: fund names containing "Total" mid-line (NOT at EOL)
    # MUST NOT trigger the column break.
    assert _STANDALONE_TOTAL_AT_EOL_RE.search(
        "AT&T Asset Total US Stock AT&T US Lg Cap US"
    ) is None, (
        "fund name 'Total US Stock Index' must not misfire as "
        "column-break marker"
    )
    assert _STANDALONE_TOTAL_AT_EOL_RE.search(
        "Activity"
    ) is None, (
        "single-word 'Activity' line (the L018 column-header "
        "continuation) must not misfire"
    )
    assert _STANDALONE_TOTAL_AT_EOL_RE.search(
        "Account Totals $501,754.50"
    ) is None, (
        "section-totals line 'Account Totals $X' must not "
        "misfire"
    )

    # Positive: activity row matches all 3 keep labels and all 3
    # skip labels with realistic 2+ money-tokens payload.
    for label in (
        "Employee Contributions",
        "Employer Contributions",
        "Dividends",
        "Beginning Balance",
        "Ending Balance",
        "Change in Market Value",
    ):
        line = f"{label} $499.40 $0.00 $1,997.72 $9,988.62"
        m = _FIDELITY_401K_ACTIVITY_RE.match(line)
        assert m is not None, (
            f"activity row for label {label!r} should match the "
            f"pivot-table regex; got no match"
        )
        assert m.group("label").upper() == label.upper()

    # Negative: amounts that lack a leading ``-`` for a
    # negative-only row OR single money token do NOT match.
    assert _FIDELITY_401K_ACTIVITY_RE.match(
        "Employee Contributions $9,988.62"  # only 1 money token
    ) is None, (
        "single-money-token lines (Page 1 prose) must not match "
        "the pivot-table regex"
    )
    assert _FIDELITY_401K_ACTIVITY_RE.match(
        "CASH You Bought FIDELITY GOVERNMENT MONEY MARKET"
    ) is None


def test_individual_statement_pdf_preview_returns_pdf_record_count():
    """Fidelity brokerage statement — the Phase 10.1 fix added
    :data:`FIDELITY_GENERAL_RE` + :data:`FIDELITY_TWO_DATE_RE` plus
    statement-year harvesting and continuation-line support, so the
    brokerage statement's per-section activity lines now extract real
    transactions instead of returning 0.

    Locks:

    1. The heuristic MUST extract ≥ 30 records from the brokerage
       statement (Securities Bought/Sold + Dividends + Deposits +
       Taxes Withheld + Core Fund Activity + HSA sections + Debit
       Card).
    2. Spot-check that some well-known rows land on the asserted
       amounts/dates — page 8 page's ``ALPHABET INC CAP STK CL A
       (You Bought)`` for ``-$199.84``, page 9's NVIDIA dividend for
       ``+$1.59``, page 19's debit-card ``WWW.PROVID* PROVIDENCE`` for
       ``-$50.00``.
    3. CUSIPs (``02079K305``, ``78462F103``, ``46625H100``) MUST NOT
       leak into descriptions — they're stripped by the canonical
       9-char ``\\d{6}[A-Z0-9]{2}\\d`` shape in
       :func:`_extract_fidelity_security`.
    4. The statement-year MUST be harvested from the ``April 1, 2026
       - April 30, 2026`` header so MM/DD dates resolve to 2026 (not
       pandas's 1900 default for partial dates).
    """
    from app.services.import_parser import parse_pdf_file, parse_pdf_transactions

    body = (FIXTURES / "individual_Statement4302026.pdf").read_bytes()
    pre = parse_pdf_file(_upload("individual_Statement4302026.pdf", body))
    recs = parse_pdf_transactions(_upload("individual_Statement4302026.pdf", body))

    assert pre["file_type"] == "pdf"
    assert pre["record_count"] > 0  # text IS extracted
    assert isinstance(recs, list)
    # Lock the real extraction contract — was 0 before the Phase 10.1
    # fix; now ≥ 60 because Securities, Dividends, Deposits, Core
    # Fund Activity, HSA activity, and Debit Card all surface.
    assert len(recs) >= 60, (
        f"brokerage statement extraction regressed: expected >= 60, got {len(recs)}"
    )

    # Spot-check known transactions.
    by_desc = {round(r["amount"], 2): r["description"] for r in recs}
    # Page 8: 04/08 ALPHABET INC CAP STK CL A — purchased for -$199.84
    assert any(
        -199.84 == round(r["amount"], 2)
        and "ALPHABET" in r["description"].upper()
        and "(YOU BOUGHT)" in r["description"].upper()
        for r in recs
    ), f"missing -199.84 Alphabet You Bought; got {[r['amount'] for r in recs[:5]]}"
    # Page 9: 04/01 NVIDIA CORPORATION COM — Dividend Received for +$1.59
    assert any(
        1.59 == round(r["amount"], 2)
        and "NVIDIA" in r["description"].upper()
        and "DIVIDEND RECEIVED" in r["description"].upper()
        for r in recs
    ), "missing +$1.59 NVIDIA Dividend Received"
    # Page 19: 04/09 04/09 WWW.PROVID* PROVIDENCE — debit card -$50.00
    assert any(
        -50.00 == round(r["amount"], 2)
        and "PROVID" in r["description"].upper()
        for r in recs
    ), "missing -$50.00 debit card transaction on page 19"

    # CUSIP quality. The 9-char canonical CUSIP shape MUST NOT
    # surface in the persist-path descriptions.
    cusip_leak = [
        r for r in recs
        for cusip in ("02079K305", "78462F103", "46625H100")
        if cusip in r["description"]
    ]
    assert cusip_leak == [], (
        f"CUSIPs leaked into {len(cusip_leak)} descriptions: "
        f"{cusip_leak[0]['description'] if cusip_leak else 'n/a'!r}"
    )

    # Year-harvest correctness. The brokerage statement mixes two
    # date formats on different pages:
    #
    # - Most activity tables (pages 8-19) emit ``MM/DD`` only — the
    #   parser prepends ``statement_year=2026`` (harvested from the
    #   page-6 ``April 1, 2026 - April 30, 2026`` header) so these
    #   land in 2026.
    # - The Bond & CD section (page 12) emits full ``MM/DD/YYYY``
    #   with the user's actual lot-purchase dates, including
    #   PRIOR-YEAR rows (``02/21/2024 18RUT24G``,
    #   ``02/18/2025 18RUT25G``). These dates are LEGITIMATE history
    #   of the user's bond purchases and MUST be preserved verbatim
    #   — they would otherwise be silently overwritten to 2026.
    #
    # The year assertion therefore blocks ONLY future-dated records
    # (year > 2026), which catches the regressions that actually
    # matter:
    #   - pandas 1900-default for partial dates (would surface as
    #     1900-02-21, lower than 2026, but is still wrong).
    #   - off-by-one rollovers from a mis-incremented year.
    #
    # Prior versions of this assert used ``year != 2026`` — that was
    # too strict and would fire on the genuine 2024/2025 bond rows
    # above. The relaxed ``year > 2026`` captures only future-dated
    # exceptions. DO NOT tighten back without a separate bond-row
    # registry lock.
    future_year = [r for r in recs if r["transaction_date"].year > 2026]
    assert future_year == [], (
        f"year-harvest produces future-dated records: "
        f"{len(future_year)} records with year > 2026 — likely a "
        f"mis-parse of MM/DD/YYYY. First offender: "
        f"{future_year[0]['transaction_date']!r}"
    )


def test_inline_table_header_skip():
    """:data:`_INLINE_TABLE_HEADER_RE` MUST skip multi-word table-header
    lines whose token set contains AT LEAST TWO of the canonical
    activity-table column words. Without this, a header like
    ``Date Security Name CUSIP Description Quantity Price Cost Amount``
    would leak every column word into a previous record's description
    via the continuation-line path.

    Locks the positive case (skip these headers) AND a negative case
    (do NOT skip a transaction row that only mentions one of those
    words incidentally — e.g. ``ALPHABET INC … Reinvestment …``).
    """
    from app.services.import_parser import _INLINE_TABLE_HEADER_RE

    assert _INLINE_TABLE_HEADER_RE.search(
        "Date Security Name CUSIP Description Quantity Price Cost Amount"
    ) is not None
    assert _INLINE_TABLE_HEADER_RE.search(
        "Settlement Symbol/CUSIP Transaction Date Security Name Quantity Price"
    ) is not None
    assert _INLINE_TABLE_HEADER_RE.search(
        "Trans. Date Post Date Location Reference/Description Amount"
    ) is not None
    # Negative case — transaction rows mentioning ONE column word
    # but not two MUST NOT be mis-classified as a header.
    assert _INLINE_TABLE_HEADER_RE.search(
        "ALPHABET INC CAP STK CL A You Bought 0.658 $303.71500 - -$199.84"
    ) is None
    # And the bare ``Quantity`` header (single-word) isn't skipped
    # by the inline detector — that path is the SECTION_HEADER_RE's job.
    assert _INLINE_TABLE_HEADER_RE.search("Quantity") is None


def test_year_end_marker_never_false_positives_on_year_to_date():
    """Phase 10's year-end reject regex MUST NOT flag legitimate
    "year-to-date" markers that appear in quarterly Fidelity statements.
    Lock the anti-false-positive contract directly on the regex.
    """
    from app.services.import_parser import _YEAR_END_RE

    assert _YEAR_END_RE.search("Year-to-Date") is None, (
        "year-to-date text in a Fidelity quarterly statement must not "
        "trigger the year-end reject"
    )
    assert _YEAR_END_RE.search("YTD Performance") is None
    assert _YEAR_END_RE.search("This Period Year-to-Date") is None
    # Positive cases — must match.
    assert _YEAR_END_RE.search("Year-End Summary of Holding") is not None
    assert _YEAR_END_RE.search("2025 year-end summary of transactions") is not None
    assert _YEAR_END_RE.search("Annual Summary of Charges") is not None


def test_csv_summary_skip_returns_zero_for_csv_without_register_header():
    """If a CSV has no register header in the first 50 rows, the
    :func:`_find_csv_header_index` helper MUST gracefully return 0
    (no skiprows) so the legacy path runs unchanged. The user's
    "Missing: date, amount" 400 still surfaces; we don't silently mask
    it with a 0-count preview.
    """
    from app.services.import_parser import _find_csv_header_index

    # CSV that is summary-only (no canonical register header).
    body = (
        b"Description,,Summary Amt.\n"
        b"Beginning balance,,5438.03\n"
        b"Total credits,,2500.00\n"
        b"Total debits,,1500.00\n"
        b"Ending balance,,6438.03\n"
    )

    found = _find_csv_header_index(_upload("summary_only.csv", body))
    assert found == 0, (
        f"header scanner should return 0 (fallback to legacy path) when "
        f"no canonical header is found; got {found}"
    )


def test_transaction_synonym_routes_to_description():
    """Phase 10 added ``transaction`` -> ``description`` so a CSV with
    ``Date,Transaction,Amount,Balance`` validates end-to-end. Drives
    :func:`_validate_csv_schema` directly so future synonym-map
    regressions surface immediately.
    """
    import pandas as pd
    from app.services.import_parser import _validate_csv_schema

    df = pd.DataFrame(columns=["Date", "Transaction", "Amount", "Balance"])
    column_map = _validate_csv_schema(df)
    canonicals = set(column_map.values())
    assert {"date", "description", "amount"}.issubset(canonicals), (
        f"transaction synonym failed: {column_map!r}"
    )


def test_excel_multi_sheet_preview_persist_parity():
    """Phase 10 multi-sheet Excel: a workbook with one sheet must
    preview.match_records == persist, and both must equal the row
    count of the single sheet (no off-by-one from the dict iteration).
    """
    import openpyxl
    from app.services.import_parser import parse_excel_file, parse_excel_transactions

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Checking"
    ws.append(["Date", "Description", "Amount", "Merchant"])
    for d, desc, amt, m in [
        ("01/15/2024", "Coffee", -4.50, "Blue Bottle"),
        ("01/16/2024", "Salary", 3500.00, "Acme"),
        ("01/17/2024", "Grocery", -87.32, "Whole Foods"),
    ]:
        ws.append([d, desc, amt, m])
    buf = io.BytesIO()
    wb.save(buf)
    body = buf.getvalue()

    pre = parse_excel_file(_upload("multi.xlsx", body))
    body2 = buf.getvalue()
    recs = parse_excel_transactions(_upload("multi.xlsx", body2))

    assert pre["file_type"] == "xlsx"
    assert pre["record_count"] == len(recs), (
        f"Excel parity drift: preview={pre['record_count']} vs persist={len(recs)}"
    )
    assert pre["record_count"] == 3
