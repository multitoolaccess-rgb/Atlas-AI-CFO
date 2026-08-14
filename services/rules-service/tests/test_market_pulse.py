"""Hermetic Market Intelligence v2 market-pulse tests.

No network and no paid endpoints: synthetic providers only.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.market_intelligence.contracts import (
    EarningsEvent,
    Freshness,
    MarketQuoteSnapshot,
    PriceBasis,
    SourceMetadata,
)
from app.market_intelligence.pulse import (
    INDEX_PROXIES,
    MarketPulseComposer,
    OperationalMarketPulse,
    SP500_SYMBOLS_PATH,
    build_operational_market_pulse,
    load_sp500_symbols,
)

NOW = datetime(2026, 8, 12, 15, 0, tzinfo=UTC)


def _quote(symbol: str, price: str = "110") -> MarketQuoteSnapshot:
    return MarketQuoteSnapshot(
        symbol=symbol,
        currency="USD",
        current_price=price,
        previous_close="100",
        source=SourceMetadata(
            provider="synthetic", source_url=f"https://quotes.test/{symbol.lower()}",
            retrieved_at=NOW, observed_at=NOW, freshness=Freshness.FRESH, price_basis=PriceBasis.LIVE,
        ),
    )


class PulseProviders:
    def __init__(self, *, quote_missing: set[str] | None = None, news: list | None = None) -> None:
        from app.market_intelligence.contracts import MarketNewsItem

        self.quote_missing = quote_missing or set()
        self.news = news if news is not None else [
            MarketNewsItem(
                headline="Market headline",
                source=SourceMetadata(provider="synthetic", source_url="https://news.test/market", retrieved_at=NOW),
            )
        ]

    def quote(self, symbol: str):
        if symbol in self.quote_missing:
            return None
        return _quote(symbol)

    def market_news(self, *, limit: int = 15):
        return self.news[:limit]

    def market_earnings_calendar(self, *, from_date: str, to_date: str):
        return [EarningsEvent(
            symbol="AAPL",
            event_date=datetime(2026, 8, 13, tzinfo=UTC),
            source=SourceMetadata(provider="synthetic", source_url="https://earnings.test/calendar", retrieved_at=NOW),
        )]


def test_pulse_uses_approved_etf_proxies_and_truthful_direction() -> None:
    pulse = MarketPulseComposer(PulseProviders(), now=lambda: NOW, max_scan_symbols=3).assemble()
    assert [index.label for index in pulse.indices] == [label for label, _ in INDEX_PROXIES]
    assert all(index.is_etf_proxy for index in pulse.indices)
    assert pulse.indices[0].direction == "up"
    assert pulse.indices[0].symbol == "SPY"
    assert pulse.scanned_symbol_count == 3
    assert pulse.total_universe_size == len(load_sp500_symbols())
    assert pulse.categories_unavailable == ()
    assert pulse.generated_at == NOW


def test_pulse_marks_unavailable_categories_truthfully() -> None:
    missing = set(load_sp500_symbols()) | {"SPY", "QQQ"}
    pulse = MarketPulseComposer(
        PulseProviders(quote_missing=missing, news=[]),
        now=lambda: NOW,
        max_scan_symbols=5,
    ).assemble()
    assert pulse.scanned_symbol_count == 0
    assert "indices" in pulse.categories_unavailable
    assert "market_news" in pulse.categories_unavailable
    assert "scanner" in pulse.categories_unavailable
    # Earnings calendar still came from the synthetic provider.
    assert len(pulse.earnings_calendar) == 1


def test_pulse_scanner_prioritizes_portfolio_holdings() -> None:
    holdings = ("NFLX", "AAPL")
    pulse = MarketPulseComposer(PulseProviders(), now=lambda: NOW, max_scan_symbols=6).assemble(priority_symbols=holdings)
    scanned = [quote.symbol for quote in pulse.scanner]
    assert scanned[0] == "NFLX"
    assert scanned[1] == "AAPL"
    assert len(scanned) == 6


def test_pulse_scanner_is_bounded_and_deduplicated() -> None:
    holdings = ("AAPL", "AAPL", "MSFT")
    pulse = MarketPulseComposer(PulseProviders(), now=lambda: NOW, max_scan_symbols=4).assemble(priority_symbols=holdings)
    scanned = [quote.symbol for quote in pulse.scanner]
    assert scanned == ["AAPL", "MSFT", pulse.scanner[2].symbol, pulse.scanner[3].symbol]
    assert len(set(scanned)) == len(scanned) == 4


def test_sp500_symbols_bundle_is_bounded_and_upper_case() -> None:
    symbols = load_sp500_symbols()
    assert 400 <= len(symbols) <= 502
    assert all(symbol.isupper() for symbol in symbols)
    assert "AAPL" in symbols and "MSFT" in symbols


def test_operational_pulse_is_not_wired_without_server_owned_controls() -> None:
    assert build_operational_market_pulse(SimpleNamespace(atlas_market_brief_generation_enabled=False, atlas_market_brief_external_provider_enabled=False)) is None
    assert build_operational_market_pulse(SimpleNamespace(atlas_market_brief_generation_enabled=True, atlas_market_brief_external_provider_enabled=True, finnhub_api_key=None)) is None
    assert build_operational_market_pulse(SimpleNamespace(atlas_market_brief_generation_enabled=True, atlas_market_brief_external_provider_enabled=True, finnhub_api_key="local-only")) is not None


def test_operational_pulse_uses_only_finnhub_free_transport() -> None:
    from app.market_intelligence.adapters import EndpointClass
    from app.market_intelligence.controls import UsageLedger

    pulse = OperationalMarketPulse(api_key="synthetic-key", now=lambda: NOW)
    assert pulse._finnhub is not None
    assert EndpointClass.MARKET_NEWS.value == "market_news"
    assert EndpointClass.MARKET_EARNINGS_CALENDAR.value == "market_earnings_calendar"


def test_pulse_route_returns_sanitized_503_when_unwired(client) -> None:
    from app.routes.market_briefs import configure_market_pulse

    configure_market_pulse(None)
    try:
        response = client.get("/api/v1/market-briefs/pulse")
    finally:
        configure_market_pulse(None)
    assert response.status_code == 503
    assert response.json()["reason_code"] == "provider_configuration_missing"
