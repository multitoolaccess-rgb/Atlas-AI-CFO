"""Phase 52+ — one-shot data migration: sign-flip stored transactions
on credit_account_types accounts whose imports were misclassified as
``checking`` at upload time (so the importer's sign-flip never ran).

WHY THIS SCRIPT EXISTS
======================

The pre-Phase-52 import-time account-type detection scanned ONLY
transaction descriptions for keywords like ``"credit card"`` /
``"payment due"``. When the bank's transaction descriptions WEREN'T
loaded with their bank statement header (the most common real-world
case for PDF statements -- the header lives on page 1, the
transaction rows on subsequent pages), the heuristic fell through to
``"checking"``. Result:

- ``account_type`` was set to ``"checking"`` at import time.
- The ``if _txn_acct.account_type in CREDIT_ACCOUNT_TYPES: amount = -amount``
  block in ``app/routes/imports.py`` did NOT fire (checking isn't in
  CREDIT_ACCOUNT_TYPES).
- Every transaction was stored at its raw-statement sign:
  purchases = positive, payments = negative.
- ``recalculate_account_balance(account_id)`` summed them:
  ``SUM(amount)`` = purchases - payments = the bank's "current
  balance" = a POSITIVE number that REPRESENTS net debt, not an
  asset.

If a user then manually corrected the type via
``PUT /api/accounts/{id}`` (changing the type from ``checking`` to
``credit_card``), the historical transactions were never re-flipped.
The dashboard formula in ``app/routes/dashboard.py`` then reads the
stored ``Account.current_balance`` directly for the credit_card
case -- a positive ``+17,400.82`` (debt) was ADDED to net worth
instead of subtracted.

This script fixes the historical data:

1. Finds every account where ``account_type in {'credit_card',
   'loan', 'mortgage'}``, ``is_active=True``, ``current_balance > 0``,
   AND the description carries the misclassification marker
   ``"type=checking"`` (recorded at upload time, only present on
   pre-Phase-52 imports).
2. For each such account, multiplies every transaction's ``amount``
   by ``-1``.
3. Recalculates the account's ``current_balance`` from the
   sign-flipped ledger.
4. Updates the ``description`` so a subsequent migration tool or
   operator can spot the fix has been applied.

Idempotent: a second run finds the now-negative balances and
balances-without-the-marker and SKIPS them. Safe to re-run.

Dry-run by default: pass ``--apply`` to commit. Prints a summary
of which accounts would change so the operator signs off.

Usage
=====

.. code-block:: bash

    cd services/rules-service
    source ../../.venv/bin/activate

    # 1. Preview what would change (no writes):
    python scripts/fix_credit_account_sign_flip.py

    # 2. Apply once you've reviewed the preview:
    python scripts/fix_credit_account_sign_flip.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow ``python scripts/fix_credit_account_sign_flip.py`` from any
# cwd by injecting the rules-service root onto sys.path before
# importing the app package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func  # noqa: E402

from app.account_types import CREDIT_ACCOUNT_TYPES  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Account, Transaction  # noqa: E402

# Marker recorded on pre-Phase-52 imports: the description template
# in Phase 37 / 38 routes was
#   "Imported PDF from {filename} ({N} transactions, type={pdf_type})"
# When ``pdf_type`` resolved to ``"checking"`` for what was actually a
# credit-card statement, the marker persists in the row forever
# unless we update it. Used here as a HEURISTIC (not the sole
# criterion -- we ALSO require balance > 0) so a future Phase that
# introduces a ``type=checking`` diagnostic for a different reason
# wouldn't silently re-trigger this migration.
_MISCLASSIFICATION_MARKER = "type=checking"
_POST_FIX_MARKER = "type=credit_account [sign-flip-migrated]"


def _find_candidates(db) -> list[Account]:
    """Accounts that need the sign-flip.

    Two-condition heuristic: the account was RE-classified to a
    credit-account type (so currently typed credit_card/loan/mortgage)
    AND its stored balance is positive (raw-statement semantics, NOT
    the post-sign-flip negative-debt convention) AND its description
    carries the pre-Phase-52 misclassification marker -- so we know
    the sign-flip was skipped at upload time.

    Idempotent: a row whose ``current_balance`` is already negative
    OR whose ``description`` carries the post-fix marker is skipped
    unless it ALSO matches the marker (defensive: a re-run on a
    pathological partially-migrated dataset shouldn't 500).
    """
    return (
        db.query(Account)
        .filter(
            Account.account_type.in_(list(CREDIT_ACCOUNT_TYPES)),
            Account.is_active.is_(True),
            # ``+ debt > 0`` is the smoking gun -- a correctly
            # imported credit_card balance is negative.
            Account.current_balance > 0.0,
            Account.description.contains(_MISCLASSIFICATION_MARKER),
        )
        .all()
    )


def _find_suspicious_unflipped(db, candidates: list[Account]) -> list[Account]:
    """Reviewer feedback: silent-skip detection.

    A credit-type account whose balance is still positive but whose
    description DOESN'T carry the marker is a candidate that slipped
    past :func:`_find_candidates` -- typically because the user
    edited the description via the Accounts-page Edit modal and the
    marker went away. Without this pass, the operator would see
    "no candidates" and conclude the DB is clean, when in fact a
    still-broken account exists.

    Returns the LIST (not count) so the operator can inspect each
    row before deciding to manually flip it via SQL.
    """
    candidate_ids = {acct.id for acct in candidates}
    rows = (
        db.query(Account)
        .filter(
            Account.account_type.in_(list(CREDIT_ACCOUNT_TYPES)),
            Account.is_active.is_(True),
            Account.current_balance > 0.0,
            ~Account.description.contains(_MISCLASSIFICATION_MARKER)
            if hasattr(Account.description, "notilike")
            else True,  # SQLAlchemy will handle the ``contains`` semantics
        )
        .all()
    )
    # Above ``~Account.description.contains(...)`` is the SQLAlchemy
    # NOT-contaions idiom; we double-check in Python because the
    # attribute-level ``notilike`` is dialect-specific.
    return [
        r for r in rows
        if r.id not in candidate_ids
        and r.description
        and _MISCLASSIFICATION_MARKER not in r.description
    ]


def _transaction_sign_histogram(db, account_id: int) -> tuple[int, int]:
    """Reviewer feedback: partial-migration detection.

    A correctly imported credit_card after sign-flip should have
    NEGATIVE-amount purchases and POSITIVE-amount payments -- so a
    MIXED-sign histogram (some positive, some negative) with mostly
    positive rows is a smoking gun for raw-statement data that
    never got flipped. A correctly sign-flipped account would have
    a similar mixed-sign histogram (purchase-negative, payment-
    positive), so the histogram alone is informative -- it's the
    BALANCE sign that definitively tells us "needs flip".

    Returns ``(positive_amount_count, negative_amount_count)`` so
    the operator can spot anomaly patterns before committing.
    """
    pos = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.account_id == account_id,
            Transaction.amount > 0.0,
        )
        .scalar()
    ) or 0
    neg = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.account_id == account_id,
            Transaction.amount < 0.0,
        )
        .scalar()
    ) or 0
    return int(pos), int(neg)


def _preview(db) -> list[tuple[Account, int, float, tuple[int, int]]]:
    """Return ``[(account, txn_count, new_balance, sign_histogram)]``
    for each candidate.

    Pure read; no db.commit. Used by the default dry-run path.
    The histogram lets the operator spot accounts whose stored
    transaction signs are mixed in unusual proportions -- a
    forensic clue for partial-migration-by-hand state.
    """
    out: list[tuple[Account, int, float, tuple[int, int]]] = []
    for acct in _find_candidates(db):
        txn_count = (
            db.query(Transaction)
            .filter(Transaction.account_id == acct.id)
            .count()
        )
        # New balance is the negation of the current (positive)
        # sum, because sign-flipping every amount by -1 inverts the
        # total. Equivalent to re-running ``recalculate_account_balance``
        # after flipping, but pre-computing here for the preview.
        new_balance = -float(acct.current_balance or 0.0)
        histogram = _transaction_sign_histogram(db, acct.id)
        out.append((acct, txn_count, new_balance, histogram))
    return out


def _apply(db, candidates: list[Account]) -> list[tuple[int, str, float, float]]:
    """Apply the sign-flip + balance recalc to each candidate.

    Returns ``[(account_id, account_name, old_balance, new_balance)]``
    so the CLI can print a confirmation summary. Commits at the end.
    """
    summary: list[tuple[int, str, float, float]] = []
    for acct in candidates:
        old_balance = float(acct.current_balance or 0.0)
        txns = (
            db.query(Transaction)
            .filter(Transaction.account_id == acct.id)
            .all()
        )
        for txn in txns:
            txn.amount = -float(txn.amount)
            db.add(txn)
        db.flush()

        # Recompute from the now-flipped ledger -- DO NOT just take
        # ``-old_balance``, because the old balance was the *cached*
        # value the route stored at import time and might be stale
        # if any post-import mutation happened (e.g. a user deleted
        # a batch via ``DELETE /api/imports/batches/{id}`` and the
        # session never re-ran recalculate_account_balance).
        total = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
            .filter(Transaction.account_id == acct.id)
            .scalar()
        )
        new_balance = float(total)

        # Stamp the description with the post-fix marker so
        # idempotent re-runs are clean (and so an operator can spot
        # "this row was migrated" via SQL alone). Append at the tail
        # so the original diagnostic phrase (filename + count) is
        # preserved for ops grepping.
        original_desc = (acct.description or "").strip()
        if _POST_FIX_MARKER not in original_desc:
            acct.description = (
                f"{original_desc} | {_POST_FIX_MARKER}"
                if original_desc
                else _POST_FIX_MARKER
            )
        acct.current_balance = new_balance
        db.add(acct)

        summary.append((acct.id, acct.account_name, old_balance, new_balance))

    db.commit()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 52+ sign-flip migration for misclassified credit-account "
            "imports. Default: dry-run (preview only). Pass --apply to commit."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually commit the changes. Without this flag the script "
            "only prints the candidate list + predicted new balances."
        ),
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        candidates_preview = _preview(db)
        suspicious = _find_suspicious_unflipped(db, [a for a, _, _, _ in candidates_preview])

        if not candidates_preview and not suspicious:
            print(
                "No accounts need migration.\n"
                "(All credit-type balances are post-sign-flip negative, OR no "
                "accounts carry the pre-Phase-52 'type=checking' marker.)"
            )
            return 0

        mode_str = "DRY RUN (no writes)" if not args.apply else "APPLYING"
        print(f"=== {mode_str} ===\n")

        if candidates_preview:
            for acct, txn_count, new_balance, (pos, neg) in candidates_preview:
                print(
                    f"  Account #{acct.id}: name={acct.account_name!r} "
                    f"type={acct.account_type!r}"
                )
                print(
                    f"    description: {acct.description!r}"
                )
                print(
                    f"    current_balance: {acct.current_balance:.2f} "
                    f"-- post-fix expected: {new_balance:.2f}"
                )
                print(
                    f"    {txn_count} transactions will be sign-flipped "
                    f"(histogram: {pos} positive + {neg} negative)"
                )
                # Partial-migration-by-manual-edit warning. After
                # the sign-flip, a healthy credit_card ledger should
                # have negatives ~ purchases and positives ~ payments
                # (mixed signs is normal; the gross ratio tells us
                # whether the data looks balanced). A constant sign
                # (all-positive OR all-negative) of >=5 rows is a
                # smoking gun for already-flipped data + a bug
                # (e.g. only purchases imported, no payments).
                ratio_tag = ""
                if txn_count >= 5 and (pos == 0 or neg == 0):
                    ratio_tag = "  [!] UNUSUAL: all one-signed -- inspect before applying"
                print(f"    {ratio_tag}".rstrip())
                print()

        if suspicious:
            print(
                "=== SUSPICIOUS UNFLIPPED (description marker missing) ===\n"
                "These credit-type accounts still have a POSITIVE balance "
                "but lack the 'type=checking' marker (likely the user edited "
                "the description via the Accounts Edit modal). They were "
                "skipped by the marker-based heuristic -- inspect manually:\n"
            )
            for s in suspicious:
                pos, neg = _transaction_sign_histogram(db, s.id)
                print(
                    f"  Account #{s.id}: name={s.account_name!r} "
                    f"type={s.account_type!r} balance={s.current_balance:.2f} "
                    f"({pos} positive + {neg} negative txns)"
                )
                print(f"    description: {s.description!r}")
            print()

        if not args.apply:
            print(
                "Re-run with --apply to commit these changes.\n"
                "(The script is idempotent -- safe to dry-run repeatedly.)"
            )
            return 0

        # Confirm before applying only if running interactively AND
        # the suspicious-unflipped list is empty (i.e. the only rows
        # to flip are unambiguous). With suspicious rows present we
        # ALWAYS require y/N -- the operator should look at them first
        # even if they're not in the auto-flip set.
        if sys.stdin.isatty() and sys.stdout.isatty():
            if suspicious:
                print(
                    "(!) SUSPICIOUS rows above -- inspect before flipping the "
                    "candidates below."
                )
            answer = input("Apply these changes? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted; no changes made.")
                return 0

        summary = _apply(
            db, [acct for acct, _, _, _ in candidates_preview],
        )
        print("=== APPLIED ===\n")
        for account_id, account_name, old_balance, new_balance in summary:
            print(
                f"  Account #{account_id} ({account_name!r}): "
                f"{old_balance:.2f} -> {new_balance:.2f}"
            )
        if suspicious:
            print(
                "\nThe SUSPICIOUS rows above are still un-flipped. They were "
                "skipped because their description marker is missing or "
                "altered. Decide per-row:\n"
                "  - If they are correctly-imported+overpaid cards: leave as-is.\n"
                "  - If they are correctly-imported+debt but stored negative: leave as-is.\n"
                "  - If they are misclassified-imports whose marker was "
                "manually removed: run\n"
                "    UPDATE transactions SET amount = -amount WHERE account_id = ?;\n"
                "    UPDATE accounts SET current_balance = "
                "(SELECT SUM(amount) FROM transactions WHERE account_id = ?) "
                "WHERE id = ?;\n"
                "    by hand, matching the balance flip this script "
                "would have applied.\n"
            )
        print(
            "\nVerify via GET /api/dashboard/summary -- total_balance should "
            "now correctly subtract the credit-account balance (debt). "
            "Browse GET /api/accounts to confirm the sign-flipped ledger."
        )
        return 0
    except Exception:
        # Roll back any in-flight writes so a partial migration doesn't
        # leave the DB in a half-applied state.
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
