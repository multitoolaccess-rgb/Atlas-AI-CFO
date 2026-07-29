"""Source-backed account-currency validation and conflict handling."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.models.account import Account


APPROVED_CURRENCY_SOURCES = frozenset(
    {"provider_reported", "statement_declared", "user_confirmed"}
)
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._:-]{0,127}$")


class CurrencyEvidenceError(ValueError):
    """Stable, non-sensitive invalid-evidence signal."""


class CurrencyEvidenceConflict(CurrencyEvidenceError):
    """A different evidence record may not silently replace established truth."""


def validate_currency_evidence(
    *, code: str, source: str, observed_at: datetime, source_reference: str
) -> None:
    if not isinstance(code, str) or not _CURRENCY.fullmatch(code):
        raise CurrencyEvidenceError("invalid_currency_code")
    if source not in APPROVED_CURRENCY_SOURCES:
        raise CurrencyEvidenceError("invalid_currency_source")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        raise CurrencyEvidenceError("invalid_currency_observed_at")
    if not isinstance(source_reference, str) or not _REFERENCE.fullmatch(source_reference):
        raise CurrencyEvidenceError("invalid_currency_source_reference")


def validate_stable_reference(source_reference: str) -> None:
    """Validate a bounded non-PII stable reference used in provider metadata."""
    if not isinstance(source_reference, str) or not _REFERENCE.fullmatch(source_reference):
        raise CurrencyEvidenceError("invalid_currency_source_reference")


def set_currency_evidence(
    account: Account,
    *,
    code: str,
    source: str,
    observed_at: datetime,
    source_reference: str,
) -> bool:
    """Set first authoritative evidence, refusing unreviewed replacement.

    Returns ``True`` only when a previously unknown account was populated.
    Existing identical evidence is a no-op; any changed evidence requires a
    separate reconciliation workflow and never overwrites in this slice.
    """
    validate_currency_evidence(
        code=code,
        source=source,
        observed_at=observed_at,
        source_reference=source_reference,
    )
    current = (
        account.currency_code,
        account.currency_source,
        account.currency_observed_at,
        account.currency_source_reference,
    )
    incoming = (code, source, observed_at, source_reference)
    if any(value is not None for value in current):
        # A matching code is not conflicting new currency evidence. Preserve
        # the original provenance rather than silently overwriting it.
        if account.currency_code == code:
            return False
        raise CurrencyEvidenceConflict("currency_evidence_conflict")
    account.currency_code = code
    account.currency_source = source
    account.currency_observed_at = observed_at.astimezone(timezone.utc)
    account.currency_source_reference = source_reference
    return True
