"""Bounded, provider-neutral market-research contracts (Phase 5 Slice 1)."""

from .adapters import FinnhubAdapter, ProviderConfigurationError, SecAdapter
from .contracts import (
    CompanyNewsItem,
    CoverageBasis,
    CoverageOmission,
    CoverageSummary,
    EarningsEvent,
    EarningsResult,
    MarketBriefReasonCode,
    MarketQuoteSnapshot,
    PriceBasis,
    ProviderReadiness,
    NormalizedProviderFailure,
    PortfolioHolding,
    PortfolioUniverse,
    ProviderStatus,
    SecCompanyFact, SecFilingEvent,
    SourceMetadata,
)
from .controls import BoundedCache, EndpointClass, UsageLedger
from .fakes import SyntheticMarketTransport
from .market_calendar import (
    LIVE_QUOTE_MAX_AGE,
    MAX_PRIOR_CLOSE_SESSIONS,
    MarketSession,
    classify_quote,
    is_trading_day,
    us_market_holidays,
)

__all__ = [
    "BoundedCache", "CompanyNewsItem", "CoverageBasis", "CoverageOmission", "CoverageSummary",
    "EarningsEvent", "EarningsResult", "EndpointClass", "FinnhubAdapter",
    "LIVE_QUOTE_MAX_AGE", "MAX_PRIOR_CLOSE_SESSIONS", "MarketBriefReasonCode",
    "MarketQuoteSnapshot", "MarketSession", "NormalizedProviderFailure",
    "PortfolioHolding", "PortfolioUniverse", "PriceBasis", "ProviderReadiness",
    "ProviderConfigurationError", "ProviderStatus", "SecAdapter", "SecCompanyFact",
    "SecFilingEvent", "SourceMetadata", "SyntheticMarketTransport", "UsageLedger",
    "classify_quote", "is_trading_day", "us_market_holidays",
]
