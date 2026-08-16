"""Bounded local-operator batch confirmation of account evidence.

Dry-run is the default.  The command resolves every active owned account that
lacks authoritative USD currency evidence or a fresh balance observation and
reports only counts plus a bounded intent hash — never balances, account
numbers, names, transactions, holdings, credentials, or provider payloads.

Writes are append-only and idempotent: a retry after a partial failure replays
the already-recorded currency events and applies only the missing balance
observations.  No stored balance is ever changed and no existing evidence is
ever rewritten.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, User
from app.projection_state.balance_evidence import (
    BalanceEvidenceError,
    account_balance_evidence_state,
    balance_precondition_hash,
    observation_intent_hash,
)
from app.projection_state.confirm_balance_observations import (
    BalanceObservationError,
    confirm_all_active_balances_current,
)
from app.projection_state.currency import (
    CurrencyEvidenceError,
    effective_currency_for_account,
    record_currency_evidence,
)
from app.projection_state.observation import balance_state_hash

SOURCE_KIND = "operator_confirmed"
ACTOR_CATEGORY = "local_operator"


class BatchConfirmationError(ValueError):
    """Stable sanitized batch-confirmation failure."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise BatchConfirmationError("batch_observation_timestamp_invalid")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_user_and_accounts(db: Session, user_sub: str) -> tuple[User, list[Account]]:
    user = db.scalar(select(User).where(User.local_user_sub == user_sub, User.is_active.is_(True)))
    if user is None:
        raise BatchConfirmationError("operator_user_unavailable")
    accounts = list(db.scalars(select(Account).where(
        Account.user_id == user.id, Account.is_active.is_(True)
    ).order_by(Account.id.asc())))
    if not accounts:
        raise BatchConfirmationError("batch_confirmation_incomplete")
    return user, accounts


def _pending_scope(
    db: Session, accounts: list[Account], *, now: datetime,
) -> tuple[list[Account], list[Account], list[Account]]:
    """Return (currency_pending, balance_pending, both_pending) active accounts."""
    currency_pending: list[Account] = []
    balance_pending: list[Account] = []
    for account in accounts:
        currency_state = effective_currency_for_account(
            db, account_id=account.id, user_id=account.user_id, now=now,
        )
        balance_state = account_balance_evidence_state(db, account, now=now)
        if currency_state.state != "ready":
            currency_pending.append(account)
        if balance_state.state != "ready":
            balance_pending.append(account)
    both = sorted(
        {int(account.id) for account in currency_pending} & {int(account.id) for account in balance_pending},
    )
    return currency_pending, balance_pending, both


def _intent_hash(accounts: list[Account], *, observed_at: datetime) -> str:
    observed = _utc(observed_at)
    payload = {
        "observed_at": observed.isoformat(timespec="microseconds"),
        "source_kind": SOURCE_KIND,
        "accounts": [
            {
                "account_id": int(account.id),
                "currency_precondition": balance_state_hash(account),
                "balance_precondition": balance_precondition_hash(account),
            }
            for account in sorted(accounts, key=lambda item: int(item.id))
        ],
    }
    import hashlib
    import json

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _apply_currency_evidence(db: Session, accounts: list[Account], *, observed_at: datetime) -> int:
    recorded = 0
    for account in accounts:
        key = f"operator-confirmed:{int(account.user_id)}:{int(account.id)}:USD"
        result = record_currency_evidence(
            db, account=account, event_type="assertion", source_kind=SOURCE_KIND,
            code="USD", observed_at=observed_at,
            source_reference=f"operator-confirmed:{int(account.user_id)}",
            actor_category=ACTOR_CATEGORY, idempotency_key=key, apply=True,
        )
        if result["status"] == "recorded":
            recorded += 1
    return recorded


def confirm_new_active_accounts(
    db: Session,
    *,
    user_sub: str,
    observed_at: datetime,
    apply: bool = False,
    confirm: bool = False,
    expected_intent_hash: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Preview or atomically append USD currency + balance evidence for accounts lacking it."""
    if apply and not confirm:
        raise BatchConfirmationError("explicit_batch_confirmation_required")
    observation_time = _utc(observed_at)
    current_time = _utc(now or datetime.now(timezone.utc))
    if observation_time > current_time:
        raise BatchConfirmationError("batch_observation_timestamp_in_future")
    user, accounts = _resolve_user_and_accounts(db, user_sub)
    currency_pending, balance_pending, both = _pending_scope(db, accounts, now=current_time)
    pending_ids = sorted(
        {int(account.id) for account in currency_pending} | {int(account.id) for account in balance_pending},
    )
    if not pending_ids:
        return {
            "mode": "dry_run" if not apply else "apply",
            "status": "no_pending_accounts",
            "eligible_active_accounts": len(accounts),
            "currency_pending": 0,
            "balance_pending": 0,
            "observed_at": observation_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "intent_hash": None,
        }
    pending = [account for account in accounts if int(account.id) in pending_ids]
    intent_hash = _intent_hash(pending, observed_at=observation_time)
    if expected_intent_hash is not None and expected_intent_hash != intent_hash:
        raise BatchConfirmationError("batch_intent_mismatch")
    if apply and not expected_intent_hash:
        raise BatchConfirmationError("batch_intent_required")

    preview = {
        "mode": "dry_run" if not apply else "apply",
        "status": "pending_confirmation",
        "eligible_active_accounts": len(accounts),
        "currency_pending": len(currency_pending),
        "balance_pending": len(balance_pending),
        "accounts_requiring_both": len(both),
        "observed_at": observation_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "intent_hash": intent_hash,
    }
    if not apply:
        return preview

    # Currency events first (idempotent per-account keys), then scoped balance
    # observations in their own locked transaction.  A partial failure leaves a
    # safe, retryable state: currency replays idempotently and balance applies
    # only the remaining accounts.
    try:
        currency_ids = [int(account.id) for account in currency_pending]
        if currency_ids:
            currency_accounts = [account for account in accounts if int(account.id) in currency_ids]
            recorded = _apply_currency_evidence(db, currency_accounts, observed_at=observation_time)
            db.commit()
        balance_ids = [int(account.id) for account in balance_pending]
        if balance_ids:
            balance_accounts = [account for account in accounts if int(account.id) in balance_ids]
            balance_intent = observation_intent_hash(balance_accounts, observed_at=observation_time)
            confirm_all_active_balances_current(
                db,
                user_sub=user_sub,
                observed_at=observation_time,
                apply=True,
                confirm_all_active=True,
                expected_intent_hash=balance_intent,
                account_ids=balance_ids,
                now=current_time,
            )
    except (BalanceObservationError, BalanceEvidenceError, CurrencyEvidenceError) as exc:
        db.rollback()
        raise BatchConfirmationError(str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise BatchConfirmationError("batch_confirmation_write_failed") from exc

    preview["status"] = "confirmed"
    preview["currency_recorded"] = recorded if currency_ids else 0
    preview["balance_confirmed"] = len(balance_ids)
    return preview
