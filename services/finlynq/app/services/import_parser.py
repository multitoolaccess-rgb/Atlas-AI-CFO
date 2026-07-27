"""Phase 7+ lift — ``import_parser`` with .csv + .pdf + .ofx + .xlsx dispatch.

This module replaces the Phase 5 stub with the real wealthiq parser
verbatim + extension to .ofx/.qfx (Phase 5 drop) + .xlsx (Phase 9).
Phase 5b.2 OCR support lives in ``ocr_parser.py``;
``parse_uploaded_statement`` returns a dict with ``ocr: True`` when
the PDF path went through OCR (Phase 5 routes/imports.py uses this
marker).

Wealthiq parity:

- CSV: pandas ``read_csv`` + normalised column mapping (date /
  amount / description / merchant_name / is_pending).
- PDF (text-layer): pdfplumber ``extract_text()`` line-by-line
  preview; ``extract_pdf_transactions`` heuristic turns Fidelity
  quarterly statements into real ``Transaction`` rows.
- PDF (image-only, OCR fallback): pdfplumber ``to_image(300dpi)`` +
  pytesseract ``image_to_string`` (in ``ocr_parser.ocr_parse_statement``).
- OFX/QFX: ``ofxparse.OfxParser.parse`` (Phase 5) — free Plaid substitute.
- Excel: ``pd.read_excel`` (engine auto-detected) on every sheet
  (Phase 10: ``sheet_name=None``) so a bank that exports checking
  onto sheet 1 and savings onto sheet 2 isn't silently truncated.

Phase 10 extensions (real-world bank-statement samples):

- **CSV summary-header skip**: A Wells Fargo statement begins with
  ~5 rows of summary block (``Description,,Summary Amt.``) BEFORE
  the actual ``Date,Description,Amount,Running Bal.`` header. Without
  the pre-scan, pandas treats the summary's first row as the header
  and ``_validate_csv_schema`` raises the cryptic
  ``Missing: date, amount`` 400. We pre-scan the first 50 rows with
  stdlib ``csv`` looking for the canonical schema, then pass
  ``skiprows=N`` to ``pd.read_csv`` so the real header is row 0 of
  the parsed DataFrame.
- **Bank of America year-end card summary (Phase 10.1b)**: A Bank
  of America / Credi year-end summary PDF
  (e.g. ``credi_YearEndSummary_2026.pdf``) is THE canonical user-
  importable transaction list — the file contains ~200 lines of
  ``MM/DD/YY <merchant> <CITY>, <ST> <amount>[CR]``, which is the
  layout real users count on the importer to handle. An earlier
  Phase 10 change auto-rejected any PDF that mentioned
  ``year-end summary`` / ``annual summary`` — that reject was the
  wrong default. The user's two screenshots showing "0 transactions"
  were this rejection firing on the very PDF they wanted to import.
  Phase 10.1b REMOVES the reject and ADDS
  :data:`CREDI_YEAR_END_RE` so the layout now extracts (the
  :data:`_YEAR_END_RE` regex constant is retained for tests / UI
  metadata but no longer triggers a runtime reject).
- **Multi-sheet Excel**: Banks that export to .xlsx frequently put
  checking in sheet 1 and savings in sheet 2. Reading ``sheet_name=0``
  silently drops the second account. We iterate all sheets and
  accumulate the surviving records.
- **Debug breadcrumb on unparseable date lines**: When a PDF line
  starts with ``01/15`` but none of PATTERN_A/B/GENERAL match (e.g.
  the description field is on a separate line), we log a DEBUG
  breadcrumb so an operator chasing "why is the count low?" can find
  the offender. Never INFO — would flood the log on normal statements.
- **Transaction synonym** (``transaction`` → ``description``):
  Covers Wells Fargo "Transaction" column without weakening the
  schema-validation contract.
"""
import csv
import io
import logging
import re
from datetime import datetime
from typing import Any

import pandas as pd
import pdfplumber
from fastapi import UploadFile

# Module logger so the heuristic parser can surface DEBUG/WARNING
# breadcrumbs for unparseable date / amount inputs that get silently
# dropped (vs a ledger full of garbage, silent drops are safer but
# are also useless to debug without a log line). Pair this breadcrumb
# with the module-level `_logger` in routes/imports.py so an operator
# running ``tail -f`` on the uvicorn access log correlates parser-
# level drops with route-level DELETE events.
_logger = logging.getLogger(__name__)

# Year-end/annual summary markers (case-insensitive). Matches a line
# containing ``year-end summary`` or ``annual summary`` (or with a
# single dash/space variant, e.g. ``Year End Summary``). Excludes
# ``year-to-date`` because that phrase appears LEGITIMATELY on
# quarterly statements (Fidelity includes "Year-to-Date" headers
# that must NOT be rejected).
#
# RETAINED FOR TESTS/UI — Phase 10.1b removed the runtime
# auto-reject that consumed this regex. Year-end-summary PDFs are
# legitimate user-importable transaction lists (canonical Bank of
# America / Credi card exports — see the BofA bullet in the
# module docstring), so the parser no longer short-circuits to
# zero records just because the document mentions the phrase.
# The constant stays around so the ``test_year_end_marker_never_
# false_positives_on_year_to_date`` regression test continues
# locking the regex's anti-false-positive contract.
_YEAR_END_RE = re.compile(
    r"year[\s\-]*end[\s\-]+summary|annual[\s\-]+summary",
    re.IGNORECASE,
)

# A date-like prefix used by the parse_pdf_transactions debug
# breadcrumb — log when a line STARTS with what looks like a date
# but no regex matched, so the operator can debug "missing rows".
_DATE_PREFIX_RE = re.compile(r"^\d{1,2}[/\-]\d{1,2}")


def _normalize_headers(columns: list[str]) -> list[str]:
    """Lowercase + collapse whitespace to underscores, strip
    parenthetical suffixes and currency glyphs.

    Real-world bank CSV headers such as ``Transaction Date``,
    ``Posted Date``, ``Transaction Amount``, ``Amount (USD)``,
    ``Amount ($)``, ``Debit ($CAD)`` and ``Credit (£)`` all need
    to resolve to the canonical snake_case keys used by
    :func:`_build_column_map`. Without:

    (a) the whitespace collapse, ``Transaction Date`` would
        lowercase to ``transaction date`` (with a literal space)
        and miss ``transaction_date``;
    (b) the parenthetical strip, ``Amount (USD)`` would lower to
        ``amount_(usd)`` and miss ``amount``;
    (c) the currency-glyph strip, ``Debit (£)`` would lower to
        ``debit_(£)`` and miss ``debit``.

    All three mutations fold onto a single canonical form so the
    synonym map stays single-source-of-truth. Tabs/non-breaking-
    spaces collapse too (``\\s+``); nothing else is mutated.
    Non-Latin glyphs (₹/₩/¥ etc.) are NOT stripped — a rare
    importer with such headers can rename their column header to
    ``Amount`` instead.
    """
    cleaned: list[str] = []
    for column in columns:
        # Strip trailing parenthetical suffix: ``Amount (USD)`` ->
        # ``Amount``. Non-greedy on the inner match so
        # ``Amount ($CAD)`` collapses to ``Amount`` cleanly.
        # Parentheses inside a real header (e.g. ``Acme Corp
        # (Office)``) are bank-territory rare; the trade-off is
        # documented and the rare importer can rename.
        no_paren = re.sub(r"\(.*?\)", "", column)
        # Strip inline currency glyphs so ``$ Amount`` and
        # ``Credit (£)`` resolve to canonical names.
        no_glyph = re.sub(r"[$€£¥]", "", no_paren)
        snake = re.sub(r"\s+", "_", no_glyph.strip().lower()).strip("_")
        cleaned.append(snake)
    return cleaned


def _build_column_map(columns: list[str]) -> dict[str, str]:
    mapping = {
        # date column — covers the common bank-export shapes
        # (Chase "Transaction Date", BofA "Date Posted", Wells
        # "Posting Date", Fidelity "Posted Date", Amex "Trans Date").
        "date": "date",
        "transaction_date": "date",
        "activity_date": "date",
        "trans_date": "date",
        "tx_date": "date",
        "txn_date": "date",
        "posting_date": "date",
        "posted_date": "date",
        "date_posted": "date",
        # amount column — covers most CSV exports.
        "amount": "amount",
        "transaction_amount": "amount",
        # split-amount columns (savings / checking export format).
        # When BOTH ``credit`` AND ``debit`` headers are present
        # and no plain ``amount`` column is, the per-row loop
        # computes ``amount = credit - debit`` so deposits are
        # positive, withdrawals negative. Constraint-4 in
        # :func:`_validate_csv_schema` settles the tie when a
        # file has BOTH a plain amount AND the split pair: the
        # populated column wins, the empty one is dropped (so a
        # quirky export filling all four columns does not get
        # doubly-counted).
        "credit": "credit",
        "credits": "credit",
        "deposits": "credit",
        "deposit": "credit",
        "money_in": "credit",
        "paid_in": "credit",
        "debit": "debit",
        "debits": "debit",
        "withdrawals": "debit",
        "withdrawal": "debit",
        "money_out": "debit",
        "paid_out": "debit",
        # description column — banks use several synonyms. The bare
        # ``transaction`` synonym was added (Phase 10) so a Wells
        # Fargo "Transaction" column routes to ``description`` —
        # without that, a hypothetical WF checking export using
        # ``Date,Transaction,Amount,Running Bal.`` would fail with
        # ``Missing: description``. Bare ``description`` and the
        # existing ``transaction_details`` / ``particulars`` /
        # ``narrative`` / ``remarks`` synonyms stay.
        "description": "description",
        "memo": "description",
        "details": "description",
        "transaction_details": "description",
        "transaction": "description",
        "transaction_description": "description",
        "particulars": "description",
        "narrative": "description",
        "remarks": "description",
        # merchant_name column.
        "merchant_name": "merchant_name",
        "merchant": "merchant_name",
        "payee": "merchant_name",
        # pending flag.
        "pending": "is_pending",
    }
    normalized = {}
    for column in columns:
        canonical = mapping.get(column)
        if canonical:
            normalized[column] = canonical
    return normalized


def _coerce_amount_or_zero(value: Any) -> float:
    """Parse an amount cell, returning 0.0 ONLY for legitimately-
    blank cells (NaN / None / empty string) — raises on unparseable
    input.

    Used by the per-row loop in :func:`parse_csv_transactions` to
    fold split-credit / split-debit columns into the canonical
    ``amount`` field of the output record. A row where the user
    has a deposit (``debit`` column blank, ``credit`` column
    populated) is legitimate: ``amount_in = 2500, amount_out = 0,
    amount = +2500``. Same for withdrawals — that's why blanks /
    NaN / empty-strings all coerce to 0.0 silently.

    Distinct from :func:`_parse_amount` which RAISES on missing /
    invalid input — that strict mode is correct for a single-
    amount column where a blank is genuinely malformed. Here the
    permissive zero-coerce is correct ONLY for the structural-
    empty cases (so a row with one side filled doesn't drop); for
    TRULY unparseable input (typos like ``"abc"``, ``"N/A"``,
    ``"--"``) we MUST raise so the per-row try/except catches it
    and the row is dropped via the existing
    ``_drop_malformed_rows`` pipeline. Returning 0.0 for ``"abc"``
    would silently convert ``Date,Coffee,abc,3500`` into
    ``amount = 0 - 3500 = -3500`` — wrong-signed pollution of
    the ledger that the user only notices on a later reconciliation.

    Sign convention: callers feed `amount = credit - debit`
    (Chase / BofA / Wells convention where debit values are entered
    positive and represent money going out). A bank that exports
    Debits with explicit negation will produce wrong-signed rows;
    that's a separate shipping concern documented in the
    container-phase followup and out of scope for Phase 9b.
    """
    if value is None or pd.isna(value):
        return 0.0
    s = str(value).strip().replace(",", "").replace("$", "")
    if s == "":
        return 0.0
    try:
        return float(s)
    except ValueError as exc:
        raise ValueError(
            f"Could not parse split-amount cell '{value}': {exc}"
        ) from exc


def _parse_amount(value: Any) -> float:
    if pd.isna(value):
        raise ValueError("Amount cannot be blank")
    if isinstance(value, (int, float)):
        return float(value)
    value_str = str(value).strip().replace(",", "").replace("$", "")
    if value_str == "":
        raise ValueError("Amount cannot be blank")
    try:
        return float(value_str)
    except ValueError as exc:
        raise ValueError(f"Could not parse amount '{value}': {exc}")


def _parse_date(value: Any) -> datetime:
    if pd.isna(value) or value is None:
        raise ValueError("Date cannot be blank")
    try:
        return pd.to_datetime(value)
    except Exception as exc:
        raise ValueError(f"Could not parse date '{value}': {exc}")


def _find_csv_header_index(
    upload_file: UploadFile, max_scan_rows: int = 50
) -> int:
    """Pre-scan the upload's first ``max_scan_rows`` rows and return
    the row index N whose normalized headers satisfy the CSV schema
    (``date`` + ``description`` + ``amount`` OR ``date`` +
    ``description`` + ``credit`` + ``debit``).

    Wells Fargo bank statements (and similar real-world exports)
    start with a 5-10 line ``Summary`` block that doesn't satisfy
    the schema; the actual ``Date,Description,Amount,...`` register
    header only appears later. Without pre-scanning, ``pd.read_csv``
    treats the summary's ``Description,,Summary Amt.`` row as the
    header (yielding a 3-column DataFrame that mismatches later
    rows whose column count grows), and ``_validate_csv_schema``
    surfaces a cryptic ``Missing: date, amount`` error.

    Implementation:

    - Read up to 64 KB of the upload's head (enough for ~50 lines
      without pulling entire 10 MB CSVs into memory).
    - Decode UTF-8 (with latin-1 fallback) and feed the bytes to
      stdlib ``csv.reader``.
    - For each row, run :func:`_normalize_headers` + :func:`_build_column_map`.
    - On a candidate match, ALSO verify the NEXT non-empty row has a
      parseable date in the same date-column index. This prevents a
      summary-section line containing the words ``Date`` /
      ``Description`` (rare but possible in metric tables) from
      being mistaken for the real register header.
    - If the next-row date evidence fails, save the candidate as a
      fallback and keep scanning.
    - Returns ``>= 1`` (real row index to pass to ``skiprows``) on a
      confident match, ``>= 1`` on a fallback match, ``0`` if no
      candidate was found (caller falls back to the legacy
      ``pd.read_csv`` with no skiprows).

    Returns ``0`` (not ``-1``) when no candidate was found so the
    caller's `skiprows > 0` check is unambiguous: ``0`` means
    "fall through to legacy path", ``>= 1`` means "skip the first
    N rows before pd.read_csv".

    The 64 KB pre-scan read is cheap (~ free for CSV) and bounded;
    a 10 MB bank's annual statement is unlikely to have its real
    register header past the first 64 KB of preamble.
    """
    upload_file.file.seek(0)
    raw = upload_file.file.read(64 * 1024)
    upload_file.file.seek(0)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = []
    fallback_candidate = 0
    for i, row in enumerate(reader):
        if i >= max_scan_rows:
            break
        rows.append(row)
        if not row:
            continue
        normalized = _normalize_headers(row)
        column_map = _build_column_map(normalized)
        canonicals = set(column_map.values())
        if "date" not in canonicals or "description" not in canonicals:
            continue
        has_amount = "amount" in canonicals
        has_split = "credit" in canonicals and "debit" in canonicals
        if not (has_amount or has_split):
            continue
        # First-time candidate without next-row evidence: save as fallback.
        # Confirmed candidate (next row has a parseable date in the date
        # column): return immediately so we lock onto the EARLIEST such
        # match, which is what the WF summary-section case requires.
        date_col_idx = next(
            (j for j, c in enumerate(normalized) if column_map.get(c) == "date"),
            None,
        )
        if date_col_idx is None:
            if fallback_candidate == 0:
                fallback_candidate = i
            continue
        for next_row in rows[i + 1:]:
            if not next_row or date_col_idx >= len(next_row):
                continue
            date_cell = str(next_row[date_col_idx]).strip()
            try:
                pd.to_datetime(date_cell)
                _logger.info(
                    "CSV %s: register header detected at row %d; skipping %d "
                    "summary rows before pd.read_csv.",
                    upload_file.filename, i, i,
                )
                return i
            except Exception:
                break
        if fallback_candidate == 0:
            fallback_candidate = i
    if fallback_candidate > 0:
        _logger.info(
            "CSV %s: register header fallback at row %d (no next-row date "
            "evidence, but schema matched).",
            upload_file.filename, fallback_candidate,
        )
    return fallback_candidate


def _find_dataframe_header_idx(
    df: "pd.DataFrame", max_scan_rows: int = 20
) -> int:
    """Find the row index that should be used as the header for a
    DataFrame that may not have a real header on row 0. Mirrors
    :func:`_find_csv_header_index` but operates on an in-memory
    DataFrame (e.g. after a ``pd.read_excel(sheet_name=None,
    header=None)`` pre-scan).

    Returns the row index N (``>= 0``) if a candidate was found,
    else ``-1`` so the caller can fall back to using the existing
    ``df.columns`` as-is.

    Same schema-validation heuristic as the CSV path:

    - row contains canonicals for ``date`` + ``description`` +
      (``amount`` OR ``credit`` AND ``debit``)
    - the next non-empty row has a parseable date in the same
      date-column position
    - if next-row evidence fails, save as fallback and keep scanning
    """
    if df.empty or len(df.columns) == 0:
        return -1
    fallback = -1
    rows_scanned = 0
    # Use index-based iteration because we may need to look AHEAD
    # of the current row; ``df.iterrows()`` is row-by-row but reading
    # df.iloc[j] is cleaner here.
    for i in range(len(df)):
        if rows_scanned >= max_scan_rows:
            break
        rows_scanned += 1
        row_vals = ["" if pd.isna(v) else str(v) for v in df.iloc[i].tolist()]
        if not any(v.strip() for v in row_vals):
            continue
        normalized = _normalize_headers(row_vals)
        column_map = _build_column_map(normalized)
        canonicals = set(column_map.values())
        if "date" not in canonicals or "description" not in canonicals:
            continue
        has_amount = "amount" in canonicals
        has_split = "credit" in canonicals and "debit" in canonicals
        if not (has_amount or has_split):
            continue
        date_col_idx = next(
            (j for j, c in enumerate(normalized) if column_map.get(c) == "date"),
            None,
        )
        if date_col_idx is None:
            if fallback < 0:
                fallback = i
            continue
        for j in range(i + 1, min(i + 5, len(df))):
            try:
                date_cell = df.iloc[j].iloc[date_col_idx]
                if pd.isna(date_cell):
                    continue
                pd.to_datetime(str(date_cell).strip())
                return i
            except Exception:
                continue
        if fallback < 0:
            fallback = i
    return fallback


def _slice_dataframe_with_header(
    raw_sheets: dict[str, "pd.DataFrame"],
) -> list[tuple[str, "pd.DataFrame"]]:
    """Pre-process a multi-sheet ``pandas`` dict so EACH sheet has
    a valid register-header row at position 0. Used by the Excel
    parser to handle the same kind of summary-block preamble that
    the CSV path's :func:`_find_csv_header_index` handles.

    Returns a list of ``(sheet_name, df)`` where ``df`` is the
    sheet's register rows + normalized column names. Sheets where
    no header row was found are dropped (logged at INFO with an
    "skipped" breadcrumb). Designed to be order-stable: iteration
    follows ``raw_sheets`` insertion order.

    Implementation reads the workbook once through ``pd.read_excel``
    without ``header=None`` so column count is preserved. The
    :func:`_find_dataframe_header_idx` helper is single-pass per
    sheet so the cost is O(rows * sheets).
    """
    out: list[tuple[str, "pd.DataFrame"]] = []
    for sheet_name, df_raw in raw_sheets.items():
        if df_raw.empty or len(df_raw.columns) == 0:
            _logger.info(
                "Excel sheet %r: empty; skipping.", sheet_name,
            )
            continue
        header_idx = _find_dataframe_header_idx(df_raw, max_scan_rows=20)
        if header_idx <= 0:
            # No preamble OR header is already at row 0 — use as-is.
            df = df_raw.reset_index(drop=True)
        else:
            # Use row header_idx as columns, drop rows <= header_idx.
            new_columns = [
                "" if pd.isna(v) else str(v).strip()
                for v in df_raw.iloc[header_idx].tolist()
            ]
            df = df_raw.iloc[header_idx + 1:].copy()
            df.columns = new_columns
            df = df.reset_index(drop=True)
            _logger.info(
                "Excel sheet %r: register header detected at row %d; "
                "skipping %d summary rows.", sheet_name, header_idx, header_idx,
            )
        out.append((sheet_name, df))
    return out


def _validate_csv_schema(df: "pd.DataFrame") -> dict[str, str]:
    """Normalize headers, build the column map, and assert the schema
    has structurally required canonicals (``date``/``amount``/``description``
    OR ``date``/``credit``+``debit``/``description`` for split-amount files).

    Shared between :func:`parse_csv_file` (preview) and
    :func:`parse_csv_transactions` (persist) so a CSV with arbitrary
    headers raises the SAME error from both paths — no preview/persist
    drift on bad schemas. Mutates ``df.columns`` in place to the
    normalized lowercase form so downstream helpers can index by canonical.

    Constraint 4: if BOTH a plain ``amount`` column AND the split
    pair (credit + debit) are present, the populated column wins
    and the empty one is dropped. This handles PDFs-of-CSVs and
    badly-exported statements that emit all four columns while
    only filling one. The populated check runs against the
    already-normalized df which has been written in place by
    ``df.columns = normalized`` above.

    Returns the canonical column map (``orig_name → canonical``) so the
    caller can pass it straight to :func:`_drop_malformed_rows`.
    """
    normalized = _normalize_headers(list(df.columns))
    df.columns = normalized
    column_map = _build_column_map(normalized)

    # Constraint 4 — see docstring.
    has_amount = "amount" in column_map.values()
    has_split_pair = (
        "credit" in column_map.values() and "debit" in column_map.values()
    )
    if has_amount and has_split_pair:
        amount_orig = next(
            (o for o, c in column_map.items() if c == "amount"), None
        )
        # Coerce-as-NaN populated-check so the picker and the
        # drop_malformed filter agree on what "populated" means. A
        # column of blank ``""`` strings (the actual artifact of
        # ``on_bad_lines='skip'`` on too-FEW-field rows) coerces to
        # NaN, so this check correctly classifies such a column as
        # ``not populated`` (vs the old ``.notna().any()`` which
        # treated ``""`` rows as populated and the engaged split
        # pair ended up wrongly discarded downstream, silently
        # wiping the CSV to zero records).
        amount_populated = (
            amount_orig is not None
            and amount_orig in df.columns
            and pd.to_numeric(
                df[amount_orig], errors="coerce"
            ).notna().any()
        )
        split_keys_to_drop = [
            o for o, c in column_map.items() if c in ("credit", "debit")
        ]
        amount_keys_to_drop = [
            o for o, c in column_map.items() if c == "amount"
        ]
        if amount_populated:
            for k in split_keys_to_drop:
                del column_map[k]
        else:
            for k in amount_keys_to_drop:
                del column_map[k]

    # Schema-required columns: ``date`` and ``description`` are
    # single-canonical. ``amount`` is satisfied by EITHER the
    # plain canonical OR the split pair (credit + debit). The
    # error message stays single-canonical so the UI surface
    # continues showing "Missing: date, amount" / "Missing:
    # description" rather than branching on which path the
    # parser would have used.
    final_canonicals = set(column_map.values())
    missing: list[str] = []
    if "date" not in final_canonicals:
        missing.append("date")
    if "description" not in final_canonicals:
        missing.append("description")
    if (
        "amount" not in final_canonicals
        and not (
            "credit" in final_canonicals and "debit" in final_canonicals
        )
    ):
        missing.append("amount")
    if missing:
        raise ValueError(
            "CSV statement must include 'date', 'amount', and 'description' columns. "
            f"Missing: {', '.join(missing)}."
        )
    return column_map


def _drop_malformed_rows(
    df: "pd.DataFrame", column_map: dict[str, str]
) -> tuple["pd.DataFrame", int]:
    """Drop rows where the canonical ``date`` column is NaN or blank,
    OR where the amount column is NaN/blank (single-amount files),
    OR where BOTH split-credit AND split-debit are NaN/blank
    (split-amount files).

    Description column is intentionally NOT filtered: NaN/blank-string
    descriptions are kept and auto-filled downstream in the per-row
    loop with ``"Imported transaction"`` (legitimate-pocket for banks
    like Plaid that leave memo/description blank on some rows). An
    EMPTY FIELD in a CSV (``,``) IS read by ``pandas`` as actual
    ``np.nan`` — so even a NaN check would drop legitimate bank
    exports that use this pattern. Keep it permissive here; the
    per-row loop owns the description placeholder.

    For split-amount CSVs (canonical ``credit`` + ``debit`` instead
    of ``amount``), the keep-mask is the OR of credit-and-debit
    being populated on a row — a row with only one side filled is
    legitimate (knowingly zero on the other side; the per-row loop
    treats the missing side as 0 via :func:`_coerce_amount_or_zero`).

    Shared between :func:`parse_csv_file` (preview) and
    :func:`parse_csv_transactions` (persist) so the preview's
    ``record_count`` strictly equals the persist path's surviving row
    count — the user never sees "5 rows detected" in the preview
    while the persist path quietly drops to 4.

    Returns ``(filtered_df, dropped_count)``. The filtered df keeps the
    normalized (lowercase) column names so callers can still surface
    raw column names in their preview/persist output.
    """
    if df.empty:
        return df, 0

    # Reverse the column_map once: ``column_map[orig_name] = canonical``
    # → invert to ``canonical → orig_name``. When multiple original
    # columns map to the same canonical (e.g. CSV has BOTH ``amount``
    # and ``transaction_amount``), the FIRST insertion wins by
    # dict-insertion-order which is deterministic since Python 3.7.
    canonical_to_orig: dict[str, str] = {}
    for orig_name, canonical in column_map.items():
        canonical_to_orig.setdefault(canonical, orig_name)

    before = len(df)
    keep_mask = pd.Series(True, index=df.index)

    # Date — single canonical, drop NaN/blank.
    date_orig = canonical_to_orig.get("date")
    if date_orig and date_orig in df.columns:
        keep_mask &= (
            df[date_orig].notna()
            & (df[date_orig].astype(str).str.strip() != "")
        )

    # Amount — EITHER a single ``amount`` canonical (drop
    # NaN/blank) OR a split pair (credit + debit). For the
    # split pair, the keep-mask is credit-present OR
    # debit-present — a row with only one side populated is
    # legitimate. Constraint-4 ensures exactly one path is
    # canonical after parse-time — this branch reads the
    # surviving canonicals.
    if "amount" in column_map.values():
        amt_orig = canonical_to_orig.get("amount")
        if amt_orig and amt_orig in df.columns:
            # Coerce to numeric, NOT just NaN-check: ``pd.to_numeric(
            # errors='coerce')`` returns NaN for unparseable cells
            # like ``"abc"`` / ``"N/A"`` / ``"--"``. The downstream
            # per-row :func:`_coerce_amount_or_zero` will surface
            # these as ValueError (and the row is dropped) so the
            # preview path MUST also drop them — without this
            # ``pd.to_numeric`` filter we re-introduce the
            # preview/persist drift Phase 9 set out to eliminate
            # (preview says ``record_count=2`` but persist writes 1).
            # Strip currency symbols and commas so formatted cells
            # like ``$2,500.00`` survive the bulk filter (the per-row
            # parser already handles them, so the filter must agree).
            parsed = pd.to_numeric(
                df[amt_orig].astype(str).str.replace("[$,]", "", regex=True),
                errors="coerce",
            )
            keep_mask &= parsed.notna()
    elif (
        "credit" in column_map.values()
        and "debit" in column_map.values()
    ):
        credit_orig = canonical_to_orig.get("credit")
        debit_orig = canonical_to_orig.get("debit")
        # Coerce each side to numeric; a missing column gets an
        # all-NaN Series so the OR mask below evaluates cleanly.
        if credit_orig and credit_orig in df.columns:
            credit_parsed = pd.to_numeric(
                df[credit_orig].astype(str).str.replace("[$,]", "", regex=True),
                errors="coerce",
            )
        else:
            credit_parsed = pd.Series(float("nan"), index=df.index)
        if debit_orig and debit_orig in df.columns:
            debit_parsed = pd.to_numeric(
                df[debit_orig].astype(str).str.replace("[$,]", "", regex=True),
                errors="coerce",
            )
        else:
            debit_parsed = pd.Series(float("nan"), index=df.index)
        # Row survives if AT LEAST ONE side parses (the per-row
        # loop treats the unparsed side as 0 via
        # :func:`_coerce_amount_or_zero`). Unparseable on BOTH
        # sides === whole-row typo, drop.
        keep_mask &= (credit_parsed.notna() | debit_parsed.notna())

    filtered = df[keep_mask]
    dropped = before - len(filtered)
    return filtered, dropped


def parse_csv_file(upload_file: UploadFile) -> dict[str, Any]:
    """Read a CSV via pandas, return the first 5 records as preview.

    Phase 10 addition: pre-scans the upload's first 50 rows via
    :func:`_find_csv_header_index` so Wells Fargo-style summary
    blocks at the top of the file don't silently misalign pandas'
    header inference. The pre-scan is bounded to ~64 KB of input
    so the cost is negligible on a 10 MB statement.

    ``on_bad_lines='skip'`` makes pandas tolerant of trailing-row quirks
    the user's bank may emit: a stray footer line with the wrong column
    count, an extra column inserted by a bank's export template (e.g.
    a ``category`` column), or an embedded newline inside a quoted
    description that splits a row into two malformed halves. Pandas 1.3+
    provides this arg to opt into the old ``error_bad_lines=False``
    behaviour; we additionally emit a ``UserWarning`` because the
    behaviour is opt-in and silently changes error semantics.

    Real-world trigger that motivated this: user uploaded a Fidelity
    brokerage export and got ``ParserError: Error tokenizing data.
    C error: Expected 12 fields in line 7, saw 4``. Made the entire
    upload fail with the row-nuking 400 even though the rest of the
    file was well-formed.

    Per-row defensive NaN trim: pandas does NOT reliably drop
    too-FEW-field rows under ``on_bad_lines='skip'`` — it often pads
    them with NaN. We share :func:`_drop_malformed_rows` with the
    persist path so preview/persist symmetry holds even when the
    header is capitalised ("Amount" vs "amount") or uses a synonym
    ("transaction_amount"). The preview's ``record_count`` strictly
    equals the count of rows that land in the DB.

    Schema validation: this preview path now runs the SAME
    :func:`_validate_csv_schema` helper that the persist path does.
    Without this, a headerless CSV would preview ``record_count=10``
    while persist raises 400 and creates zero transactions —
    preview/persist drift. The 400 in the route layer turns this
    into a friendly "missing required columns" error message.
    """
    header_idx = _find_csv_header_index(upload_file)
    upload_file.file.seek(0)
    try:
        if header_idx > 0:
            df = pd.read_csv(
                upload_file.file, skiprows=header_idx, on_bad_lines="skip",
            )
        else:
            df = pd.read_csv(upload_file.file, on_bad_lines="skip")
    except Exception as exc:
        raise ValueError(f"Could not parse CSV file: {exc}")

    column_map = _validate_csv_schema(df)
    df, dropped = _drop_malformed_rows(df, column_map)
    if dropped:
        _logger.info(
            "CSV preview %s: dropped %d NaN-padded row(s); %d surviving.",
            upload_file.filename, dropped, len(df),
        )

    preview = df.head(5).fillna("").to_dict(orient="records")
    return {
        "file_type": "csv",
        "record_count": len(df),
        "preview": preview,
        "filename": upload_file.filename,
    }


def parse_csv_transactions(upload_file: UploadFile) -> list[dict[str, Any]]:
    """Parse a CSV bank statement into normalised transaction records.

    Phase 10 addition: pre-scans for the register-header row (see
    :func:`_find_csv_header_index` and :func:`parse_csv_file`) so
    summary-section CSVs are processed end-to-end.

    Same ``on_bad_lines='skip'`` contract as :func:`parse_csv_file`:
    a stray row with a different column count than the header is
    silently dropped so the upload doesn't reject a file that's
    otherwise valid. The preview returned by ``parse_csv_file`` and
    the persisted transactions returned by this function therefore
    see the SAME surviving row set (modulo the df-to-rows column
    filter below), which keeps the BE's preview/persist invariant
    consistent — before this fix the preview said "5 rows" and the
    persisted set said "0 rows" for a file with a malformed footer.
    """
    header_idx = _find_csv_header_index(upload_file)
    upload_file.file.seek(0)
    try:
        if header_idx > 0:
            df = pd.read_csv(
                upload_file.file, skiprows=header_idx, on_bad_lines="skip",
            )
        else:
            df = pd.read_csv(upload_file.file, on_bad_lines="skip")
    except Exception as exc:
        raise ValueError(f"Could not parse CSV file for transactions: {exc}")

    if df.empty:
        return []

    column_map = _validate_csv_schema(df)

    # Apply the bulk malformed-row filter so persist's record count
    # matches the preview path's record_count invariant. Without
    # this, the persist path only caught malformed rows via the
    # per-row try/except (above), which lets through additional
    # rows the preview path drops via ``_drop_malformed_rows``
    # (e.g. checking_stmt.csv: preview=381, persist=505). Applying
    # the same filter unifies the two paths. The per-row try/except
    # is kept as a second layer of defense — it catches rows that
    # pass the bulk filter but fail format-specific parsing (a
    # date-shaped token like ``"undefined"`` that survives the
    # ``notna().str.strip() != ""`` check).
    df, _malformed_dropped = _drop_malformed_rows(df, column_map)
    if _malformed_dropped:
        _logger.info(
            "CSV persist %s: bulk-filter dropped %d malformed row(s).",
            upload_file.filename, _malformed_dropped,
        )

    # Per-row defensive try/except. ``on_bad_lines='skip'`` is the
    # first line of defence (pseudo-fix for too-many-field rows that
    # pandas recognises as malformed), BUT pandas does NOT reliably
    # drop too-FEW-field rows — it pads them with NaN. The symmetry
    # with the preview path is enforced by :func:`_drop_malformed_rows`
    # above (called on the same df). This try/except additionally
    # catches rows where ``_parse_date``/``_parse_amount`` raises AFTER
    # the NaN trim (e.g. amount column has a non-numeric token like
    # "TBD" that pandas didn't surface as NaN but ``float()`` rejects).
    # The contract is: a single bad row MUST NOT collapse a 50-row
    # statement upload. A debug log records what was dropped so an
    # operator chasing "why is the count low?" can find the offender.
    records: list[dict[str, Any]] = []
    dropped_rows = 0
    for _, row in df.iterrows():
        try:
            normalized = {}
            for column_name, canonical in column_map.items():
                value = row[column_name]
                normalized[canonical] = value

            transaction_date = _parse_date(normalized.get("date"))
            # Per-row amount resolution: single ``amount`` column
            # OR split-pair (credit + debit). Schema-validate
            # enforces AT LEAST one of those is present in the
            # file; this branch selects which path to use for
            # THIS row. Constraint-4 ensures exactly one path is
            # canonical after parse-time so the route receives
            # ``record['amount']`` either way.
            canonicals_in_use = set(column_map.values())
            if "amount" in canonicals_in_use:
                amount = _parse_amount(normalized.get("amount"))
            elif (
                "credit" in canonicals_in_use and "debit" in canonicals_in_use
            ):
                amount = (
                    _coerce_amount_or_zero(normalized.get("credit"))
                    - _coerce_amount_or_zero(normalized.get("debit"))
                )
            else:
                # Unreachable: _validate_csv_schema would have
                # raised already. Defensive default for forward-
                # compat with future canonicals.
                amount = _parse_amount(normalized.get("amount"))
            # ``pd.read_csv`` reads an empty `,,` field as ``np.nan``,
            # NOT as ``""``. ``str(np.nan).strip()`` returns ``"nan"``
            # which is truthy, so a naive `if not description` check
            # would let the literal string ``"nan"`` slip into the DB.
            # Use ``pd.isna`` first to canonicalise BOTH the empty
            # and the NaN cases to the placeholder. This is the
            # legitimate-pocket for Plaid-style exports that leave the
            # memo/description column blank on some rows.
            raw_description = normalized.get("description")
            description = _canonicalize_text(
                normalized.get("description")
            )
            if not description:
                description = "Imported transaction"
        except (ValueError, TypeError) as exc:
            dropped_rows += 1
            _logger.warning(
                "Dropping malformed CSV row: %s (row_index=%d, total_dropped=%d)",
                exc, row.name, dropped_rows,
            )
            continue

        records.append(
            {
                "transaction_date": transaction_date,
                "amount": amount,
                "description": description,
                "merchant_name": (
                    _canonicalize_text(normalized.get("merchant_name")) or None
                ),
                "is_pending": bool(normalized.get("is_pending", False)),
            }
        )

    if dropped_rows:
        _logger.info(
            "Parsed CSV %s with %d malformed row(s) dropped; %d record(s) persisted.",
            upload_file.filename, dropped_rows, len(records),
        )

    return records


def parse_pdf_file(upload_file: UploadFile) -> dict[str, Any]:
    """Extract text lines from a PDF via pdfplumber. Returns the first 10
    non-blank lines as preview metadata. Statements that require OCR
    return ``record_count == 0``; the route layer (routes/imports.py)
    detects this and falls back to ``ocr_parse_statement``."""
    upload_file.file.seek(0)
    try:
        with pdfplumber.open(upload_file.file) as pdf:
            text_lines: list[str] = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_lines.extend([line.strip() for line in page_text.splitlines() if line.strip()])
    except Exception as exc:
        raise ValueError(f"Could not parse PDF file: {exc}")

    preview = text_lines[:10]
    return {
        "file_type": "pdf",
        "record_count": len(text_lines),
        "preview": preview,
        "filename": upload_file.filename,
    }


# Phase 5 OFX/QFX dispatcher — hidden behind a lazy import so the
# heavier ofxparse dependency only loads when the user actually uploads
# an OFX file (vs starting CSVs only).
def parse_ofx_file(upload_file: UploadFile) -> dict[str, Any]:
    """OFX/QFX dispatch: defers to ``app.services.ofx_parser.parse_ofx_file``."""
    from app.services.ofx_parser import parse_ofx_file as _impl

    return _impl(upload_file)


def parse_ofx_transactions(upload_file: UploadFile) -> list[dict[str, Any]]:
    """OFX/QFX dispatch: defers to ``app.services.ofx_parser.parse_ofx_transactions``."""
    from app.services.ofx_parser import parse_ofx_transactions as _impl

    return _impl(upload_file)


def parse_excel_file(upload_file: UploadFile) -> dict[str, Any]:
    """Read an Excel (.xlsx / .xls) file via pandas and return the
    first 5 records as preview, ACCUMULATED ACROSS ALL SHEETS.

    Phase 10: a multi-sheet Excel file (e.g. a bank export with
    ``Checking`` on sheet 1 and ``Savings`` on sheet 2) used to be
    silently truncated to ``sheet_name=0`` — the savings-account
    rows were dropped on the floor. Now we read every sheet and
    accumulate the surviving records so a single .xlsx upload
    imports all accounts in one batch.

    Each sheet is pre-processed through
    :func:`_slice_dataframe_with_header` so a per-sheet summary
    block (similar to the WF CSV summary) doesn't misalign pandas'
    header inference. Sheets with no valid header row are skipped
    with an INFO log breadcrumb.

    Uses ``pd.read_excel`` with ``engine=None`` (auto-detect) so both
    ``.xlsx`` (openpyxl) and ``.xls`` (xlrd) work transparently.
    """
    # Probe engines at import time so ``ModuleNotFoundError`` surfaces
    # as a clear message rather than a stack trace inside pandas.
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        raise ValueError(
            "Excel (.xlsx) support requires openpyxl. "
            "Install with: pip install openpyxl"
        )

    filename = upload_file.filename or ""
    file_type = "xlsx"  # default — used for both .xlsx and .xls in the route

    upload_file.file.seek(0)
    try:
        raw_sheets = pd.read_excel(upload_file.file, sheet_name=None)
    except Exception as exc:
        raise ValueError(f"Could not parse Excel file: {exc}")

    if not raw_sheets:
        return {
            "file_type": file_type,
            "record_count": 0,
            "preview": [],
            "filename": upload_file.filename,
        }

    sheets = _slice_dataframe_with_header(raw_sheets)

    total_records = 0
    all_preview: list[dict[str, Any]] = []
    for sheet_name, df in sheets:
        try:
            column_map = _validate_csv_schema(df)
        except ValueError:
            _logger.info(
                "Excel sheet %r: schema validation failed; skipping.",
                sheet_name,
            )
            continue
        df, dropped = _drop_malformed_rows(df, column_map)
        if dropped:
            _logger.info(
                "Excel sheet %r: dropped %d NaN-padded row(s); %d surviving.",
                sheet_name, dropped, len(df),
            )
        total_records += len(df)
        if len(all_preview) < 5:
            remaining = 5 - len(all_preview)
            all_preview.extend(
                df.head(remaining).fillna("").to_dict(orient="records")
            )

    return {
        "file_type": file_type,
        "record_count": total_records,
        "preview": all_preview,
        "filename": upload_file.filename,
    }


def parse_excel_transactions(upload_file: UploadFile) -> list[dict[str, Any]]:
    """Parse an Excel (.xlsx / .xls) bank statement into normalised
    transaction records, ACCUMULATED ACROSS ALL SHEETS.

    Phase 10: banks that export multi-account .xlsx files (often
    Sheet1=Checking, Sheet2=Savings, Sheet3=Credit Card) no longer
    see the savings-account rows silently dropped by the legacy
    ``sheet_name=0`` shortcut. Each sheet is processed through
    :func:`_slice_dataframe_with_header` + :func:`_validate_csv_schema`
    + :func:`_drop_malformed_rows` and the per-sheet record lists
    are concatenated in workbook order.

    Sheets with no valid header row are skipped (logged at INFO).
    Returns an empty list if EVERY sheet is empty / unreadable.

    Same column-normalization + schema-validation contract as
    :func:`parse_csv_transactions` — the two functions share the
    same :func:`_validate_csv_schema` and :func:`_drop_malformed_rows`
    helpers.
    """
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        raise ValueError(
            "Excel (.xlsx) support requires openpyxl. "
            "Install with: pip install openpyxl"
        )

    upload_file.file.seek(0)
    try:
        raw_sheets = pd.read_excel(upload_file.file, sheet_name=None)
    except Exception as exc:
        raise ValueError(f"Could not parse Excel file for transactions: {exc}")

    if not raw_sheets:
        return []

    sheets = _slice_dataframe_with_header(raw_sheets)

    all_records: list[dict[str, Any]] = []
    total_dropped_rows = 0
    for sheet_name, df in sheets:
        try:
            column_map = _validate_csv_schema(df)
        except ValueError:
            _logger.info(
                "Excel sheet %r: schema validation failed; skipping.",
                sheet_name,
            )
            continue
        df, dropped = _drop_malformed_rows(df, column_map)
        if dropped:
            total_dropped_rows += dropped
            _logger.info(
                "Excel sheet %r: dropped %d NaN-padded row(s).",
                sheet_name, dropped,
            )
        if df.empty:
            continue
        records = _df_to_records(df, column_map, source_label=f"Excel {sheet_name}")
        all_records.extend(records)

    if total_dropped_rows:
        _logger.info(
            "Parsed Excel %s: %d malformed row(s) dropped across sheets; "
            "%d record(s) persisted.",
            upload_file.filename, total_dropped_rows, len(all_records),
        )
    return all_records


def _df_to_records(
    df: "pd.DataFrame",
    column_map: dict[str, str],
    source_label: str = "Excel",
) -> list[dict[str, Any]]:
    """Convert a normalized DataFrame + canonical column map into the
    list-of-dicts shape consumed by the route layer. Shared between
    the Excel preview/persist paths so the per-row normalisation
    rules (date/amount coercion, blank-description placeholder,
    merchant_name canonicalization) are single-source-of-truth.
    """
    records: list[dict[str, Any]] = []
    dropped_rows = 0
    for _, row in df.iterrows():
        try:
            normalized = {}
            for column_name, canonical in column_map.items():
                value = row[column_name]
                normalized[canonical] = value

            transaction_date = _parse_date(normalized.get("date"))
            canonicals_in_use = set(column_map.values())
            if "amount" in canonicals_in_use:
                amount = _parse_amount(normalized.get("amount"))
            elif (
                "credit" in canonicals_in_use and "debit" in canonicals_in_use
            ):
                amount = (
                    _coerce_amount_or_zero(normalized.get("credit"))
                    - _coerce_amount_or_zero(normalized.get("debit"))
                )
            else:
                amount = _parse_amount(normalized.get("amount"))
            description = _canonicalize_text(normalized.get("description"))
            if not description:
                description = "Imported transaction"
        except (ValueError, TypeError) as exc:
            dropped_rows += 1
            _logger.warning(
                "Dropping malformed %s row: %s (row_index=%d, total_dropped=%d)",
                source_label, exc, row.name, dropped_rows,
            )
            continue
        records.append(
            {
                "transaction_date": transaction_date,
                "amount": amount,
                "description": description,
                "merchant_name": (
                    _canonicalize_text(normalized.get("merchant_name")) or None
                ),
                "is_pending": bool(normalized.get("is_pending", False)),
            }
        )
    return records


def parse_uploaded_statement(upload_file: UploadFile) -> dict[str, Any]:
    """Dispatch to CSV / PDF / OFX / Excel parser based on filename extension.

    Returns a dict with ``filename``, ``file_type``, ``record_count``,
    ``preview`` (first N rows for the FE), AND ``parsed_records`` (the
    full list of normalised transaction dicts so callers can persist
    without re-parsing the file a second time).

    Raises ``ValueError`` if the filename is missing or has an
    unsupported extension (only ``.csv`` + ``.pdf`` + ``.ofx`` +
    ``.qfx`` + ``.xlsx`` + ``.xls`` are supported in this release).

    Both the preview parser and the transactions parser are called
    sequentially; each seeks to position 0 internally so the second
    call re-reads the file cleanly. This eliminates the double-parse
    that ``parse_uploaded_statement_safe`` in Finlynq previously
    performed by re-reading raw bytes and dispatching a second time.
    """
    filename = upload_file.filename or ""
    lower = filename.lower()
    if lower.endswith(".csv"):
        result = parse_csv_file(upload_file)
        result["parsed_records"] = parse_csv_transactions(upload_file)
        return result
    if lower.endswith(".pdf"):
        result = parse_pdf_file(upload_file)
        result["parsed_records"] = parse_pdf_transactions(upload_file)
        result.setdefault("warnings", [])
        # Fidelity NetBenefits 401(k) statements emit synthesized period-
        # rollup rows (not individual paycheck transactions). Warn the user
        # so the UI can explain why only 3 aggregate rows appear.
        if result["parsed_records"] and any(
            "(401k period rollup)" in (r.get("description") or "")
            for r in result["parsed_records"]
        ):
            result["warnings"].append(
                "Fidelity 401k PDFs provide period summaries, not individual transactions."
            )
        return result
    if lower.endswith(".ofx") or lower.endswith(".qfx"):
        result = parse_ofx_file(upload_file)
        result["parsed_records"] = parse_ofx_transactions(upload_file)
        return result
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        result = parse_excel_file(upload_file)
        result["parsed_records"] = parse_excel_transactions(upload_file)
        return result
    raise ValueError(
        "Unsupported file format. Please upload a CSV, PDF, OFX/QFX, or "
        "Excel (.xlsx/.xls) file."
    )


# ----------------------------------------------------------------------
# Phase 8.1 — heuristic PDF → transaction parser for Fidelity 401(k)
# statements.
#
# Goal: turn Fidelity quarterly statements (which are typically text-
# layer PDFs) from preview-only into actual ``Transaction`` rows so the
# user can track their 401(k) contributions without hand-keying them.
#
# Strategy: regex-sniff lines that look like ``<date>  <description>
# <signed amount>`` and emit one normalised record per match. Lines
# that don't match are SKIPPED (no record is written) — a noisy line is
# far less harmful to the ledger than a bogus one. The same function
# runs on text-layer pdfplumber output AND on OCR-extracted text from
# the OCR fallback path, so image-only scanned statements benefit too.
#
# KNOWN LIMITATIONS (documented so future contributors know what to
# improve):
# - **Pattern C (multi-line) is NOT supported.** Lines where the date
#   is on one row and the description + amount are on the next are
#   skipped. Attaching them to the previous date risks polluting the
#   ledger with junk attributed to the wrong statement section.
# - **Bank/Plaid statements** (Chase/Amex/etc.) generally don't fit
#   Pattern A or B and will return zero records. CSV / OFX exports
#   remain the recommended path for those.
# - **Amount sniffing is heuristic.** ``$500``-style negatives, ``(500)``
#   accounting negatives, and trailing ``-`` are all recognised. Other
#   notations (e.g. ``DR 500.00`` without parens) fall through to the
#   return-None path so the row is dropped, not silently mis-typed.
# - **is_pending=False is hardcoded.** Fidelity quarterly statements
#   are retrospective (cleared transactions only), so every extracted
#   row is treated as posted. If a future bank starts sending pending
#   rows through this heuristic, plumb through a real detection.
# ----------------------------------------------------------------------

# Pattern A — Fidelity's "Activity" multi-column layout. Two dates
# (trade date + settle date) + uppercase description + signed amount +
# running balance column. The amount is matched with a negative-aware
# regex; the trailing balance is optional.
PATTERN_A_RE = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"          # date (group 1)
    r"(?:\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?"    # optional second date
    r"\s+([A-Z0-9][A-Z0-9 \-/]{2,}?)"           # uppercase description (group 2, lazy)
    r"\s+(-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"  # signed amount (group 3)
    r"(?:\s+-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)?$"  # optional balance
)

# Pattern B — single-line: ``<date> <free text description> <amount>``.
# Used for Fidelity "Transaction detail" / older one-column layouts.
PATTERN_B_RE = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)"    # date (group 1, year optional)
    r"\s+([A-Za-z0-9][A-Za-z0-9 \-/]{2,}?)"     # mixed-case description (group 2, lazy)
    r"\s+(-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)$"  # signed amount (group 3, anchored)
)

# General pattern — for non-Fidelity bank PDFs. Splits on 2+ spaces
# (the most common delimiter in text-extracted PDF statements). The
# pattern requires:
#   - A date-like token (e.g. 01/15, 01/15/2025, 2025-01-15)
#   - A free-text description (non-empty remaining middle segments)
#   - A final signed dollar amount (e.g. -4.50, $1,234.56, (87.32))
# These are far more flexible than the Fidelity patterns and will match
# many Chase / BofA / Wells Fargo / Amex text exports too.
PATTERN_GENERAL_RE = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)"    # date (group 1, flexible)
    r"\s{2,}(.+?)"                                  # description (group 2, lazy via 2+ spaces)
    r"\s{2,}(-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"  # signed amount (group 3)
    r"(?:\s+-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)?$"  # optional balance
)

# Fidelity brokerage-statement general pattern — handles the
# "Securities Bought & Sold" / "Dividends, Interest & Other Income" /
# "Deposits" / "Taxes Withheld" / "Core Fund Activity" sections of a
# Fidelity brokerage statement (NOT the 401k quarterly summary
# statement, which has no line-item transactions). The original
# PATTERN_GENERAL_RE requires 2+ spaces between tokens, but Fidelity
# uses single-space-delimited columns, so we need this
# single-space-tolerant variant.
#
# Group semantics:
#   1 — date (always ``MM/DD``; we prepend the statement-period year
#       harvested from the page header)
#   2 — description chunk (num/qty/price/CUSIP noise stripped by
#       :func:`_extract_fidelity_security`)
#   3 — transaction amount (last money token on the line; trailing
#       balance for Core Fund Activity is consumed by the optional
#       trailing-balance group at end-of-line)
#
# Real-world signs and shapes captured:
#   ``04/08 ALPHABET INC CAP STK CL A 02079K305 You Bought 0.658 $303.71500 - -$199.84``
#   ``04/01 CASH You Bought FIDELITY GOVERNMENT MONEY MARKET 1.590 $1.0000 $1.59 $45,298.91``
#   ``04/01 NVIDIA CORPORATION COM 67066G104 Dividend Received - - $1.59``
#   ``04/06 Eft Funds Received Er74630480 $4.00``
#   ``04/09 TAIWAN SEMICONDUCTOR MANUFACTURING SPON Foreign Tax Paid -$5.92``
#
# The pattern REQUIRES a trailing amount, so 3-line wraps (description
# ends mid-line, amount is on a separate line) are NOT supported — see
# the edge-case note in :func:`extract_pdf_transactions`.
FIDELITY_GENERAL_RE = re.compile(
    r"^(\d{1,2}/\d{1,2})"                       # date MM/DD (group 1)
    r"\s+(.+?)"                                  # description (group 2, lazy)
    r"\s+(-?\$?\d{1,3}(?:,\d{3})*\.\d{2})"      # amount (group 3)
    r"(?:\s+-?\$?\d{1,3}(?:,\d{3})*\.\d{2})?$"   # optional trailing balance
)

# Fidelity two-date pattern — debit card ``Trans Date Post Date ...``
# lines of a Fidelity HSA / brokerage debit card activity section. The
# second MM/DD (post date) is used as the canonical transaction date —
# this matches the bank's settled-on convention (post date is when the
# cash actually moved). When trans-date == post-date (the usual case)
# this still picks the second one without behavioural change.
FIDELITY_TWO_DATE_RE = re.compile(
    r"^(\d{1,2}/\d{1,2})"                       # trans date (group 1, ignored)
    r"\s+(\d{1,2}/\d{1,2})"                     # post date (group 2, canonical)
    r"\s+(.+?)"                                  # location/desc (group 3)
    r"\s+(-?\$?\d{1,3}(?:,\d{3})*\.\d{2})$"     # amount (group 4, anchored)
)

# Bank of America / Credi year-end summary line pattern. Matches the
# canonical ``MM/DD/YY <merchant> <CITY>, <ST> <amount>[CR]`` layout
# that the BofA "Year-End Summary" credit-card PDF emits on every
# category page. The amount is ALWAYS the trailing money token and an
# optional ``CR`` suffix marks credit/refund rows (which the
# dispatch helper turns into a negative ``amount``).
#
# Lazy ``(.+?)`` for the description+location field handles the
# comma between ``<CITY>`` and ``<ST>`` (e.g. ``LYNNWOOD, WA``) and
# the fact that some merchant tokens (phone numbers, store IDs,
# ``TST*``, ``SQ *`` prefixes) include digits/digits-with-dashes
# that must NOT be mistaken for the amount. The regex's
# ``(?::\d{1,3}|(?:,\d{3})*\.\d{2})?`` money shape is anchored at
# ``$`` so only the trailing money token can satisfy it — phone
# numbers in the middle of the description are harmless.
#
# Phase 10.1b example lines that match:
#   ``01/13/25 NORDSTROM-RACK 0015 LYNNWOOD, WA 160.27``
#   ``01/13/25 NORDSTROM-RACK 0015 LYNNWOOD, WA 99.50CR``
#   ``01/09/25 PAPA JOHN'S 2213 425-379-6262, WA 16.46``
#   ``12/16/25 EQT*Ambetter 866-5498038, MO 1,868.73``
#
# Year handling: dates are emitted as ``MM/DD/YY`` (``25`` = 2025
# via pd.to_datetime's two-digit-year convention). For Credi PDFs
# the year is already embedded correctly, but :func:`_build_pdf_date`
# still consumes the standard :func:`_harvest_statement_year` output
# (``January 1, 2025, and December 31, 2025`` -> ``2025``) as a
# backstop in case the user's bank ever omits the two-digit year.
CREDI_YEAR_END_RE = re.compile(
    r"^"
    r"(\d{1,2}/\d{1,2}/\d{2,4})"               # date MM/DD/YY[YY] (group 1)
    r"\s+"
    r"(.+?)"                                    # merchant+location (group 2, lazy)
    r"\s+"
    r"(-?\$?\d{1,3}(?:,\d{3})*\.\d{2})"          # amount (group 3, trailing money)
    r"(CR)?"                                     # optional credit/refund marker (group 4)
    r"\s*"
    r"$",
    re.IGNORECASE,
)


# Section-header detector. Two flavours:
#
# (a) Short header line starting with one of the table-anchor
#     keywords (``Date``, ``Transaction``, ``Settlement Date`` etc.):
#     skip the entire line so it doesn't get appended to a previous
#     record's description via the continuation-line path.
#
# (b) Inline table-header line whose token set contains AT LEAST
#     TWO of the same table-anchor words (e.g. ``Date Security Name
#     CUSIP Description Quantity Price Cost Amount`` on page 8,
#     ``Trans. Date Post Date Location Reference/Description Amount``
#     on page 19): skip because every column word would otherwise
#     leak into a record's description when the same page's first
#     transaction line follows immediately.
_SECTION_HEADER_RE = re.compile(
    r"^(Date|Description|Amount|Balance|Settlement|Symbol/CUSIP|"
    r"Transaction|Trans|Security|Security Name|Reference|Quantity|"
    r"Price|Cost|CUSIP|Post Date|Trans\.?\s+Date|"
    r"Location|Symbol)\b(\s+\w[\w\s/.\-]*)?$",
    re.IGNORECASE,
)

# Inline table-header detector — a line containing AT LEAST TWO of
# the canonical activity-table column words. Used alongside
# ``_SECTION_HEADER_RE`` so the longer multi-word header lines like
# ``Date Security Name CUSIP Description Quantity Price Cost Amount``
# or ``Settlement Symbol/CUSIP Transaction Date Security Name …``
# are flagged as table headers even when they don't START with a
# single-section keyword.
_INLINE_TABLE_HEADER_RE = re.compile(
    r"\b(Date|Settlement|Security|CUSIP|Cusip|Quantity|Qty|Price|"
    r"Cost|Amount|Description|Trans\.?\s+Date|Post Date|Reference|"
    r"Location|Symbol|Transaction)\b.*\b(Date|Settlement|Security|"
    r"CUSIP|Cusip|Quantity|Qty|Price|Cost|Amount|Description|"
    r"Post Date|Reference|Location|Symbol|Transaction)\b",
    re.IGNORECASE,
)

# Money-token tail detector. Used in the continuation-line path to
# decide whether a line that did NOT match any pattern is more likely
# noise (e.g. ``Total Deposits $1,022.00``) or a wrap line for the
# previous record's security name (e.g. ``MARKET`` after
# ``... 12/31 FIDELITY GOVERNMENT MONEY``).
_MONEY_TAIL_RE = re.compile(r"-?\$?\d{1,3}(?:,\d{3})*\.\d{2}$")

# Phase 10.1c — Fidelity NetBenefits 401(k) period-summary
# pivot-table extraction. Used by
# :func:`_extract_fidelity_401k_rollups` to identify the section
# boundaries and the column-break marker (vs. the unrelated
# ``Your Account Activity`` heading on a brokerage statement).
#
# Why module-level: the section-state machine tests for
# positive/negative header detection benefit from these being
# importable as standalone regex constants, and stay compiled once
# (per :mod:`re` cache) instead of being rebuilt inside the
# extraction loop.
_FIDELITY_401K_ACTIVITY_HEADER_RE = re.compile(
    r"^\s*Your\s+Account\s+Activity\s+By\s+Fund\s*$",
    re.IGNORECASE,
)

# Period start date: ``Statement Period: 01/01/2026 to 05/29/2026``.
# The year may be 2-digit OR 4-digit; the helper
# :func:`_build_pdf_date` upgrades a ``MM/DD`` token against the
# document-level ``statement_year`` produced by
# :func:`_harvest_statement_year`. Using :func:`re.search`
# (NOT :func:`re.match`) because ``Statement Period:`` can appear
# mid-line if a future bank template reformats the section
# header — the leading whitespace is not load-bearing.
_FIDELITY_401K_PERIOD_RE = re.compile(
    r"Statement\s+Period:\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
    re.IGNORECASE,
)

# Column-break marker: standalone word ``Total`` preceded by
# ``Activity`` (or at line start) and at end of line, used with
# :func:`re.search`. The ``Activity`` prefix disambiguates from a
# fund name like ``Total US Stock Index`` (which contains ``Total``
# as the FIRST word — would still need ``Activity`` before it).
# Tightening to ``(?:Activity\s+)?Total\s*$`` reduces false
# positives on a hypothetical bank line ending with bare ``Total``.
_STANDALONE_TOTAL_AT_EOL_RE = re.compile(
    r"(?:^|\s)Activity\s+Total\s*$",
    re.IGNORECASE,
)

# Activity row: any of the 6 pivot labels + 2+ money tokens
# anchored at EOL. Sign prefix order is ``-?\$?`` (NOT ``\$?-?``)
# AND NOT literal ``-\$?`` — the ``-`` MUST BE OPTIONAL (``-?``) so
# both ``-$854.24`` AND ``$499.40`` / ``9,988.62`` match. A literal
# ``-`` here (an earlier draft's bug caught by code review) silently
# excludes every all-positive row, which on Page 5 means
# ``Employee Contributions ... $9,988.62`` — the canonical cash-flow
# row — never matches and 0 records are returned.
#
# Money tokens separated by 1+ whitespace. The ``(?P<ms>...)``
# capture grabs ALL money tokens; the helper takes the LAST one
# (period-total column) via ``re.findall`` for the per-row amount.
_FIDELITY_401K_ACTIVITY_RE = re.compile(
    r"^(?P<label>Employee\s+Contributions|Employer\s+Contributions|"
    r"Dividends|Beginning\s+Balance|Ending\s+Balance|"
    r"Change\s+in\s+Market\s+Value)"
    r"\s+"
    r"(?P<ms>"
    r"(?:-?\$?\d{1,3}(?:,\d{3})*\.\d{2}\s+){1,}"
    r"-?\$?\d{1,3}(?:,\d{3})*\.\d{2}"
    r")\s*$",
    re.IGNORECASE,
)

# Set of pivot-table labels that represent a CASH FLOW (kEEP for
# extraction). The complement — Beginning Balance, Ending Balance,
# Change in Market Value — are STATE, not flow, and are explicitly
# dropped.
_FIDELITY_401K_KEEP_LABELS = frozenset({
    "EMPLOYEE CONTRIBUTIONS",
    "EMPLOYER CONTRIBUTIONS",
    "DIVIDENDS",
})


# Fidelity category keywords → human-friendly descriptions. A substring
# match (case-insensitive on the uppercased description) qualifies a
# row. The (401k) suffix disambiguates from broker side of the same
# account.
_FIDELITY_DESC_MAP: dict[str, str] = {
    "EMPLOYEE PRE-TAX": "Employee Pre-Tax (401k)",
    "EMPLOYEE ROTH": "Employee Roth (401k)",
    "EMPLOYER MATCH": "Employer Match (401k)",
    "EMPLOYER MATCHING": "Employer Match (401k)",
    "ROLLOVER": "Rollover (401k)",
    "VESTING": "Vesting (401k)",
    "EXCHANGE": "Fund Exchange (401k)",
}


def _harvest_statement_year(text_lines: list[str]) -> str | None:
    """Scan the first 30 non-blank lines for a ``Month YYYY - Month YYYY``
    statement-period header (e.g. ``April 1, 2026 - April 30, 2026``) and
    return the END-year (``"2026"``). Returns ``None`` if no such
    header is found.

    Used by :func:`extract_pdf_transactions` to backfill the year on a
    line whose date is ``MM/DD`` only (the Fidelity brokerage
    activity tables emit dates without a year — they rely on the
    document-level statement period to disambiguate). Without this,
    every Fidelity brokerage transaction would be parsed with a
    pandas Timestamp in the year ``1900`` (the pandas default for an
    unparseable partial date), which silently corrupts the ledger by
    backdating the row by ~125 years.

    Implementation: look for ``<MonthWord> <Day>,? <4-digit-year>``
    in any of the first 30 lines. We use the END date year because
    that's the most-recent year in the period — if the user uploads
    a January statement in early February, we want rows dated
    ``01/27`` to be 2026, not some earlier year.
    """
    month_word = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    pattern = re.compile(
        rf"{month_word}\s+\d{{1,2}},?\s+(\d{{4}})",
        re.IGNORECASE,
    )
    matches_so_far: list[str] = []
    for line in text_lines[:30]:
        # Defensive: pdfplumber / OCR / upstream callers occasionally
        # emit non-string tokens (e.g. an int page number or a numeric
        # cell). Coerce to str so re.search doesn't raise
        # ``TypeError: expected string or bytes-like object`` and 500
        # the whole upload.
        if not isinstance(line, str):
            line = str(line)
        m = pattern.search(line)
        if m:
            matches_so_far.append(m.group(1))
    # Return the LAST year found (the statement-period ending year;
    # the "April 1, 2026 - April 30, 2026" line has two valid
    # matches and we want the END one).
    if matches_so_far:
        return matches_so_far[-1]
    # Fallback 1: try "Statement Period: 01/01/2026 to 05/29/2026"
    # (Fidelity 401k quarterly layout).
    # Coerce every token to str before joining — callers may pass a mix
    # of str/int/float tokens (e.g. from OCR or upstream forwarders).
    joined = "\n".join(str(line) for line in text_lines[:30])
    m2 = re.search(r"Statement Period:\s*\d{1,2}/\d{1,2}/(\d{4})", joined)
    if m2:
        return m2.group(1)
    # Fallback 2: a bare 4-digit year token (e.g. an int page number or
    # a standalone year line). This lets regression tests feed a year
    # without a full statement-period header.
    for line in text_lines[:30]:
        s = str(line).strip()
        m3 = re.match(r"^(\d{4})$", s)
        if m3:
            return m3.group(1)
    return None


def _build_pdf_date(date_str: str, statement_year: str | None) -> pd.Timestamp | None:
    """Parse a PDF date token, optionally prepending a statement-year
    discovered by :func:`_harvest_statement_year`.

    Short-form ``MM/DD`` (no year) is upgraded to ``MM/DD/<year>`` if a
    statement-year is available. Long-form ``MM/DD/YYYY`` is parsed
    as-is. Returns ``None`` for inputs that ``pd.to_datetime`` can't
    handle — the caller drops the row.
    """
    if not date_str:
        return None
    if statement_year and re.match(r"^\d{1,2}/\d{1,2}$", date_str):
        return pd.to_datetime(f"{date_str}/{statement_year}", errors="coerce")
    return pd.to_datetime(date_str, errors="coerce")


def _extract_fidelity_security(raw_text: str) -> str:
    """Extract a clean ``"SECURITY (ACTION)"`` description from a Fidelity
    brokerage activity-line chunk that may include CUSIP, qty, price,
    CUSIP-symbol, etc.

    Strategy:
    1. Find the action keyword (You Bought|You Sold|Dividend Received|
       Reinvestment|Eft Funds Received|Foreign Tax Paid|Interest Earned)
       anywhere in the line.
    2. Treat everything BEFORE the action as the security/location.
    3. Strip CUSIP-shaped tokens (8-12 digit alphanumeric, with optional
       letter at end) and reference numbers (``Er\d+``, ``FDIC\d+``)
       from the security portion.
    4. Drop a leading ``CASH`` token from Core Fund Activity rows.
    5. Output ``"<SECURITY> (<ACTION>)"`` or just ``"<ACTION>"`` if
       the security portion was empty after cleanup.

    If no action keyword is found, falls back to a whitespace-collapsed,
    title-cased version of the chunk as-is. The fallback is INTENTIONAL
    rather than raising — a missing keyword doesn't mean the row is
    junk, just that the layout drifted from the known Fidelity
    templates (Phase 11+ should add a richer keyword list).
    """
    text = " ".join((raw_text or "").strip().split())
    action_match = re.search(
        r"\b(You Bought|You Sold|Dividend Received|Reinvestment|"
        r"Eft Funds Received|Foreign Tax Paid|Interest Earned)\b",
        text,
        re.IGNORECASE,
    )
    if not action_match:
        # No action keyword found — best-effort cleanup.
        text = re.sub(r"\b\d{8,12}[A-Z]?\b", "", text)
        text = re.sub(r"\bE[rR]\d+\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text.title() or "Imported transaction"
    action = action_match.group(1)
    before = text[:action_match.start()].strip()
    # Strip CUSIPs from the security portion. A CUSIP is 9 chars:
    #   - 6-char IS issuer (alphanumeric — e.g. ``02079K``)
    #   - 2-char   issue number (alphanumeric — e.g. ``30``)
    #   - 1-char   check digit (always a digit — e.g. ``5``)
    # Examples: ``02079K305``, ``78462F103``, ``46625H100``.
    # The simple ``\d{8,12}`` strip misses these because issuer
    # position 6 is often a letter (``02079K``, ``78462F``). The
    # canonical-shape regex matches alphanumeric issuer + alphanumeric
    # issue + digit check; we keep the pure-digit fallback so older
    # all-numeric CUSIPs (rare but possible on US Treasury securities)
    # aren't orphaned.
    before = re.sub(r"\b[A-Z0-9]{6}[A-Z0-9]{2}\d\b", "", before)
    before = re.sub(r"\b\d{8,12}\b", "", before)
    before = re.sub(r"\bE[rR]\d+\b", "", before, flags=re.IGNORECASE)
    before = re.sub(r"\bF[Dd][Ii][Cc]\d+\b", "", before)
    # Drop a leading ``CASH`` (Core Fund Activity token) — it's noise.
    before = re.sub(r"^CASH\s+", "", before)
    before = " ".join(before.split()).strip()
    if before:
        return f"{before.title()} ({action})"
    return action


def _normalize_amount(raw: str) -> float | None:
    """Parse a noisy amount string into a signed float.

    Recognises ``-500.00``, ``-$500``, ``(500.00)``, ``$1,234.56``,
    ``$500.00-``. Returns ``None`` (so the caller can skip the row) for
    unparseable input; an empty / zero-only string is also ``None`` so
    a regex-attraction of balance/header text never produces a junk
    transaction.
    """
    if not raw:
        return None
    s = raw.strip().upper()
    is_negative = (
        s.startswith("-")
        or s.endswith("-")
        or (s.startswith("(") and s.endswith(")"))
    )
    digits = re.sub(r"[^\d\.]", "", s)
    if not digits or digits == ".":
        return None
    try:
        value = float(digits)
    except ValueError:
        return None
    if value == 0.0:
        return None
    return -value if is_negative else value


def _parse_pdf_date(raw: str) -> pd.Timestamp | None:
    """Parse a date string from a Fidelity PDF line.

    Returns a ``pandas.Timestamp`` (NOT a stdlib ``datetime``) for
    consistency with the existing ``_parse_date`` helper used by the
    CSV / OFX paths. Mixing the two types across upload sources was
    the root cause of an inter-parser drift bug caught by code
    review — the SQLAlchemy ``Column(DateTime)`` coerces both but
    JSON serialisation, ORM attribute comparison, and tests assume a
    single type. Keep this returning ``pd.Timestamp`` to match.

    Falls back to ``pd.to_datetime`` for unusual formats (e.g. ISO
    ``2025-01-15``) and returns ``None`` for inputs the pandas
    resolver can't handle. The wrapper function will then skip the
    row so we never write a transaction with a null date. A debug
    log is emitted on failure so an operator can see why a row was
    silently dropped.
    """
    if not raw:
        return None
    try:
        return pd.to_datetime(raw)
    except Exception as exc:
        _logger.warning(
            "Could not parse PDF date %r: %s — dropping Fidelity row",
            raw, exc,
        )
        return None


def _normalize_description(raw: str) -> str:
    """Clean + canonicalise a raw description string.

    - collapses internal whitespace,
    - title-cases generic descriptions,
    - maps Fidelity keywords to a friendly human label (so the UI
      and CSV exports distinguish "Employee Pre-Tax (401k)" from
      a regular bank "EMPLOYEE PRE-TAX" string).
    """
    cleaned = " ".join(raw.strip().split())
    upper = cleaned.upper()
    for keyword, friendly in _FIDELITY_DESC_MAP.items():
        if keyword in upper:
            return friendly
    return cleaned.title()


def _canonicalize_text(raw: Any) -> str:
    """Canonicalise a CSV text cell for persistence (no default label).

    Used by both ``description`` AND ``merchant_name`` to handle the
    three messy shapes ``pd.read_csv`` produces for blank fields:
    ``None``/``np.nan`` / whitespace-only / real string. Returns ``""``
    for the first two so the per-row caller can decide its own
    fallback (``"Imported transaction"`` for description, ``None`` for
    merchant_name). The same helper prevents the
    ``str(np.nan).strip() == "nan"`` footgun on merchant_name.

    Companion to :func:`_normalize_description` (the Fidelity PDF
    path's keyword-mapping helper). Pair presence documented via
    shared docstring so future contributors don't reinvent the
    ``pd.isna`` vs empty-string distinction between the two ingest
    sources. **Don't** change the NaN handling without also updating
    ``test_parse_csv_preview_keeps_blank_description_legitimate_row``.
    """
    if raw is None or pd.isna(raw):
        return ""
    return str(raw).strip()


# Backwards-compatible alias — the public API contract docs and the
# Phase 9 followup-#4 commit both refer to ``_normalize_csv_description``
# (the parallel to the Fidelity-path ``_normalize_description``). The
# impl lives under the more-precise ``_canonicalize_text`` name so the
# helper's no-default-label contract is explicit; this alias keeps
# outside-doc references working without re-naming the implementation.
_normalize_csv_description = _canonicalize_text


def _extract_fidelity_401k_rollups(
    text_lines: list[str],
) -> list[dict[str, Any]]:
    """Phase 10.1c — Fidelity NetBenefits 401(k) period-summary
    pivot-table extraction.

    A Fidelity NetBenefits quarterly statement (``Statement Details``
    PDF) places the period totals in a cross-tabulation on the
    ``Your Account Activity By Fund`` page (page 5 in the test
    fixture). Rows are Activity types (``Employee Contributions``,
    ``Employer Contributions``, ``Dividends``, ``Beginning Balance``
    etc.) and columns are the funds held. The LAST column is the
    period TOTAL — but only on the SECOND half of the table (after
    the column break). Picking the LAST money token WITHOUT
    detecting the column break would invent wrong amounts out of
    the FIRST half of the table.

    State machine:
    
    - Section entry: a line matching
      :data:`_FIDELITY_401K_ACTIVITY_HEADER_RE` (``Your Account
      Activity By Fund``) flips ``in_section = True``.
    - Period start: any line anywhere on the document that
      contains ``Statement Period: <start> to <end>`` updates the
      canonical period start. The year on ``<start>`` may be
      2-digit; :func:`_build_pdf_date` upgrades it against the
      document-level statement_year.
    - Column break: a line ending with the standalone ``Total``
      marker (e.g. ``Activity Total``) flips
      ``in_total_phase = True``. Before this point, rows in this
      section are per-fund-only (4 fund columns, no Total) and
      MUST NOT be extracted.
    - Section exit: any line starting with the next major heading
      (``Your Account Information`` or ``Additional Fund
      Information``) flips ``in_section = False``.

    Records emitted: only Activity rows with a CASH-FLOW label
    (``Employee Contributions``, ``Employer Contributions``,
    ``Dividends``) AND a positive non-zero LAST money token AND a
    harvested period start. Skip labels (``Beginning Balance``,
    ``Ending Balance``, ``Change in Market Value``) are explicitly
    dropped — they are state, not flow.

    Called from the BOTTOM of :func:`extract_pdf_transactions` so
    the existing per-pattern chain (PATTERN_A, PATTERN_B,
    PATTERN_GENERAL, FIDELITY_GENERAL, FIDELITY_TWO_DATE,
    CREDI_YEAR_END) gets first crack at the text. None of those
    patterns match the 401k section lines (they all require a
    leading date token; the 401k labels are dekam-case + multiple
    money tokens), so the chase is contention-free.

    Args:
        text_lines: the same flat list of pdfplumber-extracted
            lines that :func:`extract_pdf_transactions` is given.

    Returns:
        List of 0–6 normalised record dicts in the canonical
        shape (``transaction_date`` / ``amount`` / ``description``
        / ``merchant_name`` / ``is_pending``). A statement that
        has no NetBenefits ``Account Activity By Fund`` page
        (``0`` records) — most documents — is the common case.
    """
    statement_year = _harvest_statement_year(text_lines)
    period_start: pd.Timestamp | None = None
    in_section = False
    in_total_phase = False
    records: list[dict[str, Any]] = []

    for raw_line in text_lines:
        if not isinstance(raw_line, str):
            raw_line = str(raw_line)
        line = raw_line.strip()
        if not line:
            continue

        # Section entry — "Your Account Activity By Fund".
        if _FIDELITY_401K_ACTIVITY_HEADER_RE.match(line):
            in_section = True
            _logger.debug(
                "401k activity section opened at: %r", line,
            )
            continue

        # Section exit — the next major heading closes it. We
        # intentionally do NOT close the section on every "Your"
        # line so a stray "Your Investment Direction" header on a
        # preceding page (Page 4) doesn't accidentally end a
        # section that hasn't yet opened.
        if in_section and (
            line.startswith("Your Account Information")
            or line.startswith("Additional Fund Information")
        ):
            in_section = False
            _logger.debug(
                "401k activity section closed by: %r", line,
            )
            continue

        # Period start — harvest anywhere on the document, so a
        # ``Statement Period:`` line on Page 1 (which precedes the
        # ``Account Activity By Fund`` section on Page 5) is
        # captured in time for Page 5 extraction. Multi-occurrence
        # is safe — every Fidelity NetBenefits statement uses the
        # same dates for every "Statement Period:" marker on the
        # document so the LAST one is the same value as the FIRST.
        m_period = _FIDELITY_401K_PERIOD_RE.search(line)
        if m_period:
            candidate = _build_pdf_date(
                m_period.group(1), statement_year,
            )
            if candidate is not None:
                period_start = candidate
            continue

        # Column-break marker — only flip ONCE (idempotent within
        # the section). Lines like ``Activity Total`` (page 5 L025)
        # match; ``Activity`` (L018) does not because the regex
        # requires ``Total`` at end-of-line.
        if (
            in_section
            and not in_total_phase
            and _STANDALONE_TOTAL_AT_EOL_RE.search(line)
        ):
            in_total_phase = True
            _logger.debug(
                "401k activity total-phase opened by: %r", line,
            )
            continue

        # Activity row — extract only when BOTH gates are open.
        if in_section and in_total_phase:
            m = _FIDELITY_401K_ACTIVITY_RE.match(line)
            if not m:
                continue
            label = m.group("label")
            if label.upper() not in _FIDELITY_401K_KEEP_LABELS:
                # Beginning/Ending Balance, Change in Market Value.
                # State, not flow — never a transaction.
                continue
            if period_start is None:
                _logger.debug(
                    "401k activity row %r matched but period_start "
                    "unavailable; dropping (would otherwise attach "
                    "to today()).", line,
                )
                continue
            # The amount column is the LAST money token in the
            # match. ``-?\$?`` ordering matters here: ``\$?-?``
            # would not match ``-$854.24`` (real Change-in-MV rows
            # use this format on Page 5 L031).
            money_tokens = re.findall(
                r"-?\$?\d{1,3}(?:,\d{3})*\.\d{2}", m.group("ms"),
            )
            if not money_tokens:
                continue
            amount = _normalize_amount(money_tokens[-1])
            if amount is None or amount <= 0:
                # ``Change in Market Value`` rows can legitimately
                # be negative (``-$854.24`` on Page 5 L031) but
                # Change is in the skip label set above so we
                # never reach this branch with it. A zero
                # ``_normalize_amount`` (zero-total employee
                # contributions for a quarter with no activity)
                # is also dropped here.
                continue
            record = {
                "transaction_date": period_start,
                "amount": amount,
                # ``Employee Contributions`` / ``Employer
                # Contributions`` / ``Dividends`` title-cased so
                # the consumer sees the same label as Page 1
                # prose. The ``(401k period rollup)`` suffix is
                # the honest marker that this is a synthesized,
                # per-quarter aggregate — NOT a per-paycheck line.
                "description": f"{label.title()} (401k period rollup)",
                "merchant_name": None,
                "is_pending": False,
            }
            records.append(record)
            _logger.debug(
                "401k activity extracted: %r -> amount=%s date=%s",
                line, amount, period_start,
            )

    return records


def extract_pdf_transactions(text_lines: list[str]) -> list[dict[str, Any]]:
    """Heuristic extraction of transaction lines from PDF text output.

    Pure function: takes a flat list of text lines (output of either
    ``parse_pdf_file`` text-layer extraction or ``ocr_parse_statement``
    OCR), returns a list of normalised transaction records matching the
    shape produced by ``parse_csv_transactions`` / ``parse_ofx_transactions``.

    Strategy (tried in order for each line):
    1. **Fidelity 401k Pattern A** — multi-column layout with two dates
       + uppercase description + signed amount + optional trailing balance.
    2. **Fidelity 401k Pattern B** — single-line ``<date> <description> <amount>``.
    3. **General pattern** — splits on 2+ spaces and looks for date +
       free-text description + signed amount (handles many Chase /
       BofA / Wells Fargo / Amex text exports with 2+ space columns).
    4. **Fidelity brokerage general** — covers a Fidelity brokerage
       statement's activity sections (Securities Bought & Sold,
       Dividends/Reinvestments, Deposits, Core Fund Activity, Taxes
       Withheld etc.). Single-space-delimited columns, so the 2+
       spaces heuristic of the general pattern is too strict. Uses
       :func:`_harvest_statement_year` + :func:`_build_pdf_date` to
       backfill the year on ``MM/DD`` dates.
    5. **Fidelity two-date** — debit card "Trans Date Post Date ..."
       rows (two ``MM/DD`` at the start, then location + amount). Post
       date is treated as canonical.
    6. **BofA / Credi year-end summary** — covers the Bank of
       America / Credi credit-card year-end summary PDF layout:
       ``MM/DD/YY <merchant> <CITY>, <ST> <amount>[CR]``. Lazy regex
       backtracks to find the trailing money token, and the
       ``CR`` suffix is converted to a negative amount so credits /
       refunds surface as outflow reductions. The
       ``January 1, 2025, and December 31, 2025`` header on the
       first page lets :func:`_harvest_statement_year` cross-check
       the two-digit year, and pd.to_datetime resolves ``25`` to
       ``2025`` so dates land in the right year without intervention.

    Phase 10+: lines that don't match any pattern are checked for
    **continuation** (``<no date> + <no money-tail>`` AND a previous
    record exists) — the line's text is appended to the previous
    record's description so wrap-around security names like
    ``04/30 FIDELITY GOVERNMENT MONEY\nMARKET`` survive instead of
    dropping noise.

    Lines that don't match AND have neither date nor money at end are
    silently dropped. Lines that START with a date but failed all
    patterns emit a DEBUG breadcrumb so an operator can debug
    "missing rows" runs.
    """
    records: list[dict[str, Any]] = []
    statement_year = _harvest_statement_year(text_lines)
    last_record: dict[str, Any] | None = None

    for raw_line in text_lines:
        # Defensive: same coercion as in _harvest_statement_year —
        # callers (OCR, pdfplumber, forwarders) can hand us non-string
        # tokens. ``.strip()`` and the regex matchers below all assume
        # str, so coerce first and skip empties.
        if not isinstance(raw_line, str):
            raw_line = str(raw_line)
        line = raw_line.strip()
        if not line:
            continue
        # Skip short all-caps section headers like ``DATE``,
        # ``SETTLEMENT DATE``, ``TRANSACTION`` etc. that anchor most
        # Fidelity activity tables. Without this skip, a line like
        # ``Security Name CUSIP Description Quantity Price Cost Amount``
        # could be mis-classified by the continuation-line path as a
        # wrap-around for the previous record's description.
        if (
            (
                _SECTION_HEADER_RE.match(line)
                or _INLINE_TABLE_HEADER_RE.search(line)
            )
            and len(line) <= 120
        ):
            continue

        # Try the existing regex set first (no behaviour change vs.
        # prior version of this function on lines PATTERN_A/B/GENERAL
        # already matched).
        match_a = PATTERN_A_RE.match(line)
        match_b = PATTERN_B_RE.match(line) if match_a is None else None
        match_general = (
            PATTERN_GENERAL_RE.match(line)
            if (match_a is None and match_b is None)
            else None
        )
        # Then the new Fidelity-specific patterns. Run only if no
        # prior pattern matched (keeps the existing 401k quarterly
        # path byte-identical for lines PATTERN_A/B already handle).
        match_fid = (
            FIDELITY_GENERAL_RE.match(line)
            if (match_a is None and match_b is None and match_general is None)
            else None
        )
        match_two = (
            FIDELITY_TWO_DATE_RE.match(line)
            if (
                match_a is None
                and match_b is None
                and match_general is None
                and match_fid is None
            )
            else None
        )
        # Phase 10.1b — BofA / Credi year-end summary layout. Tried
        # last (Fidelity patterns have higher specificity and most
        # Credi lines don't fit either's column shape). Lazy
        # backtracking finds the trailing money token so the
        # merchant+location fields absorb any embedded commas /
        # phone numbers WITHOUT mis-picking them as amounts.
        match_credi = (
            CREDI_YEAR_END_RE.match(line)
            if (
                match_a is None
                and match_b is None
                and match_general is None
                and match_fid is None
                and match_two is None
            )
            else None
        )

        if (
            match_a is None
            and match_b is None
            and match_general is None
            and match_fid is None
            and match_two is None
            and match_credi is None
        ):
            # No pattern matched. Debug breadcrumb + continuation logic.
            if _DATE_PREFIX_RE.match(line):
                _logger.debug(
                    "PDF line starts with date but no pattern matched: %r",
                    line,
                )
                continue
            # Continuation: previous record exists AND this line has
            # NEITHER a date at the start NOR a money-amount tail.
            # Append to the previous record's description (handles
            # Fidelity's 2-line wrap-around for long security names).
            # Skip lines ending with a money token — those are
            # section-totals like ``Total Deposits $1,022.00`` which
            # would pollute the description with noise.
            if (
                last_record is not None
                and not _MONEY_TAIL_RE.search(line)
                and len(line) <= 80
            ):
                last_record["description"] += " " + line
            continue

        # We have a match. Decide which pattern matched and pull
        # group semantics accordingly.
        date_str: str
        desc_str: str
        amt_str: str
        if match_a is not None:
            date_str, desc_str, amt_str = (
                match_a.group(1), match_a.group(2), match_a.group(3),
            )
            description = _normalize_description(desc_str)
        elif match_b is not None:
            date_str, desc_str, amt_str = (
                match_b.group(1), match_b.group(2), match_b.group(3),
            )
            description = _normalize_description(desc_str)
        elif match_general is not None:
            date_str, desc_str, amt_str = (
                match_general.group(1),
                match_general.group(2),
                match_general.group(3),
            )
            description = " ".join(desc_str.strip().split()).title()
        elif match_fid is not None:
            date_str = match_fid.group(1)
            desc_str = match_fid.group(2)
            amt_str = match_fid.group(3)
            description = _extract_fidelity_security(desc_str)
        elif match_two is not None:
            # Two-date pattern: post date is canonical.
            date_str = match_two.group(2)
            desc_str = match_two.group(3)
            amt_str = match_two.group(4)
            description = _extract_fidelity_security(desc_str)
        else:
            assert match_credi is not None
            # Phase 10.1b — BofA / Credi year-end summary layout.
            # The trailing ``CR`` suffix marks credit/refund rows;
            # the per-row branch negates the amount so the sign
            # convention lands negative (matches credit-card
            # convention where sales are + and refunds are -).
            date_str = match_credi.group(1)
            desc_str = match_credi.group(2)
            amt_str = match_credi.group(3)
            cr_suffix = match_credi.group(4) is not None
            description = (
                " ".join(desc_str.strip().split()).title()
                or "Imported transaction"
            )
            full_date = _build_pdf_date(date_str, statement_year)
            amount = _normalize_amount(amt_str)
            if cr_suffix and amount is not None:
                amount = -abs(amount)
            if full_date is None or pd.isna(full_date) or amount is None:
                continue
            record = {
                "transaction_date": full_date,
                "amount": amount,
                "description": description,
                "merchant_name": None,
                "is_pending": False,
            }
            records.append(record)
            last_record = record
            continue

        full_date = _build_pdf_date(date_str, statement_year)
        amount = _normalize_amount(amt_str)

        if full_date is None or pd.isna(full_date) or amount is None:
            continue

        record = {
            "transaction_date": full_date,
            "amount": amount,
            "description": description,
            "merchant_name": None,
            "is_pending": False,
        }
        records.append(record)
        last_record = record

    # Phase 10.1c — Fidelity NetBenefits 401(k) period-summary
    # pivot-table extraction. Runs AFTER the existing pattern
    # chain so brokerage / Credi / general PDFs are unaffected.
    # The helper has its own scoped state machine
    # (:func:`_extract_fidelity_401k_rollups`) so it cannot pick
    # up lines from outside the ``Your Account Activity By Fund``
    # section even when the document has dozens of unrelated
    # money lines earlier.
    records.extend(_extract_fidelity_401k_rollups(text_lines))
    return records


def parse_pdf_transactions(upload_file: UploadFile) -> list[dict[str, Any]]:
    """Open an uploaded PDF and run the Fidelity 401(k) heuristic.

    Phase 10.1b update: the prior Phase 10 logic auto-rejected any
    PDF containing ``year-end summary`` / ``annual summary`` text.
    That reject was wrong — those phrases are the canonical Bank
    of America / Credi year-end-summary exporter's identifier, and
    rejecting them silently zeroed out the very file the user wants
    to import. The auto-reject is REMOVED; :data:`CREDI_YEAR_END_RE`
    inside :func:`extract_pdf_transactions` is the new handler for
    the layout. ``year-to-date`` was always excluded from the
    reject (legitimate quarterly YTD columns), and stays excluded.
    Duplicate-import protection (year-end recap on top of monthly
    statements) is a per-DB-row concern that belongs in the
    application's unique-key / hash-id layer (Phase 11+), not in
    the parser.

    Re-opens with pdfplumber, extracts all non-blank text lines
    across every page, then delegates to ``extract_pdf_transactions``.

    Returns an empty list (rather than raising) if pdfplumber
    rejects the file — the route layer treats ``saved_transactions
    == 0`` as a preview-only batch and the UI surfaces a friendly
    message.
    """
    upload_file.file.seek(0)
    try:
        with pdfplumber.open(upload_file.file) as pdf:
            text_lines: list[str] = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_lines.extend(
                    [line.strip() for line in page_text.splitlines() if line.strip()]
                )
    except Exception:
        return []

    return extract_pdf_transactions(text_lines)
