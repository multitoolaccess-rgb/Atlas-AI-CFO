"""Authoritative account-currency evidence and projection gating.

The ``accounts.currency_*`` columns are retained as a compatibility cache for
older import surfaces.  They are never treated as authority here.  Authority
comes only from immutable ``account_currency_evidence`` events created by this
module or a trusted structured-ingestion caller.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Account, AccountCurrencyEvidence

APPROVED_CURRENCY_SOURCES = frozenset(
    {"structured_provider", "structured_statement", "operator_confirmed"}
)
APPROVED_EVENT_TYPES = frozenset({"assertion", "correction", "revocation"})
MAX_FRESHNESS_DAYS = 7
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._:-]{0,127}$")
_IDEMPOTENCY = re.compile(r"^[a-z][a-zA-Z0-9._:-]{0,127}$")
_EVENT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_REASON = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_LEGACY_SOURCE = {
    "structured_provider": "provider_reported",
    "structured_statement": "statement_declared",
    "operator_confirmed": "user_confirmed",
}


class CurrencyEvidenceError(ValueError):
    """Stable, non-sensitive invalid-evidence signal."""


class CurrencyEvidenceConflict(CurrencyEvidenceError):
    """A divergent or non-linear evidence event cannot be appended."""


@dataclass(frozen=True)
class EffectiveCurrency:
    state: str
    reason_code: str
    currency_code: str | None = None
    evidence_event_id: str | None = None
    observed_at: datetime | None = None


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CurrencyEvidenceError("invalid_currency_observed_at")
    return value.astimezone(timezone.utc)


def _stored_utc(value: datetime) -> datetime:
    """Interpret SQLite's timezone-naive round-trip as the stored UTC value."""
    if not isinstance(value, datetime):
        raise CurrencyEvidenceError("currency_evidence_incomplete")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_currency_evidence(*, code: str | None, source: str, observed_at: datetime, source_reference: str) -> None:
    """Validate caller input without inspecting or logging sensitive payloads."""
    if code is not None and (not isinstance(code, str) or not _CURRENCY.fullmatch(code)):
        raise CurrencyEvidenceError("invalid_currency_code")
    if source not in APPROVED_CURRENCY_SOURCES:
        raise CurrencyEvidenceError("invalid_currency_source")
    _utc(observed_at)
    if not isinstance(source_reference, str) or not _REFERENCE.fullmatch(source_reference):
        raise CurrencyEvidenceError("invalid_currency_source_reference")


def validate_stable_reference(source_reference: str) -> None:
    if not isinstance(source_reference, str) or not _REFERENCE.fullmatch(source_reference):
        raise CurrencyEvidenceError("invalid_currency_source_reference")


def _validate_event(
    *, event_type: str, source_kind: str, code: str | None, observed_at: datetime,
    source_reference: str, actor_category: str, reason_code: str | None,
    supersedes_event_id: str | None,
) -> None:
    if event_type not in APPROVED_EVENT_TYPES:
        raise CurrencyEvidenceError("invalid_currency_event_type")
    if event_type == "assertion":
        if source_kind not in APPROVED_CURRENCY_SOURCES:
            raise CurrencyEvidenceError("invalid_currency_source")
        if code is None:
            raise CurrencyEvidenceError("invalid_currency_evidence")
    elif event_type == "correction":
        if source_kind != "correction" or code is None or not supersedes_event_id:
            raise CurrencyEvidenceError("invalid_currency_correction")
    elif event_type == "revocation":
        if source_kind != "revocation" or code is not None or not supersedes_event_id:
            raise CurrencyEvidenceError("invalid_currency_revocation")
    if code is not None and not _CURRENCY.fullmatch(code):
        raise CurrencyEvidenceError("invalid_currency_code")
    _utc(observed_at)
    if not isinstance(source_reference, str) or not _REFERENCE.fullmatch(source_reference):
        raise CurrencyEvidenceError("invalid_currency_source_reference")
    if not isinstance(actor_category, str) or not _REASON.fullmatch(actor_category):
        raise CurrencyEvidenceError("invalid_currency_actor")
    if reason_code is not None and not _REASON.fullmatch(reason_code):
        raise CurrencyEvidenceError("invalid_currency_reason")
    if supersedes_event_id is not None and not _EVENT_ID.fullmatch(supersedes_event_id):
        raise CurrencyEvidenceError("invalid_currency_supersedes")


def _ordered_events(db: Session, account_id: int, user_id: int) -> list[AccountCurrencyEvidence]:
    return list(
        db.query(AccountCurrencyEvidence)
        .filter(
            AccountCurrencyEvidence.account_id == account_id,
            AccountCurrencyEvidence.user_id == user_id,
        )
        .order_by(AccountCurrencyEvidence.recorded_at.asc(), AccountCurrencyEvidence.id.asc())
        .all()
    )


def effective_currency_for_account(
    db: Session, *, account_id: int, user_id: int, now: datetime | None = None,
) -> EffectiveCurrency:
    """Derive one account's effective currency from its immutable event stream."""
    current_time = _utc(now or datetime.now(timezone.utc))
    events = _ordered_events(db, account_id, user_id)
    if not events:
        return EffectiveCurrency("blocked", "currency_unknown")

    active: AccountCurrencyEvidence | None = None
    revoked = False
    for event in events:
        if event.event_type == "assertion":
            if active is not None and active.currency_code != event.currency_code:
                return EffectiveCurrency("blocked", "currency_conflict")
            active = event
            revoked = False
        elif event.event_type == "correction":
            if active is None or event.supersedes_event_id != active.id:
                return EffectiveCurrency("blocked", "currency_conflict")
            active = event
            revoked = False
        elif event.event_type == "revocation":
            if active is None or event.supersedes_event_id != active.id:
                return EffectiveCurrency("blocked", "currency_conflict")
            active = None
            revoked = True
        else:
            return EffectiveCurrency("blocked", "currency_evidence_incomplete")

    if active is None:
        return EffectiveCurrency("blocked", "currency_revoked" if revoked else "currency_unknown")
    if active.currency_code is None:
        return EffectiveCurrency("blocked", "currency_evidence_incomplete")
    try:
        observed_at = _stored_utc(active.observed_at)
    except CurrencyEvidenceError:
        return EffectiveCurrency("blocked", "currency_evidence_incomplete")
    if observed_at > current_time or current_time - observed_at > timedelta(days=MAX_FRESHNESS_DAYS):
        return EffectiveCurrency("blocked", "currency_stale", active.currency_code, active.id, observed_at)
    if active.currency_code != "USD":
        return EffectiveCurrency("blocked", "currency_unsupported", active.currency_code, active.id, observed_at)
    return EffectiveCurrency("ready", "currency_authority_ready", "USD", active.id, observed_at)


def derive_effective_currency(
    db: Session, *, user_id: int, now: datetime | None = None,
) -> EffectiveCurrency:
    """Derive the aggregate state for every active account without skipping rows."""
    accounts = list(
        db.query(Account)
        .filter(Account.user_id == user_id, Account.is_active.is_(True))
        .order_by(Account.id.asc())
        .all()
    )
    if not accounts:
        return EffectiveCurrency("blocked", "currency_evidence_incomplete")
    states = [effective_currency_for_account(db, account_id=a.id, user_id=user_id, now=now) for a in accounts]
    codes = {state.currency_code for state in states if state.currency_code is not None}
    if len(codes) > 1:
        return EffectiveCurrency("blocked", "currency_mixed")
    for reason in (
        "currency_conflict", "currency_revoked", "currency_stale", "currency_unsupported",
        "currency_unknown", "currency_evidence_incomplete",
    ):
        match = next((state for state in states if state.reason_code == reason), None)
        if match is not None:
            return match
    return EffectiveCurrency("ready", "currency_authority_ready", "USD")


def _event_fingerprint(event: AccountCurrencyEvidence) -> tuple[Any, ...]:
    # Idempotency identifies one mutation intent. The caller may retry after
    # transport delay with a newly computed observation timestamp; replay must
    # return the original immutable event rather than create a duplicate or
    # mutate its timestamp. Semantic payload fields still must match.
    return (
        event.event_type, event.source_kind, event.currency_code,
        event.actor_category, event.source_reference_hash, event.supersedes_event_id,
        event.reason_code,
    )


def _cache_account_currency(account: Account, event: AccountCurrencyEvidence) -> None:
    """Maintain legacy columns as a non-authoritative compatibility projection."""
    if event.event_type == "revocation":
        account.currency_code = None
        account.currency_source = None
        account.currency_observed_at = None
        account.currency_source_reference = None
        return
    account.currency_code = event.currency_code
    account.currency_source = _LEGACY_SOURCE.get(event.source_kind, account.currency_source or "user_confirmed")
    account.currency_observed_at = _utc(event.observed_at)
    # This field predates the hash-only event contract. Keep only an opaque,
    # bounded event identifier in the compatibility projection.
    account.currency_source_reference = f"evidence:{event.id}"


def record_currency_evidence(
    db: Session,
    *,
    account: Account,
    event_type: str,
    source_kind: str,
    code: str | None,
    observed_at: datetime,
    source_reference: str,
    actor_category: str,
    idempotency_key: str,
    supersedes_event_id: str | None = None,
    reason_code: str | None = None,
    apply: bool = True,
) -> dict[str, Any]:
    """Validate and append one evidence event, or return a dry-run preview."""
    if not account.id or not account.user_id:
        raise CurrencyEvidenceError("account_scope_unavailable")
    _validate_event(
        event_type=event_type, source_kind=source_kind, code=code,
        observed_at=observed_at, source_reference=source_reference,
        actor_category=actor_category, reason_code=reason_code,
        supersedes_event_id=supersedes_event_id,
    )
    if not isinstance(idempotency_key, str) or not _IDEMPOTENCY.fullmatch(idempotency_key):
        raise CurrencyEvidenceError("invalid_currency_idempotency_key")
    source_hash = _hash(source_reference)
    key_hash = _hash(idempotency_key)
    existing = (
        db.query(AccountCurrencyEvidence)
        .filter(AccountCurrencyEvidence.account_id == account.id, AccountCurrencyEvidence.idempotency_key_hash == key_hash)
        .first()
    )
    if existing is not None:
        probe = AccountCurrencyEvidence(
            event_type=event_type, source_kind=source_kind, currency_code=code,
            observed_at=_utc(observed_at), actor_category=actor_category,
            source_reference_hash=source_hash, supersedes_event_id=supersedes_event_id,
            reason_code=reason_code,
        )
        if _event_fingerprint(existing) != _event_fingerprint(probe):
            raise CurrencyEvidenceConflict("currency_evidence_conflict")
        return {"status": "idempotent_replay", "event_id": existing.id, "account_id": account.id, "event_type": existing.event_type, "currency_code": existing.currency_code}

    prior = effective_currency_for_account(db, account_id=account.id, user_id=account.user_id, now=observed_at)
    if event_type == "assertion" and prior.currency_code is not None and prior.currency_code != code:
        raise CurrencyEvidenceConflict("currency_evidence_conflict")
    if event_type in {"correction", "revocation"} and (prior.evidence_event_id is None or prior.evidence_event_id != supersedes_event_id):
        raise CurrencyEvidenceConflict("currency_evidence_conflict")

    recorded_at = datetime.now(timezone.utc)
    latest_recorded = (
        db.query(AccountCurrencyEvidence.recorded_at)
        .filter(AccountCurrencyEvidence.account_id == account.id)
        .order_by(AccountCurrencyEvidence.recorded_at.desc())
        .first()
    )
    if latest_recorded and latest_recorded[0] is not None and _stored_utc(latest_recorded[0]) >= recorded_at:
        recorded_at = _stored_utc(latest_recorded[0]) + timedelta(microseconds=1)
    event = AccountCurrencyEvidence(
        id=str(uuid.uuid4()), user_id=account.user_id, account_id=account.id,
        event_type=event_type, source_kind=source_kind, currency_code=code,
        observed_at=_utc(observed_at), recorded_at=recorded_at,
        actor_category=actor_category, source_reference_hash=source_hash,
        idempotency_key_hash=key_hash, supersedes_event_id=supersedes_event_id,
        reason_code=reason_code,
    )
    if not apply:
        return {"status": "dry_run", "account_id": account.id, "event_type": event_type, "currency_code": code}
    db.add(event)
    try:
        db.flush()
    except Exception as exc:
        db.rollback()
        raise CurrencyEvidenceConflict("currency_evidence_conflict") from exc
    _cache_account_currency(account, event)
    db.add(account)
    return {"status": "recorded", "event_id": event.id, "account_id": account.id, "event_type": event_type, "currency_code": code}
