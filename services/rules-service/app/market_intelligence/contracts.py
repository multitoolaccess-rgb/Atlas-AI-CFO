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


class PriceBasis(StrEnum):
    """The bounded price basis used by a generated brief."""
    LIVE = "live"
    PRIOR_CLOSE = "prior_close"
    UNUSABLE = "unusable"
    UNKNOWN = "unknown"


class CoverageBasis(StrEnum):
    VALUE_WEIGHTED = "value_weighted"
    POSITION_COUNT = "position_count"


class MarketBriefReasonCode(StrEnum):
    PROVIDER_CONFIGURATION_MISSING = "provider_configuration_missing"
    PROVIDER_TRANSPORT_FAILURE = "provider_transport_failure"
    PROVIDER_AUTHENTICATION_FAILED = "provider_authentication_failed"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    LIVE_QUOTE_STALE = "live_quote_stale"
    PRIOR_CLOSE_ACCEPTED = "prior_close_accepted"
    PRIOR_CLOSE_TOO_OLD = "prior_close_too_old"
    INVALID_QUOTE = "invalid_quote"
    AMBIGUOUS_CURRENCY = "ambiguous_currency"
    INSUFFICIENT_PORTFOLIO_COVERAGE = "insufficient_portfolio_coverage"
    NO_MARKET_ADDRESSABLE_HOLDINGS = "no_market_addressable_holdings"
    MARKET_BRIEF_GENERATION_UNAVAILABLE = "market_brief_generation_unavailable"


class FailureClass(StrEnum):
    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"
    PAID_ENDPOINT = "paid_endpoint"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UPSTREAM = "upstream"
    AUTHENTICATION_FAILED = "authentication_failed"
    INVALID_PAYLOAD = "invalid_payload"
    INVALID_QUOTE = "invalid_quote"
    STALE = "stale"
    NOT_FOUND = "not_found"


class EvidenceCategory(StrEnum):
    """The bounded evidence category a holding omission or availability refers to."""
    QUOTE = "quote"
    NEWS = "news"
    EARNINGS = "earnings"
    FILINGS = "filings"
    ANALYST = "analyst"


class CoverageOmission(StrictModel):
    symbol: str = Field(min_length=1, max_length=10)
    evidence_category: EvidenceCategory = EvidenceCategory.QUOTE
    reason_code: MarketBriefReasonCode
    # User-safe recovery guidance; never raw provider text. Optional so
    # existing persisted v1 briefs remain readable (backward compatible).
    recovery: str | None = Field(default=None, max_length=200)


class EvidenceAvailability(StrictModel):
    """Per-holding, per-evidence-category availability for the v2 brief.

    Records WHICH evidence category failed for WHICH holding with a stable
    reason code and safe recovery guidance, so a single unavailable category
    never kills the complete brief and the UI can explain it precisely.
    """
    symbol: str = Field(min_length=1, max_length=10)
    evidence_category: EvidenceCategory
    reason_code: MarketBriefReasonCode
    recovery: str | None = Field(default=None, max_length=200)


class AnalystRecommendation(StrictModel):
    """A bounded sell-side recommendation snapshot (period-scoped rows)."""
    schema_version: Literal["AnalystRecommendation/v1"] = "AnalystRecommendation/v1"
    symbol: str
    period: str = Field(min_length=4, max_length=10)
    strong_buy: int = Field(ge=0, le=10000)
    buy: int = Field(ge=0, le=10000)
    hold: int = Field(ge=0, le=10000)
    sell: int = Field(ge=0, le=10000)
    strong_sell: int = Field(ge=0, le=10000)
    source: SourceMetadata

    @field_validator("symbol")
    @classmethod
    def recommendation_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""


class PriceTarget(StrictModel):
    """A bounded analyst price-target snapshot with no guidance claim."""
    schema_version: Literal["PriceTarget/v1"] = "PriceTarget/v1"
    symbol: str
    target_high: str | None = Field(default=None, max_length=48)
    target_low: str | None = Field(default=None, max_length=48)
    target_mean: str | None = Field(default=None, max_length=48)
    target_median: str | None = Field(default=None, max_length=48)
    source: SourceMetadata

    @field_validator("symbol")
    @classmethod
    def price_target_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""

    @field_validator("target_high", "target_low", "target_mean", "target_median")
    @classmethod
    def canonical_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        decimal = Decimal(value)
        if not decimal.is_finite() or decimal <= 0:
            raise ValueError("price target must be a positive finite decimal")
        return format(decimal.normalize(), "f")


class DividendEvent(StrictModel):
    """A bounded dividend event (ex-date, declared, record, payable)."""
    schema_version: Literal["DividendEvent/v1"] = "DividendEvent/v1"
    symbol: str
    ex_date: datetime | None = None
    declared_date: datetime | None = None
    record_date: datetime | None = None
    payable_date: datetime | None = None
    amount: str | None = Field(default=None, max_length=48)
    source: SourceMetadata

    @field_validator("symbol")
    @classmethod
    def dividend_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""

    @field_validator("amount")
    @classmethod
    def canonical_dividend_amount(cls, value: str | None) -> str | None:
        if value is None:
            return None
        decimal = Decimal(value)
        if not decimal.is_finite() or decimal < 0:
            raise ValueError("dividend amount must be a non-negative finite decimal")
        return format(decimal.normalize(), "f")


class CompanyProfile(StrictModel):
    """A bounded company-profile record used only for CIK resolution and labeling."""
    schema_version: Literal["CompanyProfile/v1"] = "CompanyProfile/v1"
    symbol: str
    cik: str | None = Field(default=None, max_length=10)
    company_name: str | None = Field(default=None, max_length=200)
    exchange: str | None = Field(default=None, max_length=64)
    sector: str | None = Field(default=None, max_length=80)
    source: SourceMetadata

    @field_validator("symbol")
    @classmethod
    def profile_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""

    @field_validator("company_name", "exchange", "sector")
    @classmethod
    def sanitize_profile_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _untrusted_text(value, 200)

    @field_validator("cik")
    @classmethod
    def normalized_cik(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_cik(value)
        except ValueError:
            return None


class HoldingEvidence(StrictModel):
    """Market Intelligence v2 per-holding intelligence packet.

    All records are bounded and source-cited; every claim carries provenance.
    """
    schema_version: Literal["HoldingEvidence/v1"] = "HoldingEvidence/v1"
    symbol: str
    quote: MarketQuoteSnapshot | None = None
    profile: CompanyProfile | None = None
    news: tuple[CompanyNewsItem, ...] = ()
    earnings_events: tuple[EarningsEvent, ...] = ()
    earnings_results: tuple[EarningsResult, ...] = ()
    filings: tuple[SecFilingEvent, ...] = ()
    recommendations: tuple[AnalystRecommendation, ...] = ()
    price_target: PriceTarget | None = None
    dividends: tuple[DividendEvent, ...] = ()
    materiality: Literal["high", "watch", "informational"] = "informational"
    materiality_reason: str | None = Field(default=None, max_length=200)

    @field_validator("symbol")
    @classmethod
    def evidence_symbol(cls, value: str) -> str:
        return PortfolioHolding(symbol=value, instrument_type="equity").symbol or ""


class CoverageSummary(StrictModel):
    eligible_holding_count: int = Field(ge=0, le=500)
    covered_holding_count: int = Field(ge=0, le=500)
    omitted_holding_count: int = Field(ge=0, le=500)
    coverage_basis: CoverageBasis
    coverage_percentage: str | None = Field(default=None, max_length=48)
    minimum_required_percentage: str = Field(default="0.8", max_length=48)
    omitted_symbols: tuple[str, ...] = ()
    omissions: tuple[CoverageOmission, ...] = ()


class ProviderReadiness(StrictModel):
    provider: str = Field(min_length=1, max_length=32)
    status: Literal["ready", "degraded", "unavailable"]
    reason_code: MarketBriefReasonCode | None = None


class SourceMetadata(StrictModel):
    schema_version: Literal["SourceMetadata/v1"] = "SourceMetadata/v1"
    provider: str = Field(min_length=1, max_length=32)
    source_url: str = Field(min_length=1, max_length=512)
    retrieved_at: datetime
    published_at: datetime | None = None
    observed_at: datetime | None = None
    freshness: Freshness = Freshness.FRESH
    price_basis: PriceBasis = PriceBasis.UNKNOWN

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
