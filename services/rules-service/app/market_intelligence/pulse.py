"""Market Intelligence v2 market-pulse composition.

Zero-dollar, quota-aware layer that answers "what is happening across the
broader market" without paid endpoints:

- index direction via approved ETF proxies (SPY/QQQ) when the free tier
  cannot quote the raw index (truthfully labeled, never fabricated);
- free-tier general market news (single call, cached);
- market-wide earnings calendar for a bounded window;
- a bounded S&P 500 scanner: the bundled factual symbol list is NEVER
  requested wholesale. Quotes are fetched for a bounded sample with the
  provider pacer and cache, portfolio holdings take priority, and every
  unavailable category is exposed truthfully.

This module never fabricates data and never calls a paid endpoint.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from .adapters import FinnhubAdapter
from .contracts import (
    EarningsEvent,
    MarketIndexQuote,
    MarketNewsItem,
    MarketPulseSnapshot,
    MarketQuoteSnapshot,
)

SP500_SYMBOLS_PATH = Path(__file__).resolve().parent / "data" / "sp500_symbols.json"

# Approved ETF proxies for indices the free tier cannot quote directly.
# Label always states the proxy; the value is never passed off as the index.
INDEX_PROXIES: tuple[tuple[str, str], ...] = (
    ("S&P 500 (SPY proxy)", "SPY"),
    ("Nasdaq-100 (QQQ proxy)", "QQQ"),
)

MAX_SCAN_SYMBOLS = 20
SCAN_TTL_SECONDS = 300


def load_sp500_symbols() -> tuple[str, ...]:
    """Bundled factual S&P 500 ticker list; read-only scanner input."""
    data = json.loads(SP500_SYMBOLS_PATH.read_text(encoding="utf-8"))
    return tuple(sorted({str(symbol).strip().upper() for symbol in data if symbol}))


class MarketPulseProviders(Protocol):
    def quote(self, symbol: str) -> MarketQuoteSnapshot | None: ...
    def market_news(self, *, limit: int = 15) -> list[MarketNewsItem]: ...
    def market_earnings_calendar(self, *, from_date: str, to_date: str) -> list[EarningsEvent]: ...


class OperationalMarketPulse:
    """Server-owned pulse providers; the Finnhub free tier is the only source."""

    def __init__(self, *, api_key: str, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._finnhub = FinnhubAdapter(api_key=api_key, enabled=True, now=self._now)

    def quote(self, symbol: str) -> MarketQuoteSnapshot | None:
        result = self._finnhub.quote(symbol)
        return result.value

    def market_news(self, *, limit: int = 15) -> list[MarketNewsItem]:
        result = self._finnhub.market_news(limit=limit)
        if result.failure:
            return []
        return result.value or []

    def market_earnings_calendar(self, *, from_date: str, to_date: str) -> list[EarningsEvent]:
        result = self._finnhub.market_earnings_calendar(from_date=from_date, to_date=to_date)
        if result.failure:
            return []
        return result.value or []


class MarketPulseComposer:
    """Assembles the bounded market-pulse snapshot with truthful states."""

    def __init__(
        self,
        providers: MarketPulseProviders,
        *,
        sp500_symbols: tuple[str, ...] | None = None,
        now: Callable[[], datetime] | None = None,
        max_scan_symbols: int = MAX_SCAN_SYMBOLS,
    ) -> None:
        self.providers = providers
        self._now = now or (lambda: datetime.now(UTC))
        self._sp500_symbols = sp500_symbols if sp500_symbols is not None else load_sp500_symbols()
        self._max_scan_symbols = max_scan_symbols

    @staticmethod
    def _index_quote(label: str, symbol: str, provider) -> MarketIndexQuote | None:
        quote = provider.quote(symbol)
        if quote is None:
            return None
        current = float(quote.current_price) if quote.current_price else 0.0
        previous = float(quote.previous_close) if quote.previous_close else 0.0
        if current <= 0 or previous <= 0:
            direction = "unavailable"
        elif current > previous:
            direction = "up"
        elif current < previous:
            direction = "down"
        else:
            direction = "flat"
        return MarketIndexQuote(
            label=label,
            symbol=symbol,
            current_price=quote.current_price,
            previous_close=quote.previous_close,
            direction=direction,
            is_etf_proxy=True,
            source=quote.source,
        )

    def assemble(self, *, priority_symbols: tuple[str, ...] = ()) -> MarketPulseSnapshot:
        now = self._now()
        categories_unavailable: list[str] = []

        # ---- Indices (ETF proxies; truthful labeling) ----
        indices: list[MarketIndexQuote] = []
        for label, symbol in INDEX_PROXIES:
            index = self._index_quote(label, symbol, self.providers)
            if index is not None:
                indices.append(index)
        if not indices:
            categories_unavailable.append("indices")

        # ---- Market-wide news ----
        news = self.providers.market_news(limit=15)
        if not news:
            categories_unavailable.append("market_news")

        # ---- Market-wide earnings calendar (next 14 days) ----
        today = now.date()
        try:
            calendar = self.providers.market_earnings_calendar(
                from_date=today.isoformat(),
                to_date=(today + timedelta(days=14)).isoformat(),
            )
        except Exception:
            calendar = []
        if not calendar:
            categories_unavailable.append("earnings_calendar")

        # ---- Bounded S&P 500 scanner ----
        # Portfolio holdings first, then the bundled universe, deduplicated,
        # capped at the quota-aware bound. The provider pacer + cache keep
        # this within the free-tier ceiling.
        ordered = list(dict.fromkeys([*priority_symbols, *self._sp500_symbols]))[: self._max_scan_symbols]
        scanned: list[MarketQuoteSnapshot] = []
        for symbol in ordered:
            quote = self.providers.quote(symbol)
            if quote is not None:
                scanned.append(quote)
        if not scanned:
            categories_unavailable.append("scanner")

        return MarketPulseSnapshot(
            indices=tuple(indices),
            news=tuple(news),
            earnings_calendar=tuple(calendar[:30]),
            scanner=tuple(scanned),
            scanned_symbol_count=len(scanned),
            total_universe_size=len(self._sp500_symbols),
            categories_unavailable=tuple(sorted(categories_unavailable)),
            generated_at=now,
        )


def build_operational_market_pulse(settings: object) -> MarketPulseComposer | None:
    """Build only when server-owned rollout gates and the key are present."""
    if not (
        getattr(settings, "atlas_market_brief_generation_enabled", False)
        and getattr(settings, "atlas_market_brief_external_provider_enabled", False)
    ):
        return None
    api_key = (getattr(settings, "finnhub_api_key", None) or "").strip()
    if not api_key:
        return None
    return MarketPulseComposer(OperationalMarketPulse(api_key=api_key))
