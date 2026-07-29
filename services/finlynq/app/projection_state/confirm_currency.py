"""Bounded operator-only confirmation of authoritative account currency.

Usage: ``python -m app.projection_state.confirm_currency --user-id 7
--account-id 11 --currency USD``.  It is dry-run unless ``--apply`` is given.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Account, User
from app.projection_state.currency import CurrencyEvidenceConflict, CurrencyEvidenceError, set_currency_evidence


MAX_ACCOUNT_IDS = 10


def _parse_account_ids(values: list[str]) -> list[int]:
    ids: list[int] = []
    for value in values:
        try:
            account_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_account_id") from exc
        if account_id <= 0 or account_id in ids:
            raise ValueError("invalid_account_id")
        ids.append(account_id)
    if not ids or len(ids) > MAX_ACCOUNT_IDS:
        raise ValueError("invalid_account_batch")
    return ids


def confirm_currency(
    db: Session,
    *,
    user_id: int,
    account_ids: list[int],
    currency: str,
    apply: bool,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    """Validate a bounded owned batch and apply it atomically only on request."""
    if user_id <= 0:
        raise ValueError("invalid_user_id")
    requested = _parse_account_ids([str(value) for value in account_ids])
    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise ValueError("unknown_or_unowned_account")
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.id.in_(requested))
        .order_by(Account.id.asc())
        .all()
    )
    if len(accounts) != len(requested):
        raise ValueError("unknown_or_unowned_account")
    timestamp = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reference = f"user-confirmed:{user_id}"
    # Validate every target before mutating any target, including conflicts.
    for account in accounts:
        probe = Account()
        probe.currency_code = account.currency_code
        probe.currency_source = account.currency_source
        probe.currency_observed_at = account.currency_observed_at
        probe.currency_source_reference = account.currency_source_reference
        try:
            set_currency_evidence(
                probe, code=currency, source="user_confirmed", observed_at=timestamp,
                source_reference=reference,
            )
        except (CurrencyEvidenceError, CurrencyEvidenceConflict) as exc:
            raise ValueError("currency_evidence_conflict") from exc
    result = {
        "mode": "apply" if apply else "dry_run",
        "user_id": user_id,
        "accounts": [{"account_id": account.id, "currency_code": currency} for account in accounts],
    }
    if not apply:
        return result
    try:
        for account in accounts:
            set_currency_evidence(
                account, code=currency, source="user_confirmed", observed_at=timestamp,
                source_reference=reference,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--account-id", required=True, action="append")
    parser.add_argument("--currency", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        account_ids = _parse_account_ids(args.account_id)
        with SessionLocal() as db:
            result = confirm_currency(
                db, user_id=args.user_id, account_ids=account_ids,
                currency=args.currency, apply=args.apply,
            )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
