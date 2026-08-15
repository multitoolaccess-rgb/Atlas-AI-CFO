"""Bounded local-operator confirmation of currently stored balances.

This command changes only ``Account.last_sync`` and appends hash-only audit
rows. It never changes ``current_balance`` or prints financial records.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountBalanceObservation, User
from app.projection_state.observation import (
    ACTOR_CATEGORY,
    SOURCE_KIND,
    BalanceObservationError,
    balance_state_hash,
    idempotency_hash,
    observation_intent_hash,
    utc,
)


def _key_hash(intent_hash: str, account_id: int) -> str:
    return idempotency_hash(intent_hash, account_id)


def _resolve_active_accounts(db: Session, user_sub: str) -> list[Account]:
    user = db.scalar(select(User).where(User.local_user_sub == user_sub, User.is_active.is_(True)))
    if user is None:
        raise BalanceObservationError("operator_user_unavailable")
    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.user_id == user.id, Account.is_active.is_(True))
            .order_by(Account.id.asc())
        )
    )
    if not accounts:
        raise BalanceObservationError("balance_observation_incomplete")
    return accounts


def _existing_for_intent(db: Session, account: Account, key_hash: str) -> AccountBalanceObservation | None:
    return db.scalar(
        select(AccountBalanceObservation).where(
            AccountBalanceObservation.account_id == account.id,
            AccountBalanceObservation.idempotency_key_hash == key_hash,
        )
    )


def confirm_all_active_balances_current(
    db: Session,
    *,
    user_sub: str,
    observed_at: datetime,
    apply: bool = False,
    confirm_all_active: bool = False,
    expected_intent_hash: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Preview or atomically confirm every active owned account.

    ``expected_intent_hash`` is mandatory for writes and binds the exact
    server-read balance state plus observation timestamp. A changed balance,
    owner scope, inactive row, or malformed value aborts the whole batch.
    """
    if apply and not confirm_all_active:
        raise BalanceObservationError("explicit_all_active_confirmation_required")
    observation_time = utc(observed_at)
    current_time = utc(now or datetime.now(timezone.utc))
    if observation_time > current_time:
        raise BalanceObservationError("observation_timestamp_in_future")
    accounts = _resolve_active_accounts(db, user_sub)
    intent_hash = observation_intent_hash(accounts, observed_at=observation_time)
    if expected_intent_hash is not None and expected_intent_hash != intent_hash:
        raise BalanceObservationError("observation_intent_mismatch")
    if apply and not expected_intent_hash:
        raise BalanceObservationError("observation_intent_required")

    preconditions = {int(account.id): balance_state_hash(account) for account in accounts}
    previews: list[dict[str, str]] = []
    for account in accounts:
        key_hash = _key_hash(intent_hash, int(account.id))
        existing = _existing_for_intent(db, account, key_hash)
        if existing is not None:
            if existing.precondition_hash != preconditions[int(account.id)] or utc(existing.observed_at) != observation_time:
                raise BalanceObservationError("observation_replay_conflict")
            status = "idempotent_replay"
        else:
            status = "ready_to_apply"
        previews.append({"status": status})

    if not apply:
        return {
            "mode": "dry_run",
            "eligible_active_accounts": len(accounts),
            "observed_at": observation_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "intent_hash": intent_hash,
            "accounts": previews,
        }

    # Refresh the rows inside the write transaction and compare the exact
    # precondition hash again. This closes the dry-run -> apply race.
    refreshed = list(
        db.scalars(
            select(Account)
            .where(Account.user_id == accounts[0].user_id, Account.is_active.is_(True))
            .order_by(Account.id.asc())
        )
    )
    if [int(account.id) for account in refreshed] != [int(account.id) for account in accounts]:
        raise BalanceObservationError("balance_observation_scope_changed")
    for account in refreshed:
        current_hash = balance_state_hash(account)
        if current_hash != preconditions[int(account.id)]:
            raise BalanceObservationError("balance_observation_precondition_failed")
        if account.last_sync is not None and utc(account.last_sync) > observation_time:
            raise BalanceObservationError("balance_observation_conflict")

    try:
        for account in refreshed:
            key_hash = _key_hash(intent_hash, int(account.id))
            existing = _existing_for_intent(db, account, key_hash)
            if existing is None:
                db.add(AccountBalanceObservation(
                    id=str(uuid.uuid4()),
                    user_id=account.user_id,
                    account_id=account.id,
                    source_kind=SOURCE_KIND,
                    actor_category=ACTOR_CATEGORY,
                    observed_at=observation_time,
                    recorded_at=current_time,
                    precondition_hash=preconditions[int(account.id)],
                    observation_intent_hash=intent_hash,
                    idempotency_key_hash=key_hash,
                ))
            account.last_sync = observation_time
            db.add(account)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise BalanceObservationError("balance_observation_write_failed") from exc

    return {
        "mode": "apply",
        "eligible_active_accounts": len(accounts),
        "observed_at": observation_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "intent_hash": intent_hash,
        "accounts": previews,
    }
