"""Strict normalized records; no raw provider payloads cross this boundary."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Generic, Literal, TypeVar
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

_SYMBOL = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_CIK = re.compile(r"^\d{1,10}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_CREDENTIAL_QUERY_NAMES = {
    "token", "apikey", "key", "secret", "password", "passwd", "credential",
    "authorization", "auth", "signature", "sig", "accesstoken", "clientsecret",
}


def _is_credential_query_name(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return (
        normalized in _CREDENTIAL_QUERY_NAMES
        or any(marker in normalized for marker in (
            "token", "secret", "password", "credential", "authorization",
            "apikey", "accesskey", "signature",
        ))
    )


def normalize_cik(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("CIK must contain up to ten digits")
    raw = value.strip()
    if not _CIK.fullmatch(raw):
        raise ValueError("CIK must contain up to ten digits")
    return raw.lstrip("0") or "0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class FailureClass(StrEnum):
    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"
    PAID_ENDPOINT = "paid_endpoint"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UPSTREAM = "upstream"
    INVALID_PAYLOAD = "invalid_payload"
    STALE = "stale"
    NOT_FOUND = "not_found"


class SourceMetadata(StrictModel):
    schema_version: Literal["SourceMetadata/v1"] = "SourceMetadata/v1"
    provider: str = Field(min_length=1, max_length=32)
    source_url: str = Field(min_length=1, max_length=512)
    retrieved_at: datetime
    published_at: datetime | None = None
    observed_at: datetime | None = None
    freshness: Freshness = Freshness.FRESH

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(_is_credential_query_name(name) for name, _ in parse_qsl(parsed.query, keep_blank_values=True))
        ):
            raise ValueError("source URL must be a credential-free HTTP(S) URL")
        return value


class NormalizedProviderFailure(StrictModel):
    schema_version: Literal["NormalizedProviderFailure/v1"] = "NormalizedProviderFailure/v1"
    provider: str = Field(min_length=1, max_length=32)
    endpoint_class: str = Field(min_length=1, max_length=48)
    failure_class: FailureClass
    occurred_at: datetime
    retryable: bool = False
    message: str = Field(min_length=1, max_length=160)


class ProviderStatus(StrictModel):
    schema_version: Literal["ProviderStatus/v1"] = "ProviderStatus/v1"
    provider: str = Field(min_length=1, max_length=32)
    enabled: bool
    healthy: bool
    checked_at: datetime
    failure: NormalizedProviderFailure | None = None


class PortfolioHolding(StrictModel):
    symbol: str | None = None
    instrument_type: str = Field(min_length=1, max_length=32)
    quantity: str | None = Field(default=None, max_length=48)
    value: str | None = Field(default=None, max_length=48)
    sector: str | None = Field(default=None, max_length=80)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not _SYMBOL.fullmatch(normalized):
            raise ValueError("symbol must be a supported market symbol")
        return normalized


class PortfolioUniverse(StrictModel):
    schema_version: Literal["PortfolioUniverse/v1"] = "PortfolioUniverse/v1"
    holdings: tuple[PortfolioHolding, ...]
    universe_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def from_holdings(cls, holdings: list[PortfolioHolding]) -> "PortfolioUniverse":
        # Cash and unknown symbols cannot generate external requests.  First
        # occurrence wins so this function cannot invent/aggregate holdings.
        deduplicated: dict[str, PortfolioHolding] = {}
        for holding in holdings:
            if holding.symbol and holding.instrument_type.lower() != "cash":
                deduplicated.setdefault(holding.symbol, holding)
        ordered = tuple(deduplicated[symbol] for symbol in sorted(deduplicated))
        canonical = json.dumps([h.model_dump(mode="json") for h in ordered], sort_keys=True, separators=(",", ":"))
        return cls(holdings=ordered, universe_hash=hashlib.sha256(canonical.encode()).hexdigest())


class MarketQuoteSnapshot(StrictModel):
    schema_version: Literal["MarketQuoteSnapshot/v1"] = "MarketQuoteSnapshot/v1"
    symbol: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    current_price: str = Field(max_length=48)
    previous_close: str | None = Field(default=None, max_length=48)
    source: SourceMetadata

    @field_validator("symbol")
    @classmethod
    def quote_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""

    @field_validator("current_price", "previous_close")
    @classmethod
    def canonical_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        decimal = Decimal(value)
        if not decimal.is_finite() or decimal <= 0:
            raise ValueError("price must be a positive finite decimal")
        return format(decimal.normalize(), "f")


def _untrusted_text(value: str, limit: int) -> str:
    cleaned = _CONTROL.sub(" ", value).strip()
    return cleaned[:limit]


class CompanyNewsItem(StrictModel):
    schema_version: Literal["CompanyNewsItem/v1"] = "CompanyNewsItem/v1"
    symbol: str
    headline: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=1000)
    publisher: str | None = Field(default=None, max_length=120)
    source: SourceMetadata

    @field_validator("headline", "summary", "publisher")
    @classmethod
    def sanitize_external_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        sanitized = _untrusted_text(value, 1000)
        if info.field_name == "headline" and not sanitized:
            raise ValueError("headline must contain visible text")
        return sanitized

    @field_validator("symbol")
    @classmethod
    def news_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""


class EarningsEvent(StrictModel):
    schema_version: Literal["EarningsEvent/v1"] = "EarningsEvent/v1"
    symbol: str
    event_date: datetime
    source: SourceMetadata

    @field_validator("symbol")
    @classmethod
    def event_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""


class EarningsResult(StrictModel):
    schema_version: Literal["EarningsResult/v1"] = "EarningsResult/v1"
    symbol: str
    actual: str | None = Field(default=None, max_length=48)
    estimate: str | None = Field(default=None, max_length=48)
    source: SourceMetadata

    @field_validator("symbol")
    @classmethod
    def result_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""


class SecFilingEvent(StrictModel):
    schema_version: Literal["SecFilingEvent/v1"] = "SecFilingEvent/v1"
    cik: str
    form: str = Field(pattern=r"^(8-K|10-Q|10-K|20-F|40-F|6-K)$")
    accession_number: str = Field(min_length=1, max_length=40)
    filing_date: datetime
    source: SourceMetadata

    @field_validator("cik")
    @classmethod
    def normalized_cik(cls, value: str) -> str:
        return normalize_cik(value)


class SecCompanyFact(StrictModel):
    """A deliberately small XBRL fact, never the unbounded SEC response."""
    schema_version: Literal["SecCompanyFact/v1"] = "SecCompanyFact/v1"
    cik: str
    taxonomy: str = Field(pattern=r"^(us-gaap|dei)$")
    tag: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=16)
    value: str = Field(max_length=80)
    filed_at: datetime | None = None
    source: SourceMetadata

    @field_validator("cik")
    @classmethod
    def fact_cik(cls, value: str) -> str:
        return normalize_cik(value)


T = TypeVar("T")


class ProviderResult(StrictModel, Generic[T]):
    value: T | None = None
    failure: NormalizedProviderFailure | None = None
    cache_hit: bool = False

    @model_validator(mode="after")
    def exactly_one_outcome(self) -> "ProviderResult[T]":
        if (self.value is None) == (self.failure is None):
            raise ValueError("provider result must contain exactly one outcome")
        return self
