"""Phase 39 — portfolio holdings route.

POST /api/holdings/import — import a Fidelity Portfolio Positions CSV
    or a Robinhood holdings PDF.
GET  /api/holdings/        — list all holdings for the current user.
POST /api/holdings/refresh-prices — fetch live quotes from Finnhub.
"""
import csv
import io
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

import pdfplumber
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models import Account, Holding, ImportBatch
from app.routes.shared import (
    get_or_create_family_member_self,
    get_or_create_institution,
    get_or_create_local_user,
)
from app.schemas import (
    HoldingManualCreate,
    HoldingResponse,
    HoldingUpdate,
    PortfolioAccountValuation,
    PortfolioHoldingValuation,
    PortfolioImportResponse,
    PortfolioTypeValuation,
    PortfolioValuationSummary,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/holdings", tags=["holdings"])

# ---- Portfolio CSV column index (by normalized header name) ----

_PORTFOLIO_COLUMNS = {
    "account_number": "Account Number",
    "account_name": "Account Name",
    "symbol": "Symbol",
    "description": "Description",
    "quantity": "Quantity",
    "last_price": "Last Price",
    "current_value": "Current Value",
    "cost_basis_total": "Cost Basis Total",
    "type": "Type",
}


# ----------------------------------------------------------------------
# Phase 39.1+ — Fidelity extras-CSV dialect sniffing + UTF-8 BOM strip.
#
# Background — the user's actual report. A Fidelity
# ``Portfolio_Positions_Jul-05-2026.csv`` exported via the broker's
# "Export to Excel" button is TAB-delimited even though the file has
# a ``.csv`` extension. The default comma-delimiter ``csv.DictReader``
# collapsed every row into a single field, ``reader.fieldnames`` was
# the literal header line treated as a single element, and the
# ``_detect_portfolio_csv`` exact-match against ``"Account Number"``
# failed on every row. A perfect file was rejected upstream with the
# misleading
#   "This doesn't look like a Fidelity Portfolio Positions CSV.
#    Expected columns: Account Number, Symbol, Current Value."
#
# Compounding trigger: Excel's "Save As CSV (UTF-8)" prepends a UTF-8
# BOM (``\\ufeff``) to the very first header cell, breaking the
# exact-match column-name check even on a comma-delimited file.
#
# Fix: strip the BOM once at the start, then sniff the dialect from
# the first non-empty line (whichever of ``\t`` vs ``,`` is more
# frequent wins). Default is ``,`` so the legacy comma path is
# unchanged for the canonical Fidelity download.
# ----------------------------------------------------------------------


def _strip_bom(text: str) -> str:
    """Strip a leading UTF-8 byte-order mark if present.

    Without this strip, ``reader.fieldnames[0]`` is
    ``"\\ufeffAccount Number"`` and the exact-match column check
    fails on a Fidelity extras CSV saved via Excel "Save As CSV
    UTF-8". Defensive: ``decode("utf-8", errors="ignore")`` is
    silent about the BOM (it produces the ``\\ufeff`` character
    rather than stripping it) so we own the strip here.
    """
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _sniff_csv_dialect(text: str) -> str:
    """Pick ``","`` vs ``"\\t"`` from the first non-empty line.

    Counts separator characters on the first line and picks whichever
    is more frequent; ``,`` wins on ties so the legacy comma path is
    unchanged. A blank file returns ``,`` so the route's empty-header
    short-circuit still triggers without surprise.
    """
    if not text:
        return ","
    first_line = text.split("\n", 1)[0].rstrip("\r")
    tab_count = first_line.count("\t")
    comma_count = first_line.count(",")
    if tab_count > comma_count:
        return "\t"
    return ","


# ---- Robinhood PDF patterns ----

# Lines that start the stocks table header row.
_ROBINHOOD_STOCK_HEADER_RE = re.compile(
    r"Symbol\s+Shares\s+Price\s+Average\s+cost\s+Total\s+return\s+Equity",
    re.IGNORECASE,
)

# Lines that start the crypto table header row.
_ROBINHOOD_CRYPTO_HEADER_RE = re.compile(
    r"Symbol\s+Quantity\s+Price\s+Average\s+cost\s+Total\s+return\s+Equity",
    re.IGNORECASE,
)

# A row containing 4+ dollar-amount tokens (e.g. $359.73) is a candidate
# holdings row. Excludes summary lines like "Total portfolio value".
_DOLLAR_TOKEN_RE = re.compile(r"^-?\$\d{1,3}(?:,\d{3})*(?:\.\d+)?$")

# Lines to skip (UI chrome, navigation, legal, etc).
_SKIP_LINE_RE = re.compile(
    r"^(Search|Rewards|Investing|Crypto|Agentic|Retirement|Notifications|"
    r"Account|Try Robinhood|Vijay|Crypto Transfers|Recurring|"
    r"Stock Lending|Reports|Tax center|History|Settings|Help|"
    r"Total portfolio|Individual cash|Margin|Dividend|"
    r"Stock Lending|Options|High-Yield|Futures|Event contracts|"
    r"Our powerful|enabled|disabled|Definitions|"
    r"Portfolio value|This account)",
    re.IGNORECASE,
)

# The summary lines like "99.90% $189,442.81" or "Stocks $189,442.81"
# have a percentage or the word "Stocks"/"Cryptocurrencies" followed by
# a dollar amount. These are section totals, not holdings rows.
_SECTION_TOTAL_RE = re.compile(
    r"^(?:[\d.]+%|Stocks|Cryptocurrencies)\s+\$?[\d,]+(?:\.\d+)?$",
    re.IGNORECASE,
)


def _detect_portfolio_csv(reader: csv.DictReader) -> dict[str, str] | None:
    """Return a column map {canonical: header_name} if this looks like a
    Fidelity portfolio-positions CSV. Returns None if not.

    Phase 39.1+ — matching is tolerant of leading/trailing whitespace
    AND case variations (``"Account Number"``, ``" account number "``,
    ``"ACCOUNT NUMBER"`` all map to the same canonical) so a Fidelity
    download emitted through a different encoding or an old xls->csv
    pipeline still validates. Required-column check uses the canonical
    KEY (NOT the original header value) so case-normalized files
    satisfy the check too.

    The diagnostic lives at the call site (the ``import_portfolio``
    route) — this helper stays a pure predicate that returns either
    a mapping or None.
    """
    if not reader.fieldnames:
        return None
    # Normalize field names once for case-insensitive matching.
    normalized_fields: dict[str, str] = {
        (f or "").strip().lower(): f
        for f in reader.fieldnames
        if f is not None
    }
    mapping: dict[str, str] = {}
    for canonical, header in _PORTFOLIO_COLUMNS.items():
        key = header.strip().lower()
        if key in normalized_fields:
            mapping[canonical] = normalized_fields[key]
    # Required canonicals — key set, not original-header value set,
    # so case-normalized files satisfy this check too.
    if {"account_number", "symbol", "current_value"} <= set(mapping.keys()):
        return mapping
    return None


def _parse_float(value: str | None) -> float | None:
    """Parse a dollar/percentage string to float, stripping $ and commas."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s == "-" or s == "--":
        return None
    s = s.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


# Fidelity's "Portfolio Positions" export labels every position in a cash
# account with the ACCOUNT type ("Cash", "Margin", "Short", "Long", or an
# option type like "Call"/"Put") in its "Type" column — NOT the asset
# class. Storing that value verbatim as ``holding.type`` makes every real
# stock/ETF/fund in a Fidelity cash account look like a cash position,
# which silently excludes the entire portfolio from analyst coverage and
# market briefing. We therefore normalize the column:
#
#   * values that are clearly Fidelity account/position types are dropped
#     (None) unless the row has no usable ticker (a genuine sweep/cash
#     position such as ``CORE**`` keeps the "Cash" label),
#   * a genuine asset-class value from another export shape is preserved,
#   * otherwise the asset class is inferred conservatively from the row
#     description (fund/ETF markers) so downstream "no consensus" labels
#     keep working for rows that were only mislabeled.

_FIDELITY_POSITION_TYPES = {
    "cash", "margin", "short", "long", "call", "put", "option",
}

# Mirrors the market-intelligence symbol contract: 1-10 uppercase letters,
# digits, ``.`` or ``-``. Sweep labels like ``CORE**`` / ``SPAXX**`` fail
# this and stay classified as cash.
_IMPORT_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _normalize_import_type(raw_type: str | None, symbol: str | None, description: str | None) -> str | None:
    """Map a Fidelity portfolio-export ``Type`` cell to a holding asset class.

    Fidelity's export puts the account type (``Cash``/``Margin``) in this
    column for every position, so persisting it verbatim misclassifies
    stocks as cash and hides the whole portfolio from coverage features.
    Rows with a real ticker get a conservatively inferred class (or None);
    rows without a usable ticker (genuine sweeps) keep the ``Cash`` label.
    """
    value = (raw_type or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered not in _FIDELITY_POSITION_TYPES:
        # A genuine asset-class value (e.g. an export that already says
        # "Stock", "ETF", "Mutual Fund", "Bond", "Crypto") — preserve it.
        return value
    if lowered != "cash":
        # Margin/short/long/option types never describe the asset class.
        return None
    sym = (symbol or "").strip().upper()
    if not sym or not _IMPORT_TICKER_RE.fullmatch(sym):
        # No usable ticker — this is a genuine sweep/cash position.
        return "Cash"
    # A real ticker labeled "Cash" is a mislabeled position. Infer a
    # conservative asset class from the description so downstream
    # "no consensus" labels keep working; unknown shapes stay None.
    # Word-boundary matching: a plain substring test would classify
    # NFLX ("netflix") as an ETF because "etf" appears inside the name.
    text = (description or "").lower()
    if re.search(r"\betf\b", text) or "exchange-traded" in text:
        return "ETF"
    if re.search(r"\bfund\b", text):
        return "Mutual Fund"
    return None


def _parse_robinhood_pdf(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Parse Robinhood holdings PDF text into stocks and crypto holdings.

    Returns (stocks_list, crypto_list, warnings).
    """
    stocks: list[dict[str, Any]] = []
    cryptos: list[dict[str, Any]] = []
    warnings: list[str] = []
    lines = text.splitlines()

    in_stocks = False
    in_crypto = False
    skipped = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect section headers
        if _ROBINHOOD_STOCK_HEADER_RE.search(line):
            in_stocks = True
            in_crypto = False
            continue
        if _ROBINHOOD_CRYPTO_HEADER_RE.search(line):
            in_crypto = True
            in_stocks = False
            continue

        # Skip UI chrome / navigation / legal lines
        if _SKIP_LINE_RE.match(line):
            # "Stocks" as a section label (not a header) is NOT a holdings row
            if line.strip().lower() == "stocks":
                continue
            if line.strip().lower() == "cryptocurrencies":
                continue
            skipped += 1
            continue

        # Skip section totals
        if _SECTION_TOTAL_RE.match(line):
            skipped += 1
            continue

        if not in_stocks and not in_crypto:
            continue

        # Try to parse as a holdings row
        row = _parse_robinhood_row(line)
        if row is None:
            skipped += 1
            continue

        if in_crypto:
            row["type"] = "Crypto"
            cryptos.append(row)
        else:
            row["type"] = "Stock"
            stocks.append(row)

    if skipped > 0:
        warnings.append(
            f"{skipped} line(s) skipped (UI chrome, section headers, or unparseable rows)."
        )

    return stocks, cryptos, warnings


def _parse_robinhood_row(line: str) -> dict[str, Any] | None:
    """Parse a single Robinhood holdings row like:
    'Alphabet Class A GOOGL 142.323 $359.73 $128.67 $32,884.84 $51,197.75'
    or 'NVDA 133.909 $195.31 $113.92 $10,898.98 $26,153.71'

    Returns None if the line cannot be parsed.
    """
    # Phase 39+ — Robinhood PDFs sometimes truncate long descriptions
    # with "…" and glue the symbol to the truncated text (e.g.
    # "Invesco Exchange-Traded Fun…QQQM"). Replace "…" with spaces
    # so the symbol splits into its own token.
    line = line.replace("\u2026", "  ").replace("...", "  ")

    tokens = line.split()
    if len(tokens) < 6:
        return None

    # Find indices of all dollar-amount tokens
    dollar_indices: list[int] = []
    for i, t in enumerate(tokens):
        if _DOLLAR_TOKEN_RE.match(t):
            dollar_indices.append(i)

    if len(dollar_indices) < 4:
        return None

    # Phase 39+ — when the last stock/crypto row on a page has the
    # page subtotal appended (e.g. "... $26,153.71 $189,442.81"),
    # there are 5+ dollar tokens. Use the 4 tokens BEFORE the last
    # one (which is the page subtotal).
    if len(dollar_indices) > 4:
        data_indices = dollar_indices[-5:-1]
        shares_idx = dollar_indices[-5] - 1
    else:
        data_indices = dollar_indices[-4:]
        shares_idx = dollar_indices[-4] - 1

    if shares_idx < 0:
        return None

    # Extract the 4 data fields from the last 4 (non-subtotal) dollar tokens
    equity = _parse_float(tokens[data_indices[-1]])
    total_return_val = _parse_float(tokens[data_indices[-2]])
    avg_cost = _parse_float(tokens[data_indices[-3]])
    price = _parse_float(tokens[data_indices[-4]])

    if equity is None or price is None:
        return None

    shares = _parse_float(tokens[shares_idx])
    if shares is None:
        return None

    # Symbol is the token before shares
    symbol_idx = shares_idx - 1
    if symbol_idx < 0:
        return None
    symbol = tokens[symbol_idx]

    # Validate symbol looks like a ticker (uppercase, 1-5 chars)
    if not re.match(r"^[A-Z0-9.]{1,5}$", symbol):
        return None

    # Description is everything before the symbol
    description = " ".join(tokens[:symbol_idx]) if symbol_idx > 0 else ""

    # Compute cost_basis_total from quantity × average_cost when possible
    cost_basis_total = None
    if avg_cost is not None and shares is not None and shares != 0:
        cost_basis_total = avg_cost * shares

    return {
        "symbol": symbol,
        "description": description or None,
        "quantity": shares,
        "last_price": price,
        "current_value": equity,
        "cost_basis_total": cost_basis_total,
    }


def _detect_robinhood_pdf(text: str) -> bool:
    """Return True if this text looks like a Robinhood holdings PDF."""
    has_total = "Total portfolio value" in text
    has_stock_header = _ROBINHOOD_STOCK_HEADER_RE.search(text) is not None
    has_crypto_header = _ROBINHOOD_CRYPTO_HEADER_RE.search(text) is not None
    return has_total and (has_stock_header or has_crypto_header)


def _build_account_holdings_map(
    stocks: list[dict[str, Any]],
    cryptos: list[dict[str, Any]],
) -> dict[str, tuple[str, str, list[dict[str, Any]]]]:
    """Build a map of {account_key: (account_name, account_type, holdings)}.

    Returns a dict keyed by a synthetic account key used for matching on
    re-import.
    """
    result: dict[str, tuple[str, str, list[dict[str, Any]]]] = {}
    if stocks:
        result["robinhood-stocks"] = ("Robinhood Stocks", "investment", stocks)
    if cryptos:
        result["robinhood-crypto"] = ("Robinhood Crypto", "crypto", cryptos)
    return result


@router.post("/import", response_model=PortfolioImportResponse)
async def import_portfolio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Import a Fidelity Portfolio Positions CSV or Robinhood holdings PDF.

    For each unique account, auto-creates (or matches on synthetic key)
    an Account row and upserts holdings. Existing holdings for the
    same account are replaced.
    """
    local_user = get_or_create_local_user(db, _current_user)
    filename = (file.filename or "").lower()

    # ---- PDF path (Robinhood) ----
    if filename.endswith(".pdf"):
        try:
            file.file.seek(0)
            with pdfplumber.open(file.file) as pdf:
                text_lines: list[str] = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_lines.append(page_text)
                text = "\n".join(text_lines)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not parse PDF file: {exc}",
            )

        if not _detect_robinhood_pdf(text):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This doesn't look like a Robinhood holdings PDF. "
                    "Expected a Robinhood account statement with holdings table."
                ),
            )

        stocks, cryptos, warnings = _parse_robinhood_pdf(text)
        account_map = _build_account_holdings_map(stocks, cryptos)

        if not account_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid holdings found in the PDF.",
            )

    # ---- CSV path (Fidelity) ----
    elif filename.endswith(".csv"):
        text_bytes = await file.read()
        text = text_bytes.decode("utf-8", errors="ignore")
        # Phase 39.1+ — strip a UTF-8 BOM (Excel "Save As CSV UTF-8"
        # quirk) and sniff the dialect. Fidelity's "Export to Excel"
        # produces a tab-delimited file even with a .csv extension;
        # the default comma-delimiter DictReader collapses every
        # row into one field and the parser rejected a perfect
        # file with the misleading "Expected columns..." error.
        text = _strip_bom(text)
        delimiter = _sniff_csv_dialect(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV has no header row.",
            )

        column_map = _detect_portfolio_csv(reader)
        if not column_map:
            # Phase 39.1+ — surface what we actually saw so the user
            # can diagnose a column-rename themselves. Bracket-wrapped
            # list keeps truncation predictable when the file has 20+
            # extra columns. The detected-dialect string keeps tabs
            # vs comma disambiguated for human readers.
            seen = ", ".join(
                repr((h or "").strip()) for h in reader.fieldnames
            )
            fmt = "tab-separated" if delimiter == "\t" else "comma-separated"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"This doesn't look like a Fidelity Portfolio Positions CSV. "
                    f"Expected columns: Account Number, Symbol, Current Value. "
                    f"Detected a {fmt} file; saw columns: [{seen}]."
                ),
            )

        # Parse rows into account groups
        raw_account_holdings: dict[str, list[dict[str, Any]]] = {}
        account_names: dict[str, str] = {}
        warnings = []
        skipped = 0

        for row in reader:
            acct_num = (row.get(column_map.get("account_number", "")) or "").strip()
            acct_name = (row.get(column_map.get("account_name", "")) or "").strip()
            symbol = (row.get(column_map.get("symbol", "")) or "").strip()
            description = (row.get(column_map.get("description", "")) or "").strip()
            cur_val = (row.get(column_map.get("current_value", "")) or "").strip()
            qty = (row.get(column_map.get("quantity", "")) or "").strip()
            price = (row.get(column_map.get("last_price", "")) or "").strip()
            cost = (row.get(column_map.get("cost_basis_total", "")) or "").strip()
            htype = (row.get(column_map.get("type", "")) or "").strip()

            if not acct_num and not symbol and not cur_val:
                continue
            if not symbol and not description and not htype:
                skipped += 1
                continue

            value = _parse_float(cur_val)
            if value is None:
                skipped += 1
                continue

            if acct_num not in raw_account_holdings:
                raw_account_holdings[acct_num] = []
            if acct_num not in account_names and acct_name:
                account_names[acct_num] = acct_name

            raw_account_holdings[acct_num].append({
                "symbol": symbol or None,
                "description": description or None,
                "quantity": _parse_float(qty),
                "last_price": _parse_float(price),
                "current_value": value,
                "cost_basis_total": _parse_float(cost),
                # Fidelity's "Type" column is the ACCOUNT type (Cash/Margin),
                # not the asset class; normalize so real stocks are not stored
                # as "Cash" and silently excluded from coverage features.
                "type": _normalize_import_type(htype, symbol, description),
            })

        if not raw_account_holdings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid positions found in the CSV.",
            )

        # Convert to account_map format: {key: (name, type, holdings)}
        account_map = {}
        for acct_num, holdings_list in raw_account_holdings.items():
            name = account_names.get(acct_num, f"Fidelity {acct_num}")
            types_in = {h.get("type", "") for h in holdings_list if h.get("type")}
            acct_type = "investment"
            if "Cash" in types_in and len(types_in) == 1:
                acct_type = "checking"
            elif any(t in types_in for t in ("Mutual Fund", "Stock", "ETF")):
                acct_type = "investment"
            account_map[acct_num] = (name, acct_type, holdings_list)

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Please upload a CSV or PDF file.",
        )

    # ---- Persist accounts and holdings (shared path) ----
    accounts_created = 0
    accounts_updated = 0
    total_value = 0.0
    account_ids: list[int] = []
    skipped_csv = 0

    for key, (account_name, account_type, holdings_list) in account_map.items():
        # Determine institution
        if account_type == "crypto":
            inst_name = "Robinhood"
        elif "robinhood" in key:
            inst_name = "Robinhood"
        else:
            inst_name = "Fidelity Investments"

        institution = get_or_create_institution(db, inst_name)
        self_row = get_or_create_family_member_self(db, local_user)

        # Find or create account (match on account_number for Fidelity CSV,
        # or account_name for Robinhood)
        acct = (
            db.query(Account)
            .filter(
                Account.account_name == account_name,
                Account.user_id == local_user.id,
            )
            .first()
        )

        if not acct:
            acct = Account(
                user_id=local_user.id,
                institution_id=institution.id,
                account_name=account_name,
                account_type=account_type,
                current_balance=0.0,
                is_active=True,
                family_member_id=self_row.id,
                # Phase 40 — Portfolio import (matches both Fidelity
                # CSV + Robinhood PDF — the filename-derived
                # institution differentiates them in the import log).
                # ``holdings_list`` is the per-account bucket
                # already extracted from the multi-account parser.
                source="imported",
                description=(
                    f"Portfolio import from "
                    f"{file.filename or 'CSV'} "
                    f"({len(holdings_list)} holdings)"
                ),
            )
            db.add(acct)
            db.flush()
            accounts_created += 1
            _logger.info("Portfolio import: created Account #%d (%r)", acct.id, account_name)
        elif not acct.is_active:
            acct.is_active = True
            accounts_updated += 1
        account_ids.append(acct.id)

        # Compute account total
        acct_total = sum(h["current_value"] for h in holdings_list)
        total_value += acct_total

        # Replace existing holdings for this account
        db.query(Holding).filter(Holding.account_id == acct.id).delete()
        for h in holdings_list:
            holding = Holding(
                account_id=acct.id,
                symbol=h["symbol"],
                description=h["description"],
                quantity=h["quantity"],
                last_price=h["last_price"],
                current_value=h["current_value"],
                cost_basis_total=h["cost_basis_total"],
                type=h.get("type"),
            )
            db.add(holding)

        # Set account balance from holdings sum
        acct.current_balance = acct_total
        db.add(acct)

    if skipped_csv > 0:
        warnings.append(
            f"{skipped_csv} row(s) skipped (pending activity, footers, "
            f"or unparseable values)."
        )

    total_holdings = sum(len(v[2]) for v in account_map.values())
    _logger.info(
        "Portfolio import: %d holdings across %d accounts, total=$%.2f",
        total_holdings, len(account_map), total_value,
    )

    db.commit()

    return PortfolioImportResponse(
        holdings_count=total_holdings,
        accounts_created=accounts_created,
        accounts_updated=accounts_updated,
        total_value=total_value,
        warnings=warnings,
        account_ids=account_ids,
    )


@router.get("/", response_model=list[HoldingResponse])
async def list_holdings(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """List every holding for the current user, joined with account name."""
    local_user = get_or_create_local_user(db, _current_user)

    account_ids = [
        r[0] for r in db.query(Account.id)
        .filter(Account.user_id == local_user.id, Account.is_active.is_(True))
        .all()
    ]

    if not account_ids:
        return []

    holdings = (
        db.query(Holding)
        .filter(Holding.account_id.in_(account_ids))
        .order_by(Holding.account_id, Holding.current_value.desc())
        .all()
    )

    acct_names: dict[int, str] = {}
    for acct in db.query(Account).filter(Account.id.in_(account_ids)).all():
        acct_names[acct.id] = acct.account_name

    result: list[HoldingResponse] = []
    for h in holdings:
        result.append(HoldingResponse(
            id=h.id,
            account_id=h.account_id,
            account_name=acct_names.get(h.account_id),
            symbol=h.symbol,
            description=h.description,
            quantity=h.quantity,
            last_price=h.last_price,
            current_value=h.current_value,
            cost_basis_total=h.cost_basis_total,
            type=h.type,
        ))
    return result


@router.get("/summary", response_model=PortfolioValuationSummary)
async def portfolio_valuation_summary(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Server-owned portfolio valuation projection (GAP-12 closure).

    Computes grand total, per-account totals/allocation, per-holding
    value/allocation/gain, and asset-type rollups from the same rows
    served by ``GET /api/holdings/`` (``current_value`` — the stored,
    deterministic value; live quotes are ephemeral refresh responses
    and are never persisted). The browser consumes this projection and
    performs no portfolio arithmetic; percentages are ``null`` (never
    invented zeros) when a denominator or cost basis is absent.
    """
    local_user = get_or_create_local_user(db, _current_user)

    account_ids = [
        r[0]
        for r in db.query(Account.id)
        .filter(Account.user_id == local_user.id, Account.is_active.is_(True))
        .all()
    ]

    now = datetime.utcnow()
    if not account_ids:
        return PortfolioValuationSummary(
            grand_total=0.0,
            accounts=[],
            holdings=[],
            types=[],
            computed_at=now,
        )

    holdings = (
        db.query(Holding)
        .filter(Holding.account_id.in_(account_ids))
        .order_by(Holding.account_id, Holding.current_value.desc())
        .all()
    )

    acct_names: dict[int, tuple[Optional[str], Optional[str]]] = {}
    for acct in db.query(Account).filter(Account.id.in_(account_ids)).all():
        acct_names[acct.id] = (acct.account_name, acct.account_type)

    def _value(h: Holding) -> float:
        return float(h.current_value)

    holding_rows: list[PortfolioHoldingValuation] = []
    account_totals: dict[int, float] = {aid: 0.0 for aid in account_ids}
    type_totals: dict[str, float] = {}

    for h in holdings:
        value = _value(h)
        holding_rows.append(PortfolioHoldingValuation(
            holding_id=h.id,
            symbol=h.symbol,
            description=h.description,
            value=value,
            allocation_pct=None,  # filled after grand total is known
            gain_pct=(
                ((value - float(h.cost_basis_total)) / abs(float(h.cost_basis_total))) * 100.0
                if h.cost_basis_total is not None and h.cost_basis_total != 0
                else None
            ),
        ))
        account_totals[h.account_id] = account_totals.get(h.account_id, 0.0) + value
        t = h.type or "Other"
        type_totals[t] = type_totals.get(t, 0.0) + value

    grand_total = sum(account_totals.values())

    for row in holding_rows:
        if grand_total > 0:
            row.allocation_pct = (row.value / grand_total) * 100.0

    account_rows: list[PortfolioAccountValuation] = []
    for aid in account_ids:
        total = account_totals.get(aid, 0.0)
        name, atype = acct_names.get(aid, (None, None))
        account_rows.append(PortfolioAccountValuation(
            account_id=aid,
            account_name=name,
            account_type=atype,
            total=total,
            positions_count=sum(1 for h in holdings if h.account_id == aid),
            allocation_pct=((total / grand_total) * 100.0) if grand_total > 0 else None,
        ))
    account_rows.sort(key=lambda r: r.account_id)

    type_rows: list[PortfolioTypeValuation] = []
    for t, total in sorted(type_totals.items(), key=lambda kv: kv[1], reverse=True):
        type_rows.append(PortfolioTypeValuation(
            type=t,
            total=total,
            allocation_pct=((total / grand_total) * 100.0) if grand_total > 0 else None,
        ))

    return PortfolioValuationSummary(
        grand_total=grand_total,
        accounts=account_rows,
        holdings=holding_rows,
        types=type_rows,
        computed_at=now,
    )


@router.post("/refresh-prices")
async def refresh_prices(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Fetch live prices from Finnhub for unique symbols in the user's
    holdings. Returns the updated holdings list."""
    local_user = get_or_create_local_user(db, _current_user)
    account_ids = [
        r[0] for r in db.query(Account.id)
        .filter(Account.user_id == local_user.id, Account.is_active.is_(True))
        .all()
    ]
    if not account_ids:
        return {"holdings": [], "warning": "No active accounts"}

    holdings = (
        db.query(Holding)
        .filter(Holding.account_id.in_(account_ids))
        .all()
    )

    symbols: set[str] = set()
    for h in holdings:
        s = (h.symbol or "").strip().upper()
        if s and not s.endswith("**") and s not in ("CORE", "NON40", "PENDING"):
            symbols.add(s)

    prices: dict[str, dict[str, float]] = {}
    # Phase 39.2 — read from BOTH ``os.environ`` AND ``Settings`` so
    # a developer who pastes ``FINNHUB_API_KEY`` into
    # ``services/rules-service/.env`` (without ``export``-ing it in
    # the launching shell) gets a working ``refresh-prices`` call.
    # Mirrors the same fallback chain in ``app/routes/analyst_ratings.py``;
    # os.environ-first preserves the existing test pattern.
    api_key = (
        os.environ.get("FINNHUB_API_KEY") or settings.finnhub_api_key or ""
    ).strip()
    warning = None

    if not api_key:
        warning = "Finnhub API key not configured. Set FINNHUB_API_KEY in .env for live prices."
    else:
        import asyncio
        import httpx

        async def _fetch_one(symbol: str, client: httpx.AsyncClient) -> tuple[str, dict[str, float] | None]:
            try:
                resp = await client.get(
                    "https://finnhub.io/api/v1/quote",
                    params={"symbol": symbol, "token": api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return symbol, {
                        "current": float(data.get("c", 0)),
                        "previous_close": float(data.get("pc", 0)),
                    }
                _logger.warning("Finnhub quote for %s: HTTP %d", symbol, resp.status_code)
            except Exception as exc:
                _logger.warning("Finnhub quote failed for %s: %s", symbol, exc)
            return symbol, None

        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = [_fetch_one(s, client) for s in sorted(symbols)]
            results = await asyncio.gather(*tasks)
            for symbol, quote in results:
                if quote:
                    prices[symbol] = quote

    acct_names: dict[int, str] = {}
    for acct in db.query(Account).filter(Account.id.in_(account_ids)).all():
        acct_names[acct.id] = acct.account_name

    result: list[HoldingResponse] = []
    for h in holdings:
        sym = (h.symbol or "").strip().upper()
        quote = prices.get(sym)
        live_price = quote["current"] if quote else None
        live_value = (live_price * h.quantity) if (live_price and h.quantity) else None
        day_change = None
        if quote and quote.get("previous_close") and quote["previous_close"] != 0:
            day_change = ((quote["current"] - quote["previous_close"]) / quote["previous_close"]) * 100

        result.append(HoldingResponse(
            id=h.id,
            account_id=h.account_id,
            account_name=acct_names.get(h.account_id),
            symbol=h.symbol,
            description=h.description,
            quantity=h.quantity,
            last_price=h.last_price,
            current_value=h.current_value,
            cost_basis_total=h.cost_basis_total,
            type=h.type,
            live_price=live_price,
            live_value=live_value,
            day_change_pct=day_change,
        ))

    return {"holdings": result, "warning": warning, "prices_updated": len(prices)}



@router.post("/", response_model=HoldingResponse, status_code=status.HTTP_201_CREATED)
async def create_holding(
    payload: HoldingManualCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 41 -- manual single holding entry.

    Accepts EITHER ``account_id`` (existing account, must belong to
    the user + be active) OR ``account_name`` (auto-creates a new
    Account under a generic 'Portfolio' institution with
    ``source='manual'``).

    Either input must be non-null/blank -- the route 400s with a
    clear 'provide either ...' message otherwise so the FE surfaces
    a clean validation error rather than a silent 500.

    After insert, recomputes the target account's
    ``current_balance`` as the sum of ``holding.current_value``
    across ALL its holdings (including the just-added row). This
    matches the import path which also writes
    ``acct.current_balance = acct_total`` after a multi-account import.
    """
    has_id = payload.account_id is not None
    has_name = bool((payload.account_name or "").strip())
    if not has_id and not has_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Provide either account_id (existing account) or "
                "account_name (creates a new portfolio account)."
            ),
        )

    if payload.quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity must be > 0.",
        )
    if payload.current_value is None and payload.last_price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Provide either last_price (auto-computes current_value) "
                "OR current_value directly."
            ),
        )

    local_user = get_or_create_local_user(db, _current_user)
    self_row = get_or_create_family_member_self(db, local_user)

    if payload.account_id is not None:
        acct = (
            db.query(Account)
            .filter(
                Account.id == payload.account_id,
                Account.user_id == local_user.id,
                Account.is_active.is_(True),
            )
            .first()
        )
        if acct is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Account {payload.account_id} not found, does not "
                    f"belong to you, or is inactive."
                ),
            )
    else:
        new_name = (payload.account_name or "").strip()
        institution = get_or_create_institution(db, "Portfolio")
        acct = (
            db.query(Account)
            .filter(
                Account.account_name == new_name,
                Account.user_id == local_user.id,
            )
            .first()
        )
        if acct is None:
            acct = Account(
                user_id=local_user.id,
                institution_id=institution.id,
                account_name=new_name,
                account_type="investment",
                current_balance=0.0,
                is_active=True,
                family_member_id=self_row.id,
                # Phase 40/41 -- manual-add path stamps
                # ``source='manual'`` so the Accounts-page chip
                # shows Manual (vs Imported / Plaid) without a
                # follow-up PUT.
                source="manual",
                description=f"Manually-created portfolio ({new_name})",
            )
            db.add(acct)
            db.flush()
        elif acct.is_active is False:
            acct.is_active = True

    if payload.current_value is None and payload.last_price is not None:
        current_value = payload.last_price * payload.quantity
    else:
        current_value = payload.current_value if payload.current_value is not None else 0.0

    cost_basis = (
        payload.cost_basis_total
        if payload.cost_basis_total is not None
        else current_value
    )

    holding = Holding(
        account_id=acct.id,
        symbol=(payload.symbol or "").strip().upper() or None,
        description=(payload.description or "").strip() or None,
        quantity=payload.quantity,
        last_price=payload.last_price,
        current_value=current_value,
        cost_basis_total=cost_basis,
        type=(payload.type or "").strip() or None,
    )
    db.add(holding)
    db.flush()

    new_total = sum(
        (h.current_value or 0.0)
        for h in db.query(Holding).filter(Holding.account_id == acct.id).all()
    )
    acct.current_balance = new_total
    # Phase 41 -- dynamically refresh the lazily-created 'manual'
    # account's description so the Accounts-page chip keeps an
    # accurate position count instead of the static 'Manually-
    # created portfolio (X)' placeholder. The substring check
    # scopes the refresh to accounts WE created via the manual
    # path -- an import-time description on a Fidelity/Robinhood
    # account is NEVER touched.
    if acct.id is not None and 'Manually-created' in (acct.description or ''):
        n_holdings = (
            db.query(Holding).filter(Holding.account_id == acct.id).count()
        )
        plural = 's' if n_holdings != 1 else ''
        acct.description = (
            f'Manually-created portfolio ({acct.account_name}) '
            f'\u2013 {n_holdings} position{plural}'
        )
    db.add(acct)
    db.commit()
    db.refresh(holding)

    _logger.info(
        "Phase 41 manual add: account=#%d (%r) holding=%r qty=%.4f value=$%.2f",
        acct.id, acct.account_name, holding.symbol, holding.quantity or 0.0,
        float(current_value),
    )

    return HoldingResponse(
        id=holding.id,
        account_id=holding.account_id,
        account_name=acct.account_name,
        symbol=holding.symbol,
        description=holding.description,
        quantity=holding.quantity,
        last_price=holding.last_price,
        current_value=holding.current_value,
        cost_basis_total=holding.cost_basis_total,
        type=holding.type,
    )


# ----------------------------------------------------------------------
# Phase 47 -- Edit + Delete holdings (`PUT` + `DELETE` on `/api/holdings/{id}`)
# ----------------------------------------------------------------------
#
# The user reported that editing a position after import (especially
# the share count when buying more / selling some / correcting a
# parser-led typo) had no UI affordance. The only workaround was a
# full re-import which DELETEs every other position on the same
# account -- destructive and noisy. Phase 47 adds ``PUT`` and
# ``DELETE`` routes so /portfolio can mutate / remove a single row
# without touching its siblings.
#
# Design (locked by Phase 47 think-through):
#   - PUT is a PATCH-shaped partial update: every field on
#     ``HoldingUpdate`` is optional, the route treats omitted keys
#     as "leave row alone" via ``model_dump(exclude_unset=True)``.
#   - account_id is intentionally NOT in the whitelist so a FE
#     bug can't desync two account balances via a transfer that
#     wasn't atomic. A future "Transfer" affordance will own that
#     contract separately.
#   - After every successful PUT or DELETE, the parent
#     ``Account.current_balance`` is recomputed (see
#     ``_recompute_account_balance``). Skipping this silently
#     desyncs the /portfolio aggregate from the row state.
#   - DELETE is HARD (no is_archived). ``Holding`` has no FK
#     dependents (per ``models/holding.py`` docstring) and the
#     existing CSV re-import already ``.delete()``s every prior
#     row -- destructive semantics already match user
#     expectations.
#   - Cross-user isolation: every handler resolves the holding's
#     owning Account and checks ``user_id == local_user.id`` before
#     any mutation. Failures fall through to a generic 404 with
#     ``"not found"`` -- deliberately NOT distinguishing "not
#     found" from "belongs to another user" so a probing client
#     gets no signal about other users' holdings existing.
# ----------------------------------------------------------------------


def _recompute_account_balance(db: Session, account_id: int) -> None:
    """Phase 47 -- recompute ``Account.current_balance`` as the sum
    of every holding's ``current_value`` for this account.

    Mirrors the same formula the POST /api/holdings/ + import
    paths use, so the read-side aggregate stays ground-truth to the
    underlying rows regardless of which write path mutated the
    holdings table.

    A separate update path keeps the Account row's
    ``updated_at`` ``onupdate=func.now()`` firing on every
    mutation, which the FE's "last_sync" affordance surfaces.
    """
    holdings = (
        db.query(Holding)
        .filter(Holding.account_id == account_id)
        .all()
    )
    total = sum((h.current_value or 0.0) for h in holdings)
    acct = db.query(Account).filter(Account.id == account_id).first()
    if acct is not None:
        acct.current_balance = total
        db.add(acct)


def _resolve_holding_for_local_user(
    db: Session, holding_id: int, local_user_id: int,
) -> tuple[Holding, Account]:
    """Phase 47 -- single-source for the cross-user isolation
    check on every holding-scoped route.

    Returns ``(holding, account)`` when the holding exists AND its
    owning account belongs to ``local_user``. Raises 404 otherwise
    with a uniform "not found" message so a probing client cannot
    distinguish "exists but forbidden" from "doesn't exist".
    """
    holding = db.query(Holding).filter(Holding.id == holding_id).first()
    if holding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding {holding_id} not found.",
        )
    acct = (
        db.query(Account)
        .filter(
            Account.id == holding.account_id,
            Account.user_id == local_user_id,
        )
        .first()
    )
    if acct is None:
        # Deliberately indistinguishable from "doesn't exist" so
        # cross-user probing returns no signal.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding {holding_id} not found.",
        )
    return holding, acct


@router.put("/{holding_id}", response_model=HoldingResponse)
async def update_holding(
    holding_id: int,
    payload: HoldingUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 47 -- partial-update one position.

    Mirrors the create-flow's ``current_value = last_price *
    quantity`` auto-derive: if the patch updates ``quantity`` AND
    ``last_price`` (and the resulting current_value differs from
    the row's prior value), the route overwrites ``current_value``
    to ``last_price * quantity``. This keeps the edit form
    arithmetic-light for the user ("just type the new share count
    and let the wall-clock price do the rest").

    If ``quantity`` is sent with a value ``<= 0`` (Pydantic accepts
    ``ge=0`` but the create route's defence-in-depth rejects the
    boundary case), the route 400s so a fat-fingered ``0`` doesn't
    silently delete the row's value tree downstream.
    """
    local_user = get_or_create_local_user(db, _current_user)
    holding, acct = _resolve_holding_for_local_user(
        db, holding_id, local_user.id,
    )

    data = payload.model_dump(exclude_unset=True)

    # Defence in depth -- Pydantic accepts ge=0 so a literal ``0``
    # makes it past the schema layer. Mirror the create-route's
    # ``<= 0`` 400 so the edit path also rejects the boundary.
    if "quantity" in data and data["quantity"] is not None and data["quantity"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity must be > 0.",
        )

    # Apply the patch with explicit normalisation on string fields.
    for field, raw in data.items():
        if field == "symbol" and raw is not None:
            # Mirror create_holding: uppercase + strip + None for empty.
            setattr(holding, "symbol", (str(raw) or "").strip().upper() or None)
        elif field == "description" and raw is not None:
            setattr(holding, "description", (str(raw) or "").strip() or None)
        elif field == "type" and raw is not None:
            setattr(holding, "type", (str(raw) or "").strip() or None)
        else:
            setattr(holding, field, raw)

    # Auto-derive current_value ONLY when the patch INCLUDES
    # ``quantity`` (the user's stated priority share-count field).
    # A single-field ``{last_price: X}`` edit (e.g. an analyst
    # re-quoting the price) must leave current_value UNCHANGED,
    # otherwise a 10-share @ $200 = $2000 row silently drops to
    # 10 * 0.001 = $0.01 — see Phase 47 reviewer Q5. Bug-fix
    # contract: "you said quantity changed, so I recomputed the
    # value"; no quantity-in-patch = no value recomputation.
    if (
        "quantity" in data
        and holding.last_price is not None
        and holding.quantity is not None
    ):
        holding.current_value = float(holding.last_price) * float(holding.quantity)

    db.add(holding)
    db.flush()

    _recompute_account_balance(db, acct.id)

    db.commit()
    db.refresh(holding)

    _logger.info(
        "Phase 47 update holding: id=%d account=#%d quantity=%s value=$%.2f",
        holding.id, acct.id, holding.quantity or 0.0,
        float(holding.current_value or 0.0),
    )

    return HoldingResponse(
        id=holding.id,
        account_id=holding.account_id,
        account_name=acct.account_name,
        symbol=holding.symbol,
        description=holding.description,
        quantity=holding.quantity,
        last_price=holding.last_price,
        current_value=holding.current_value,
        cost_basis_total=holding.cost_basis_total,
        type=holding.type,
    )


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holding(
    holding_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 47 -- hard-delete one position.

    Returns 204 No Content (consistent with ``DELETE /api/goals/{id}``
    and ``DELETE /api/accounts/{id}`` so the FE's 401-refresh
    interceptor + ``await api.delete(...)`` pattern Just Works).
    Recomputes the parent account's balance post-mutation so an
    account whose last position was deleted lands with a clean
    ``current_balance == 0.0``.
    """
    local_user = get_or_create_local_user(db, _current_user)
    holding, _acct = _resolve_holding_for_local_user(
        db, holding_id, local_user.id,
    )

    account_id = holding.account_id
    symbol = holding.symbol

    db.delete(holding)
    db.flush()

    _recompute_account_balance(db, account_id)

    db.commit()

    _logger.info(
        "Phase 47 delete holding: id=%d account=#%d symbol=%r",
        holding_id, account_id, symbol,
    )

    # FastAPI serialises ``None`` + ``status_code=204`` as an empty
    # body per the HTTP spec (RFC 9110 §15.3.5: 204 MUST NOT include
    # a body). The FE's ``await api.delete(...)`` happily resolves
    # an empty payload.
    return None
