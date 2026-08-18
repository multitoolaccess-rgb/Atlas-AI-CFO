"""Phase 30g — transfer detection and classification.

An internal transfer is a PAIR of rows: an outflow on account A and an
inflow on account B (same amount, near date). Atlas treats the pair as
ONE neutral movement:

- both halves get ``transfer_pair_id`` pointing at each other, and
- both halves are categorised ``Transfer`` (the dashboard's
  ``classify_cashflow`` already excludes transfer effects from P&L;
  this module makes the CATEGORY assignment agree with that math).

Transfers that CANNOT be paired (money moving to/from accounts outside
Atlas — Zelle/Venmo, wires, ATM, external-account transfers) are
classified by DIRECTION:

- ``Transfer In``  — external money arriving (deposits, peer-to-peer
  received, wires in, transfers from external accounts).
- ``Transfer Out`` — money leaving to an external destination
  (withdrawals, peer-to-peer sent, wires out, transfers to external
  accounts).

Deliberate guards (financial-correctness boundary — these are the
stronger boundary tests the repo requires for money movement):

- Only rows that are UNCATEGORISED or already carry the auto-assigned
  ``Transfer`` category are touched. A manual or Debt category
  (Groceries, Credit Card Payments, Mortgage, ...) is NEVER
  overwritten.
- Pairs must be on DIFFERENT accounts. Same-account opposite-sign
  rows are refunds/reversals, not transfers.
- Amounts must match within a cent (``_PAIR_AMOUNT_EPSILON``) and
  dates within ±3 days (ACH float).
- Loan / credit-card payments keep their Debt category: pairing only
  LINKS them (adds ``transfer_pair_id``), it never re-categorises
  them to ``Transfer``.
- Pairing is one-to-one and greedy on nearest date: an inflow can
  pair with only one outflow.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction

LOG = logging.getLogger(__name__)

# Amounts must match within a cent for a pair to be credible.
_PAIR_AMOUNT_EPSILON = 0.01
# ACH float: the two halves of an internal transfer can post 1-3 days
# apart depending on the banks involved.
_PAIR_DATE_WINDOW = timedelta(days=3)

# Direction keyword groups — word-bounded, case-insensitive, matched
# against the concatenated ``merchant_name + " " + description`` text.
# "From/In/Received" ⇒ money ARRIVING (Transfer In); "To/Out/Sent" ⇒
# money LEAVING (Transfer Out). These mirror the merchant-rule
# keywords that currently dump rows into the generic ``Transfer``
# bucket (ZELLE, VENMO, CASHAPP, WIRE, ACH, ATM, ...).
_TRANSFER_IN_PATTERNS: tuple[str, ...] = (
    "transfer from",
    "transfer in",
    "zelle from",
    "zelle received",
    "venmo from",
    "cash app from",
    "cashapp from",
    "wire in",
    "wire received",
    "deposit",
    "external deposit",
    "ach credit",
    "ach in",
    "eft funds received",
    "moneyline",
    "incoming transfer",
)

_TRANSFER_OUT_PATTERNS: tuple[str, ...] = (
    "transfer to",
    "transfer out",
    "zelle to",
    "zelle out",
    "venmo to",
    "cash app to",
    "cashapp to",
    "wire out",
    "wire sent",
    "withdrawal",
    "atm ",
    "ach debit",
    "ach out",
    "eft funds sent",
    "outgoing transfer",
)


def _match_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Word-bounded substring match (space-padded, like
    ``account_types._match_any`` so ``" payment "`` does not match
    ``" repayment "``)."""
    d = f" {text.lower()} "
    return any(f" {p} " in d for p in patterns)


def _transfer_categories(
    db: Session,
) -> tuple[Optional[Category], Optional[Category], Optional[Category]]:
    """Resolve (Transfer, Transfer In, Transfer Out) category rows."""
    rows = {
        c.name: c
        for c in db.query(Category).filter(
            Category.name.in_(["Transfer", "Transfer In", "Transfer Out"])
        ).all()
    }
    return (
        rows.get("Transfer"),
        rows.get("Transfer In"),
        rows.get("Transfer Out"),
    )


def _user_rows(db: Session, user_id: int) -> list[Transaction]:
    """Every transaction the user owns (ownership flows through
    Account.user_id — there is no direct Transaction.user_id column)."""
    return (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(Account.user_id == user_id)
        .all()
    )


def pair_internal_transfers(db: Session, user_id: int) -> int:
    """Pair internal transfer rows and tag both halves ``Transfer``.

    Returns the number of PAIRS formed. Pairing rule: an outflow
    (``amount < 0``) on account A pairs with the inflow (``amount > 0``)
    on account B (``A != B``) whose amount is within a cent and whose
    date is nearest within ±3 days. Both rows get ``transfer_pair_id``
    set to the other's id. Category is set to ``Transfer`` only when
    the row is uncategorised or already ``Transfer`` — manual and
    Debt categories are left untouched (loan/credit-card payments keep
    ``Credit Card Payments`` etc. and are merely LINKED).
    """
    transfer_cat, _in_cat, _out_cat = _transfer_categories(db)
    rows = _user_rows(db, user_id)
    outflows = [
        t for t in rows
        if t.amount is not None and t.amount < 0
        and t.transfer_pair_id is None
    ]
    if not outflows:
        return 0

    # Bucket inflows by AMOUNT rounded to cents (the counterpart lives
    # on a DIFFERENT account, so account_id can't be part of the key —
    # the different-account check happens in the scan below). Each
    # bucket is date-sorted so matching is a small nearest-date scan
    # instead of an O(N^2) full scan.
    inflows: dict[int, list[Transaction]] = {}
    for t in rows:
        if (
            t.amount is None or t.amount <= 0
            or t.transfer_pair_id is not None
        ):
            continue
        key = round(t.amount, 2)
        inflows.setdefault(key, []).append(t)
    for bucket in inflows.values():
        bucket.sort(key=lambda t: (t.transaction_date, t.id))

    pairs = 0
    for out in outflows:
        bucket = inflows.get(round(-out.amount, 2))
        if not bucket:
            continue
        # Nearest-date candidate on a DIFFERENT account, within window.
        best: Optional[Transaction] = None
        best_delta = _PAIR_DATE_WINDOW + timedelta(seconds=1)
        for cand in bucket:
            if cand.account_id == out.account_id:
                continue
            delta = abs(cand.transaction_date - out.transaction_date)
            if delta <= _PAIR_DATE_WINDOW and delta < best_delta:
                best = cand
                best_delta = delta
        if best is None:
            continue
        # One-to-one: remove the matched inflow from its bucket.
        bucket.remove(best)
        out.transfer_pair_id = best.id
        best.transfer_pair_id = out.id
        # Category: only when uncategorised or already the neutral
        # Transfer bucket (manual / Debt categories are preserved).
        if transfer_cat is not None:
            for t in (out, best):
                if t.category_id is None or t.category_id == transfer_cat.id:
                    t.category_id = transfer_cat.id
        pairs += 1

    if pairs:
        LOG.info("Transfer pairing: user=%s formed %d pair(s)", user_id, pairs)
    return pairs


def classify_external_transfers(db: Session, user_id: int) -> int:
    """Classify unpaired transfer rows into ``Transfer In`` / ``Transfer Out``.

    Candidates are rows that are UNCATEGORISED or carry the generic
    auto-assigned ``Transfer`` category (merchant-rule hits for ZELLE /
    VENMO / CASHAPP / WIRE / ACH / ATM). Rows in any other category are
    manual or Debt — never touched. Direction comes from word-bounded
    description keywords; rows with no direction signal stay as they are.

    Returns the number of rows re-classified.
    """
    transfer_cat, in_cat, out_cat = _transfer_categories(db)
    if in_cat is None or out_cat is None:
        return 0
    rows = _user_rows(db, user_id)
    classified = 0
    for t in rows:
        if t.transfer_pair_id is not None:
            continue
        if t.category_id is not None and (
            transfer_cat is None or t.category_id != transfer_cat.id
        ):
            continue
        text = f"{t.merchant_name or ''} {t.description or ''}"
        if _match_any(text, _TRANSFER_IN_PATTERNS):
            t.category_id = in_cat.id
            classified += 1
        elif _match_any(text, _TRANSFER_OUT_PATTERNS):
            t.category_id = out_cat.id
            classified += 1

    if classified:
        LOG.info(
            "Transfer classification: user=%s classified %d row(s)",
            user_id, classified,
        )
    return classified


def run_transfer_detection(db: Session, user_id: int) -> dict[str, Any]:
    """Run the full transfer pipeline: pair internal transfers first,
    then classify the remaining unpaired rows by direction.

    Returns ``{"pairs": int, "classified": int}`` so callers can log
    or surface the counts. Does NOT commit — callers own the commit
    (mirrors ``categorize_transactions``'s flush-at-the-end contract).
    """
    pairs = pair_internal_transfers(db, user_id)
    classified = classify_external_transfers(db, user_id)
    return {"pairs": pairs, "classified": classified}
