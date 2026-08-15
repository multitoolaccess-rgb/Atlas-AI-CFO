"""Bounded local-operator confirmation of exact-cent account balances.

The compatibility ``Account.last_sync`` and legacy observation audit remain
untouched in meaning. Every new confirmation also appends a separate
NUMERIC(38,2) authoritative evidence event; no stored balance is changed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountBalanceEvidence, AccountBalanceObservation, User
from app.projection_state.balance_evidence import (
    ACTOR_CATEGORY,
    SOURCE_KIND,
    BalanceEvidenceError,
    balance_precondition_hash,
    confirmed_balance,
    evidence_state_hash,
    exact_balance,
    idempotency_hash,
    observation_intent_hash,
    utc,
)
from app.projection_state.observation import BalanceObservationError, balance_state_hash


def _resolve_active_accounts(db: Session, user_sub: str) -> list[Account]:
    user = db.scalar(select(User).where(User.local_user_sub == user_sub, User.is_active.is_(True)))
    if user is None:
        raise BalanceObservationError("operator_user_unavailable")
    accounts = list(db.scalars(select(Account).where(
        Account.user_id == user.id, Account.is_active.is_(True)
    ).order_by(Account.id.asc())))
    if not accounts:
        raise BalanceObservationError("balance_observation_incomplete")
    return accounts


def _exact_preconditions(accounts: list[Account]) -> dict[int, tuple[Any, Any, str]]:
    result: dict[int, tuple[Any, Any, str]] = {}
    for account in accounts:
        try:
            exact = exact_balance(account.current_balance)
            confirmed = confirmed_balance(exact)
            result[int(account.id)] = (exact, confirmed, balance_precondition_hash(account, exact))
        except BalanceEvidenceError as exc:
            raise BalanceObservationError(str(exc)) from None
    return result


def _existing_for_intent(db: Session, account: Account, key_hash: str) -> AccountBalanceEvidence | None:
    return db.scalar(select(AccountBalanceEvidence).where(
        AccountBalanceEvidence.account_id == account.id,
        AccountBalanceEvidence.user_id == account.user_id,
        AccountBalanceEvidence.idempotency_key_hash == key_hash,
    ))


def _preview_status(db: Session, account: Account, *, key_hash: str, confirmed: Any, precondition: str, observed_at: datetime) -> str:
    existing = _existing_for_intent(db, account, key_hash)
    if existing is None:
        return "ready_to_apply"
    if (
        existing.event_type == "assertion"
        and existing.amount is not None
        and confirmed_balance(existing.amount).confirmed_canonical == confirmed.confirmed_canonical
        and existing.precondition_hash == precondition
        and utc(existing.observed_at) == observed_at
    ):
        return "idempotent_replay"
    raise BalanceObservationError("observation_replay_conflict")


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
    """Preview or atomically append exact-cent evidence for every active account."""
    if apply and not confirm_all_active:
        raise BalanceObservationError("explicit_all_active_confirmation_required")
    observation_time = utc(observed_at)
    current_time = utc(now or datetime.now(timezone.utc))
    if observation_time > current_time:
        raise BalanceObservationError("observation_timestamp_in_future")
    accounts = _resolve_active_accounts(db, user_sub)
    preconditions = _exact_preconditions(accounts)
    try:
        intent_hash = observation_intent_hash(accounts, observed_at=observation_time)
    except BalanceEvidenceError as exc:
        raise BalanceObservationError(str(exc)) from None
    if expected_intent_hash is not None and expected_intent_hash != intent_hash:
        raise BalanceObservationError("observation_intent_mismatch")
    if apply and not expected_intent_hash:
        raise BalanceObservationError("observation_intent_required")

    previews: list[dict[str, str]] = []
    for account in accounts:
        key_hash = idempotency_hash(intent_hash, int(account.id))
        previews.append({"status": _preview_status(
            db, account, key_hash=key_hash, confirmed=preconditions[int(account.id)][1],
            precondition=preconditions[int(account.id)][2], observed_at=observation_time,
        )})
    if not apply:
        return {
            "mode": "dry_run",
            "eligible_active_accounts": len(accounts),
            "observed_at": observation_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "intent_hash": intent_hash,
            "accounts": previews,
        }

    account_ids = [int(account.id) for account in accounts]
    owner_id = int(accounts[0].user_id)
    try:
        # SQLite's deferred transaction would leave a race between the dry-run
        # read and the first write. BEGIN IMMEDIATE reserves the writer slot;
        # PostgreSQL uses row locks for the same bounded scope.
        if db.bind is not None and db.bind.dialect.name == "sqlite":
            db.rollback()
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            refreshed = list(db.scalars(select(Account).where(
                Account.user_id == owner_id, Account.is_active.is_(True)
            ).order_by(Account.id.asc())))
        else:
            refreshed = list(db.scalars(select(Account).where(
                Account.user_id == owner_id, Account.is_active.is_(True)
            ).with_for_update().order_by(Account.id.asc())))
        if [int(account.id) for account in refreshed] != account_ids:
            raise BalanceObservationError("balance_observation_scope_changed")
        refreshed_preconditions = _exact_preconditions(refreshed)
        for account in refreshed:
            expected = preconditions[int(account.id)]
            if refreshed_preconditions[int(account.id)][2] != expected[2]:
                raise BalanceObservationError("balance_observation_precondition_failed")
            if account.last_sync is not None and utc(account.last_sync) > observation_time:
                raise BalanceObservationError("balance_observation_conflict")

        for account in refreshed:
            account_id = int(account.id)
            exact, confirmed, precondition = refreshed_preconditions[account_id]
            key_hash = idempotency_hash(intent_hash, account_id)
            existing = _existing_for_intent(db, account, key_hash)
            if existing is not None:
                if _preview_status(
                    db, account, key_hash=key_hash, confirmed=confirmed,
                    precondition=precondition, observed_at=observation_time,
                ) != "idempotent_replay":
                    raise BalanceObservationError("observation_replay_conflict")
                continue
            event_id = str(uuid.uuid4())
            db.add(AccountBalanceEvidence(
                id=event_id,
                user_id=account.user_id,
                account_id=account.id,
                event_type="assertion",
                source_kind=SOURCE_KIND,
                actor_category=ACTOR_CATEGORY,
                currency_code="USD",
                amount=confirmed.confirmed_value,
                observed_at=observation_time,
                precondition_hash=precondition,
                state_hash=evidence_state_hash(account, exact, observation_time),
                observation_intent_hash=intent_hash,
                idempotency_key_hash=key_hash,
            ))
            # Preserve the existing timestamp/audit compatibility contract;
            # this row is not authoritative and is never used to infer cents.
            db.add(AccountBalanceObservation(
                id=str(uuid.uuid4()),
                user_id=account.user_id,
                account_id=account.id,
                source_kind=SOURCE_KIND,
                actor_category=ACTOR_CATEGORY,
                observed_at=observation_time,
                recorded_at=current_time,
                precondition_hash=balance_state_hash(account),
                observation_intent_hash=intent_hash,
                idempotency_key_hash=key_hash,
            ))
            account.last_sync = observation_time
        db.commit()
    except BalanceObservationError:
        db.rollback()
        raise
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
