"""Provider-neutral INV-01 contracts.

These contracts describe validated context and evidence only. They are not a
second financial ledger and deliberately contain no broker/order capability.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InvestmentStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataState(StrEnum):
    UNKNOWN = "unknown"
    MISSING = "missing"
    STALE = "stale"
    ESTIMATED = "estimated"
    OBSERVED = "observed"


class InvestmentCurrency(StrEnum):
    USD = "USD"


class EvidenceKind(StrEnum):
    SOURCE = "source"
    CALCULATION = "calculation"


class EvidenceReference(InvestmentStrictModel):
    """Immutable pointer to a source or deterministic calculation."""

    schema_version: Literal["InvestmentEvidenceReference/v1"] = "InvestmentEvidenceReference/v1"
    evidence_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    kind: EvidenceKind
    source: str = Field(min_length=1, max_length=160)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime
    retrieved_at: datetime
    state: DataState = DataState.OBSERVED

    @field_validator("as_of", "retrieved_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != datetime.now(UTC).utcoffset():
            raise ValueError("timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)


class SecurityIdentity(InvestmentStrictModel):
    """Provider-neutral security identity; ticker is an alias, not authority."""

    schema_version: Literal["InvestmentSecurityIdentity/v1"] = "InvestmentSecurityIdentity/v1"
    security_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    instrument_type: Literal["equity", "etf", "index", "fund", "unknown"]
    symbol: str | None = Field(default=None, max_length=16)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    state: Literal["resolved", "unresolved", "unsupported"] = "resolved"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9.\-]{1,16}", normalized):
            raise ValueError("symbol contains unsupported characters")
        return normalized

    @model_validator(mode="after")
    def validate_resolution(self) -> "SecurityIdentity":
        if self.state == "resolved" and not self.symbol:
            raise ValueError("resolved security requires an alias")
        if self.state == "unsupported" and self.instrument_type != "unknown":
            raise ValueError("unsupported security must use unknown instrument type")
        return self


class InvestmentValue(InvestmentStrictModel):
    """Exact finite Decimal represented as canonical text at the boundary."""

    amount: str = Field(max_length=48)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    state: DataState

    @field_validator("amount")
    @classmethod
    def finite_decimal(cls, value: str) -> str:
        decimal = Decimal(value)
        if not decimal.is_finite():
            raise ValueError("amount must be finite")
        return format(decimal.normalize(), "f")


class InvestmentPosition(InvestmentStrictModel):
    security: SecurityIdentity
    quantity: InvestmentValue | None = None
    market_value: InvestmentValue | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=8)


class InvestmentContext(InvestmentStrictModel):
    """Frozen owner/account-scoped input to future analysis runs."""

    schema_version: Literal["InvestmentContext/v1"] = "InvestmentContext/v1"
    owner_id: int = Field(gt=0)
    account_ids: tuple[int, ...] = Field(min_length=1, max_length=50)
    as_of: datetime
    positions: tuple[InvestmentPosition, ...] = Field(default=(), max_length=500)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=500)
    data_completeness: DataState = DataState.OBSERVED

    @field_validator("as_of")
    @classmethod
    def context_as_of_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware UTC")
        return value.astimezone(UTC)

    @field_validator("account_ids")
    @classmethod
    def unique_accounts(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value):
            raise ValueError("account_ids must be unique")
        return tuple(sorted(value))

    def canonical_payload(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude={"owner_id"}),
            sort_keys=True,
            separators=(",", ":"),
        )

    def context_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()


class ReadOnlyInvestmentRequest(InvestmentStrictModel):
    """Assistant request contract: identifiers and scope only, never facts."""

    schema_version: Literal["ReadOnlyInvestmentRequest/v1"] = "ReadOnlyInvestmentRequest/v1"
    owner_id: int = Field(gt=0)
    account_ids: tuple[int, ...] = Field(min_length=1, max_length=50)
    question: str = Field(min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def sanitize_question(cls, value: str) -> str:
        return " ".join(value.split())


_CREDENTIAL_QUERY_NAMES = {"token", "key", "secret", "password", "authorization", "apikey"}


def credential_free_source(value: str) -> str:
    parsed = urlsplit(value)
    names = {re.sub(r"[^a-z0-9]", "", key.lower()) for key, _ in parse_qsl(parsed.query)}
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("source must be a credential-free HTTP(S) URL")
    if any(name in _CREDENTIAL_QUERY_NAMES or any(part in name for part in _CREDENTIAL_QUERY_NAMES) for name in names):
        raise ValueError("source must not contain credentials")
    return value
