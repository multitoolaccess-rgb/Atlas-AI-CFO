"""Exact-cent authoritative balance evidence helpers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountBalanceEvidence

MAX_AGE_DAYS = 7
MAX_NUMERIC_38_2 = Decimal("999999999999999999999999999999999999.99")
SOURCE_KIND = "operator_confirmed"
ACTOR_CATEGORY = "local_operator"


class BalanceEvidenceError(ValueError):
    """Stable sanitized evidence failure."""


@dataclass(frozen=True)
class ExactBalance:
    value: Decimal
    canonical: str


@dataclass(frozen=True)
class BalanceEvidenceState:
    state: str
    reason_code: str
    observed_at: datetime | None = None
    event_id: str | None = None
    amount: Decimal | None = None


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise BalanceEvidenceError("balance_observation_timestamp_invalid")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def exact_balance(value: Any) -> ExactBalance:
    """Read, validate, and render a balance without rounding or quantizing it."""
    if isinstance(value, bool) or value is None:
        raise BalanceEvidenceError("balance_amount_invalid")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BalanceEvidenceError("balance_amount_invalid") from exc
    if not parsed.is_finite() or parsed.copy_abs() > MAX_NUMERIC_38_2:
        raise BalanceEvidenceError("balance_amount_precision_unavailable")
    rendered = format(parsed, "f")
    sign = "-" if rendered.startswith("-") else ""
    unsigned = rendered[1:] if sign else rendered
    integral, _, fractional = unsigned.partition(".")
    if len(fractional) > 2:
        raise BalanceEvidenceError("balance_amount_precision_unavailable")
    fractional = fractional.ljust(2, "0")
    canonical = f"{sign}{integral}.{fractional}"
    if canonical == "-0.00":
        canonical = "0.00"
    return ExactBalance(parsed, canonical)


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def balance_precondition_hash(account: Account, exact: ExactBalance | None = None) -> str:
    exact = exact or exact_balance(account.current_balance)
    return _digest({
        "account_id": int(account.id),
        "account_type": account.account_type,
        "amount": exact.canonical,
        "is_active": bool(account.is_active),
        "user_id": int(account.user_id),
    })


def evidence_state_hash(account: Account, exact: ExactBalance, observed_at: datetime) -> str:
    return _digest({
        "account_id": int(account.id),
        "amount": exact.canonical,
        "currency_code": "USD",
        "observed_at": utc(observed_at).isoformat(timespec="microseconds"),
        "source_kind": SOURCE_KIND,
        "user_id": int(account.user_id),
    })


def observation_intent_hash(accounts: list[Account], *, observed_at: datetime) -> str:
    observed = utc(observed_at)
    ordered = sorted(accounts, key=lambda account: int(account.id))
    return _digest({
        "observed_at": observed.isoformat(timespec="microseconds"),
        "source_kind": SOURCE_KIND,
        "accounts": [
            {"account_id": int(account.id), "precondition_hash": balance_precondition_hash(account)}
            for account in ordered
        ],
    })


def idempotency_hash(intent_hash: str, account_id: int) -> str:
    return hashlib.sha256(f"{intent_hash}:account:{int(account_id)}".encode("ascii")).hexdigest()


def _events(db: Session, account: Account) -> list[AccountBalanceEvidence]:
    return list(db.scalars(select(AccountBalanceEvidence).where(
        AccountBalanceEvidence.account_id == account.id,
        AccountBalanceEvidence.user_id == account.user_id,
    ).order_by(AccountBalanceEvidence.recorded_at.asc(), AccountBalanceEvidence.id.asc())))


def account_balance_evidence_state(db: Session, account: Account, *, now: datetime) -> BalanceEvidenceState:
    if not account.is_active:
        return BalanceEvidenceState("excluded", "balance_evidence_inactive")
    try:
        current = exact_balance(account.current_balance)
        current_precondition = balance_precondition_hash(account, current)
    except BalanceEvidenceError as exc:
        return BalanceEvidenceState("blocked", str(exc))
    events = _events(db, account)
    assertions: dict[str, AccountBalanceEvidence] = {}
    revoked: set[str] = set()
    for event in events:
        if event.source_kind != SOURCE_KIND or event.actor_category != ACTOR_CATEGORY or event.currency_code != "USD":
            return BalanceEvidenceState("blocked", "balance_evidence_conflict")
        if event.event_type == "assertion":
            if event.amount is None or event.supersedes_event_id is not None:
                return BalanceEvidenceState("blocked", "balance_evidence_conflict")
            assertions[event.id] = event
        elif event.event_type not in {"revocation"}:
            return BalanceEvidenceState("blocked", "balance_evidence_conflict")
    # SQLite timestamp precision can order a same-second revocation before its
    # target assertion. Validate targets after collecting all assertions rather
    # than trusting recorded_at ordering for referential authority.
    for event in events:
        if event.event_type == "revocation":
            if event.amount is not None or not event.supersedes_event_id or event.supersedes_event_id not in assertions:
                return BalanceEvidenceState("blocked", "balance_evidence_conflict")
            revoked.add(event.supersedes_event_id)
    valid = [event for event_id, event in assertions.items() if event_id not in revoked]
    if not valid:
        return BalanceEvidenceState("blocked", "balance_evidence_revoked" if revoked else "balance_evidence_unknown")
    event = max(valid, key=lambda item: (utc(item.observed_at), utc(item.recorded_at), item.id))
    try:
        observed = utc(event.observed_at)
        evidence_amount = exact_balance(event.amount)
    except BalanceEvidenceError:
        return BalanceEvidenceState("blocked", "balance_evidence_invalid")
    if event.precondition_hash != current_precondition:
        return BalanceEvidenceState("blocked", "balance_evidence_changed", observed, event.id)
    if event.state_hash != evidence_state_hash(account, evidence_amount, observed):
        return BalanceEvidenceState("blocked", "balance_evidence_conflict", observed, event.id)
    current_time = utc(now)
    if observed > current_time:
        return BalanceEvidenceState("blocked", "balance_evidence_future", observed, event.id, evidence_amount.value)
    if evidence_amount.value != current.value:
        return BalanceEvidenceState("blocked", "balance_evidence_changed", observed, event.id, evidence_amount.value)
    age = current_time - observed
    if age > timedelta(days=MAX_AGE_DAYS):
        return BalanceEvidenceState("blocked", "balance_evidence_stale", observed, event.id, evidence_amount.value)
    reason = "balance_evidence_nearing_expiry" if age > timedelta(days=6) else "balance_evidence_current"
    return BalanceEvidenceState("ready", reason, observed, event.id, evidence_amount.value)


def derive_balance_evidence_state(db: Session, *, user_id: int, now: datetime) -> BalanceEvidenceState:
    accounts = list(db.scalars(select(Account).where(
        Account.user_id == user_id, Account.is_active.is_(True)
    ).order_by(Account.id.asc())))
    if not accounts:
        return BalanceEvidenceState("blocked", "balance_evidence_incomplete")
    states = [account_balance_evidence_state(db, account, now=now) for account in accounts]
    blocking_order = (
        "balance_amount_invalid", "balance_amount_precision_unavailable", "balance_evidence_changed",
        "balance_evidence_conflict", "balance_evidence_future", "balance_evidence_stale",
        "balance_evidence_revoked", "balance_evidence_unknown", "balance_evidence_invalid",
        "balance_evidence_incomplete",
    )
    for reason in blocking_order:
        found = next((state for state in states if state.reason_code == reason), None)
        if found:
            return BalanceEvidenceState("blocked", reason, found.observed_at, found.event_id)
    if any(state.reason_code == "balance_evidence_nearing_expiry" for state in states):
        return BalanceEvidenceState("ready", "balance_evidence_nearing_expiry")
    return BalanceEvidenceState("ready", "balance_evidence_current")
