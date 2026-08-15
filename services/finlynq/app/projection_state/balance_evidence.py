"""Exact-cent authoritative balance evidence helpers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountBalanceEvidence

MAX_AGE_DAYS = 7
MAX_NUMERIC_38_2 = Decimal("999999999999999999999999999999999999.99")
MONEY_QUANTUM = Decimal("0.01")
SOURCE_KIND = "operator_confirmed"
ACTOR_CATEGORY = "local_operator"


class BalanceEvidenceError(ValueError):
    """Stable sanitized evidence failure."""


@dataclass(frozen=True)
class ExactBalance:
    """The server-read legacy value and its optional authorized cent result."""

    value: Decimal
    canonical: str
    confirmed_value: Decimal | None = None
    confirmed_canonical: str | None = None


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


def _canonical_source(parsed: Decimal) -> str:
    rendered = format(parsed, "f")
    if rendered in {"", "-0"}:
        return "0"
    return rendered


def exact_balance(value: Any) -> ExactBalance:
    """Read the server value as ``Decimal(str(value))`` without rounding it."""
    if isinstance(value, bool) or value is None:
        raise BalanceEvidenceError("balance_amount_invalid")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BalanceEvidenceError("balance_amount_invalid") from exc
    if not parsed.is_finite() or parsed.copy_abs() > MAX_NUMERIC_38_2:
        raise BalanceEvidenceError("balance_amount_precision_unavailable")
    return ExactBalance(parsed, _canonical_source(parsed))


def confirmed_balance(value: Any | ExactBalance) -> ExactBalance:
    """Apply the explicitly authorized USD-cent ``ROUND_HALF_EVEN`` policy."""
    source = value if isinstance(value, ExactBalance) else exact_balance(value)
    try:
        with localcontext() as context:
            context.prec = 50
            rounded = source.value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError) as exc:
        raise BalanceEvidenceError("balance_amount_precision_unavailable") from exc
    if not rounded.is_finite() or rounded.copy_abs() > MAX_NUMERIC_38_2:
        raise BalanceEvidenceError("balance_amount_precision_unavailable")
    rendered = format(rounded, "f")
    if rendered == "-0.00":
        rendered = "0.00"
        rounded = Decimal("0.00")
    return ExactBalance(
        source.value,
        source.canonical,
        confirmed_value=rounded,
        confirmed_canonical=rendered,
    )


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def balance_precondition_hash(account: Account, exact: ExactBalance | None = None) -> str:
    """Bind evidence to the exact legacy source and its approved cent result."""
    source = exact or exact_balance(account.current_balance)
    confirmed = confirmed_balance(source)
    return _digest({
        "account_id": int(account.id),
        "account_type": account.account_type,
        "legacy_source_amount": source.canonical,
        "confirmed_usd_cent": confirmed.confirmed_canonical,
        "is_active": bool(account.is_active),
        "user_id": int(account.user_id),
    })


def evidence_state_hash(account: Account, exact: ExactBalance, observed_at: datetime) -> str:
    """Hash exact source state, confirmed cents, owner, and observation time."""
    confirmed = confirmed_balance(exact)
    return _digest({
        "account_id": int(account.id),
        "confirmed_usd_cent": confirmed.confirmed_canonical,
        "currency_code": "USD",
        "legacy_source_amount": exact.canonical,
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
        current_source = exact_balance(account.current_balance)
        current_confirmed = confirmed_balance(current_source)
        current_precondition = balance_precondition_hash(account, current_source)
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
        elif event.event_type != "revocation":
            return BalanceEvidenceState("blocked", "balance_evidence_conflict")
    # Validate revocation targets after collecting assertions because SQLite can
    # order same-second rows differently from PostgreSQL.
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
        event_confirmed = confirmed_balance(event.amount)
    except BalanceEvidenceError:
        return BalanceEvidenceState("blocked", "balance_evidence_invalid")
    if event.precondition_hash != current_precondition:
        return BalanceEvidenceState("blocked", "balance_evidence_changed", observed, event.id)
    if event.state_hash != evidence_state_hash(account, current_source, observed):
        return BalanceEvidenceState("blocked", "balance_evidence_conflict", observed, event.id)
    if event_confirmed.confirmed_canonical != current_confirmed.confirmed_canonical:
        return BalanceEvidenceState("blocked", "balance_evidence_changed", observed, event.id, event_confirmed.confirmed_value)
    current_time = utc(now)
    if observed > current_time:
        return BalanceEvidenceState("blocked", "balance_evidence_future", observed, event.id, event_confirmed.confirmed_value)
    age = current_time - observed
    if age > timedelta(days=MAX_AGE_DAYS):
        return BalanceEvidenceState("blocked", "balance_evidence_stale", observed, event.id, event_confirmed.confirmed_value)
    reason = "balance_evidence_nearing_expiry" if age > timedelta(days=6) else "balance_evidence_current"
    return BalanceEvidenceState("ready", reason, observed, event.id, event_confirmed.confirmed_value)


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
