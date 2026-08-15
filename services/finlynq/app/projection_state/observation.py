"""Authoritative, privacy-safe account balance observation helpers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.models import Account, AccountBalanceObservation

MAX_BALANCE_OBSERVATION_AGE_DAYS = 7
NEAR_EXPIRY_DAYS = 6
MAX_BALANCE_MAGNITUDE = Decimal("1E+24")
SOURCE_KIND = "operator_confirmed"
ACTOR_CATEGORY = "local_operator"


class BalanceObservationError(ValueError):
    """Stable non-sensitive operator or readiness failure."""


@dataclass(frozen=True)
class BalanceObservationState:
    state: str
    reason_code: str
    observed_at: datetime | None = None
    event_id: str | None = None


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise BalanceObservationError("invalid_observation_timestamp")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def stored_utc(value: datetime) -> datetime:
    return utc(value)


def validate_balance(value: Any) -> str:
    """Validate the stored legacy balance without changing or returning it."""
    if isinstance(value, bool) or value is None:
        raise BalanceObservationError("balance_invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BalanceObservationError("balance_invalid") from exc
    if not parsed.is_finite() or parsed.copy_abs() > MAX_BALANCE_MAGNITUDE:
        raise BalanceObservationError("balance_invalid")
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def balance_state_hash(account: Account) -> str:
    """Bind the observation to the current server-side account state.

    The balance representation is hashed, never persisted or logged. Account
    identity, ownership, activity, and type are included so the hash cannot be
    replayed against a different scope.
    """
    payload = {
        "account_id": int(account.id),
        "account_type": account.account_type,
        "balance_representation": validate_balance(account.current_balance),
        "is_active": bool(account.is_active),
        "user_id": int(account.user_id),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def observation_intent_hash(
    accounts: list[Account], *, observed_at: datetime, source_kind: str = SOURCE_KIND,
) -> str:
    if source_kind != SOURCE_KIND:
        raise BalanceObservationError("invalid_observation_source")
    observed = utc(observed_at)
    payload = {
        "observed_at": observed.isoformat(timespec="microseconds"),
        "source_kind": source_kind,
        "accounts": [
            {"account_id": int(account.id), "precondition_hash": balance_state_hash(account)}
            for account in sorted(accounts, key=lambda item: int(item.id))
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def idempotency_hash(intent_hash: str, account_id: int) -> str:
    return hashlib.sha256(f"{intent_hash}:account:{int(account_id)}".encode("ascii")).hexdigest()


def _latest_event(db: Session, account: Account) -> AccountBalanceObservation | None:
    return (
        db.query(AccountBalanceObservation)
        .filter(
            AccountBalanceObservation.account_id == account.id,
            AccountBalanceObservation.user_id == account.user_id,
        )
        .order_by(AccountBalanceObservation.recorded_at.desc(), AccountBalanceObservation.id.desc())
        .first()
    )


def account_observation_state(db: Session, account: Account, *, now: datetime) -> BalanceObservationState:
    """Return a safe state for one active account; never skip a bad row."""
    current_time = utc(now)
    if not account.is_active:
        return BalanceObservationState("excluded", "balance_observation_inactive")
    try:
        current_hash = balance_state_hash(account)
    except BalanceObservationError as exc:
        return BalanceObservationState("blocked", str(exc))
    event = _latest_event(db, account)
    if event is None:
        return BalanceObservationState("blocked", "balance_observation_unknown")
    if event.source_kind != SOURCE_KIND or event.actor_category != ACTOR_CATEGORY:
        return BalanceObservationState("blocked", "balance_observation_incomplete")
    try:
        observed = stored_utc(event.observed_at)
    except BalanceObservationError:
        return BalanceObservationState("blocked", "balance_observation_incomplete")
    if observed > current_time:
        return BalanceObservationState("blocked", "balance_observation_future", observed, event.id)
    if event.precondition_hash != current_hash:
        return BalanceObservationState("blocked", "balance_observation_changed", observed, event.id)
    if account.last_sync is None:
        return BalanceObservationState("blocked", "balance_observation_incomplete", observed, event.id)
    try:
        last_sync = stored_utc(account.last_sync)
    except BalanceObservationError:
        return BalanceObservationState("blocked", "balance_observation_incomplete", observed, event.id)
    if last_sync != observed:
        return BalanceObservationState("blocked", "balance_observation_conflict", observed, event.id)
    age = current_time - observed
    if age > timedelta(days=MAX_BALANCE_OBSERVATION_AGE_DAYS):
        return BalanceObservationState("blocked", "balance_observation_stale", observed, event.id)
    if age > timedelta(days=NEAR_EXPIRY_DAYS):
        return BalanceObservationState("ready", "balance_observation_nearing_expiry", observed, event.id)
    return BalanceObservationState("ready", "balance_observation_current", observed, event.id)


def derive_balance_observation_state(db: Session, *, user_id: int, now: datetime) -> BalanceObservationState:
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.is_active.is_(True))
        .order_by(Account.id.asc())
        .all()
    )
    if not accounts:
        return BalanceObservationState("blocked", "balance_observation_incomplete")
    states = [account_observation_state(db, account, now=now) for account in accounts]
    for reason in (
        "balance_invalid", "balance_observation_changed", "balance_observation_conflict",
        "balance_observation_future", "balance_observation_stale", "balance_observation_unknown",
        "balance_observation_incomplete",
    ):
        match = next((state for state in states if state.reason_code == reason), None)
        if match is not None:
            return BalanceObservationState("blocked", reason, match.observed_at, match.event_id)
    if any(state.reason_code == "balance_observation_nearing_expiry" for state in states):
        return BalanceObservationState("ready", "balance_observation_nearing_expiry")
    return BalanceObservationState("ready", "balance_observation_current")
