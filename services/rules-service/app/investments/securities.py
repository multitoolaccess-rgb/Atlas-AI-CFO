"""INV-02 provider-neutral security identity primitives."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .contracts import InvestmentStrictModel


class SecurityState(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    INACTIVE = "inactive"


class InstrumentType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    INDEX = "index"
    ADR = "adr"
    CASH = "cash"
    UNKNOWN = "unknown"


class SecurityIdentifier(InvestmentStrictModel):
    """An effective-dated provider or exchange identifier, never authority."""

    schema_version: Literal["SecurityIdentifier/v1"] = "SecurityIdentifier/v1"
    namespace: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_.:-]+$")
    value: str = Field(min_length=1, max_length=128)
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def valid_interval(self) -> "SecurityIdentifier":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("identifier valid_to must not precede valid_from")
        return self


class SecurityIdentity(InvestmentStrictModel):
    """Stable identity with ticker, exchange, and provider IDs as aliases."""

    schema_version: Literal["SecurityIdentity/v1"] = "SecurityIdentity/v1"
    security_id: str = Field(min_length=1, max_length=128, pattern=r"^sec:[A-Za-z0-9._:-]+$")
    state: SecurityState
    instrument_type: InstrumentType
    symbol: str | None = Field(default=None, max_length=32)
    exchange: str | None = Field(default=None, max_length=32)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    issuer_id: str | None = Field(default=None, max_length=128)
    identifiers: tuple[SecurityIdentifier, ...] = Field(default=(), max_length=32)
    as_of: datetime

    @field_validator("symbol", "exchange")
    @classmethod
    def normalize_alias(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("as_of", "identifiers")
    @classmethod
    def utc_or_identifiers(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("as_of must be timezone-aware UTC")
            return value.astimezone(UTC)
        return value

    @model_validator(mode="after")
    def validate_identity_state(self) -> "SecurityIdentity":
        if self.state == SecurityState.RESOLVED and not self.symbol:
            raise ValueError("resolved identity requires a symbol alias")
        if self.state in {SecurityState.UNRESOLVED, SecurityState.AMBIGUOUS, SecurityState.UNSUPPORTED} and not self.symbol:
            return self
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def identity_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode()).hexdigest()


def security_id_for(*, namespace: str, value: str) -> str:
    """Derive a stable internal ID from an explicit namespace/value pair."""
    normalized = f"{namespace.strip().lower()}:{value.strip().upper()}"
    return f"sec:{hashlib.sha256(normalized.encode()).hexdigest()[:32]}"
