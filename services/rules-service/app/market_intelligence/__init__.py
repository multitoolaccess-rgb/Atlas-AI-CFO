"""Bounded, provider-neutral market-research contracts (Phase 5 Slice 1)."""

from .adapters import FinnhubAdapter, ProviderConfigurationError, SecAdapter
from .contracts import (
    CompanyNewsItem,
    EarningsEvent,
    EarningsResult,
    MarketQuoteSnapshot,
    NormalizedProviderFailure,
    PortfolioHolding,
    PortfolioUniverse,
    ProviderStatus,
    SecCompanyFact, SecFilingEvent,
    SourceMetadata,
)
from .controls import BoundedCache, EndpointClass, UsageLedger
from .fakes import SyntheticMarketTransport

__all__ = [
    "BoundedCache", "CompanyNewsItem", "EarningsEvent", "EarningsResult",
    "EndpointClass", "FinnhubAdapter", "MarketQuoteSnapshot",
    "NormalizedProviderFailure", "PortfolioHolding", "PortfolioUniverse",
    "ProviderConfigurationError", "ProviderStatus", "SecAdapter",
    "SecCompanyFact", "SecFilingEvent", "SourceMetadata", "SyntheticMarketTransport", "UsageLedger",
]
