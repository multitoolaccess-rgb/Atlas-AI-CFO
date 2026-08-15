"""Bounded local-operator account-currency evidence command.

Dry-run is the default.  This command never reads or prints balances,
transactions, account names, account numbers, credentials, or provider data.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Account, User
from app.projection_state.currency import (
    CurrencyEvidenceConflict,
    CurrencyEvidenceError,
    record_currency_evidence,
)

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
    idempotency_key: str | None = None,
) -> dict[str, object]:
    """Append explicit operator assertions atomically; dry-run by default."""
    if user_id <= 0:
        raise ValueError("invalid_user_id")
    requested = _parse_account_ids([str(value) for value in account_ids])
    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise ValueError("unknown_or_unowned_account")
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.id.in_(requested), Account.is_active.is_(True))
        .order_by(Account.id.asc())
        .all()
    )
    if len(accounts) != len(requested):
        raise ValueError("unknown_or_unowned_account")
    timestamp = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result_accounts: list[dict[str, object]] = []
    # Validate all targets before appending any event.
    for account in accounts:
        key = idempotency_key or f"operator-confirmed:{user_id}:{account.id}:{currency}"
        preview = record_currency_evidence(
            db, account=account, event_type="assertion", source_kind="operator_confirmed",
            code=currency, observed_at=timestamp, source_reference=f"operator-confirmed:{user_id}",
            actor_category="local_operator", idempotency_key=key, apply=False,
        )
        result_accounts.append({"account_id": account.id, "currency_code": currency, "status": preview["status"]})
    if not apply:
        return {"mode": "dry_run", "user_id": user_id, "accounts": result_accounts}
    try:
        for account in accounts:
            key = idempotency_key or f"operator-confirmed:{user_id}:{account.id}:{currency}"
            record_currency_evidence(
                db, account=account, event_type="assertion", source_kind="operator_confirmed",
                code=currency, observed_at=timestamp, source_reference=f"operator-confirmed:{user_id}",
                actor_category="local_operator", idempotency_key=key, apply=True,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"mode": "apply", "user_id": user_id, "accounts": result_accounts}


def record_operator_event(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    event_type: str,
    currency: str | None,
    supersedes_event_id: str | None,
    idempotency_key: str,
    source_reference: str,
    apply: bool,
) -> dict[str, object]:
    """Record one explicitly scoped correction or revocation event."""
    account = db.query(Account).filter(Account.id == account_id, Account.user_id == user_id, Account.is_active.is_(True)).first()
    if account is None:
        raise ValueError("unknown_or_unowned_account")
    return record_currency_evidence(
        db, account=account, event_type=event_type,
        source_kind="correction" if event_type == "correction" else "revocation",
        code=currency, observed_at=datetime.now(timezone.utc),
        source_reference=source_reference, actor_category="local_operator",
        idempotency_key=idempotency_key, supersedes_event_id=supersedes_event_id,
        reason_code=f"operator_{event_type}", apply=apply,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--account-id", required=True, action="append")
    parser.add_argument("--currency")
    parser.add_argument("--event-type", choices=("assertion", "correction", "revocation"), default="assertion")
    parser.add_argument("--supersedes-event-id")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--source-reference", default="operator-confirmed:cli")
    parser.add_argument("--apply", action="store_true", help="Persist the event; without this flag the command is a dry-run.")
    args = parser.parse_args(argv)
    try:
        account_ids = _parse_account_ids(args.account_id)
        with SessionLocal() as db:
            if args.event_type == "assertion":
                if not args.currency:
                    raise ValueError("currency_required")
                result = confirm_currency(
                    db, user_id=args.user_id, account_ids=account_ids,
                    currency=args.currency, apply=args.apply,
                    idempotency_key=args.idempotency_key,
                )
            elif len(account_ids) != 1 or not args.idempotency_key or not args.supersedes_event_id:
                raise ValueError("correction_or_revocation_requires_single_account_idempotency_and_supersedes")
            else:
                result = record_operator_event(
                    db, user_id=args.user_id, account_id=account_ids[0], event_type=args.event_type,
                    currency=args.currency, supersedes_event_id=args.supersedes_event_id,
                    idempotency_key=args.idempotency_key, source_reference=args.source_reference,
                    apply=args.apply,
                )
                if args.apply:
                    db.commit()
    except (ValueError, CurrencyEvidenceError, CurrencyEvidenceConflict) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
