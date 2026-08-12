"""Trusted server-only market brief input assembly; no client financial payloads."""
from __future__ import annotations
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Protocol
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.account import Account
from app.models.holding import Holding
from .briefing import BriefingInput, PositionInput
from .adapters import FinnhubAdapter, ProviderConfigurationError, SecAdapter
from .contracts import CompanyNewsItem, EarningsEvent, EarningsResult, Freshness, MarketQuoteSnapshot, SecFilingEvent


class MarketBriefCompositionError(ValueError):
    """A server-owned market input was incomplete or not safe to brief."""


class OperationalMarketResearchProviders:
    """Narrow, server-owned adapter composition for the operational route.

    Construction performs no network I/O.  Every provider result is unwrapped
    here so an upstream failure can never become a partial, authoritative
    briefing.  SEC filing lookup is deliberately deferred until Atlas has a
    trusted holding-to-CIK mapping; guessing from a symbol would weaken
    provenance.
    """
    def __init__(self, *, finnhub_api_key: str, sec_user_agent: str) -> None:
        self._finnhub = FinnhubAdapter(api_key=finnhub_api_key, enabled=True)
        # Validate the required SEC operator configuration at startup.  Do
        # not make a network request until a future authoritative CIK mapping
        # exists.
        self._sec = SecAdapter(user_agent=sec_user_agent, enabled=True)

    @staticmethod
    def _value(result, label: str):
        if result.value is None:
            detail = result.failure.message if result.failure else "provider returned no usable record"
            raise MarketBriefCompositionError(f"{label} is unavailable: {detail}")
        return result.value

    def quote(self, symbol: str) -> MarketQuoteSnapshot:
        return self._value(self._finnhub.quote(symbol), f"Quote for {symbol}")

    def news(self, symbol: str) -> list[CompanyNewsItem]:
        today = datetime.now(UTC).date()
        return self._value(self._finnhub.company_news(symbol, from_date=(today - timedelta(days=14)).isoformat(), to_date=today.isoformat()), f"News for {symbol}")

    def earnings_events(self, symbol: str) -> list[EarningsEvent]:
        return self._value(self._finnhub.earnings_calendar(symbol), f"Earnings calendar for {symbol}")

    def earnings_results(self, symbol: str) -> list[EarningsResult]:
        return self._value(self._finnhub.earnings_surprises(symbol), f"Earnings results for {symbol}")

    def filings(self) -> list[SecFilingEvent]:
        return []


def build_operational_market_brief_composer(settings: object) -> "TrustedMarketBriefComposer | None":
    """Build only when all server-owned rollout/configuration gates are true.

    No browser input, default configuration, or missing credential can cause
    a provider client to be wired.  Invalid SEC configuration fails closed.
    """
    if not (getattr(settings, "atlas_market_brief_generation_enabled", False) and getattr(settings, "atlas_market_brief_external_provider_enabled", False)):
        return None
    api_key = (getattr(settings, "finnhub_api_key", None) or "").strip()
    sec_user_agent = (getattr(settings, "sec_user_agent", None) or "").strip()
    if not api_key or not sec_user_agent:
        return None
    try:
        return TrustedMarketBriefComposer(OperationalMarketResearchProviders(finnhub_api_key=api_key, sec_user_agent=sec_user_agent))
    except ProviderConfigurationError:
        return None


class MarketResearchProviders(Protocol):
    def quote(self, symbol: str) -> MarketQuoteSnapshot | None: ...
    def news(self, symbol: str) -> list[CompanyNewsItem]: ...
    def earnings_events(self, symbol: str) -> list[EarningsEvent]: ...
    def earnings_results(self, symbol: str) -> list[EarningsResult]: ...
    def filings(self) -> list[SecFilingEvent]: ...


class TrustedMarketBriefComposer:
    def __init__(self, providers: MarketResearchProviders, *, now: callable | None = None) -> None:
        self.providers, self._now = providers, now or (lambda: datetime.now(UTC))

    def assemble(self, session: Session, *, owner_id: int, report_window: str) -> BriefingInput:
        holdings = session.scalars(
            select(Holding)
            .join(Account)
            .where(Account.user_id == owner_id, Account.is_active.is_(True))
            .order_by(Holding.symbol.asc(), Holding.id.asc())
        ).all()
        symbols = sorted({holding.symbol.strip().upper() for holding in holdings if holding.symbol and (holding.type or "").lower() != "cash"})[:50]
        if not symbols:
            raise MarketBriefCompositionError("No active, market-addressable portfolio holdings are available.")
        positions: list[PositionInput] = []
        news: list[CompanyNewsItem] = []
        events: list[EarningsEvent] = []
        results: list[EarningsResult] = []
        now = self._now()
        for symbol in symbols:
            quote = self.providers.quote(symbol)
            if quote is None:
                raise MarketBriefCompositionError(f"Quote for {symbol} is unavailable.")
            if quote.source.freshness is not Freshness.FRESH or not quote.source.source_url or quote.previous_close is None:
                raise MarketBriefCompositionError(f"Quote for {symbol} is stale or incomplete.")
            matching_holdings = [
                item for item in holdings
                if (item.symbol or "").strip().upper() == symbol and (item.type or "").lower() != "cash"
            ]
            quantity = None if any(item.quantity is None for item in matching_holdings) else format(
                sum((Decimal(str(item.quantity)) for item in matching_holdings), Decimal(0)).normalize(), "f"
            )
            positions.append(PositionInput(symbol=symbol, quantity=quantity, current_price=quote.current_price, previous_close=quote.previous_close, currency=quote.currency, source=quote.source, freshness=quote.source.freshness))
            news.extend(self.providers.news(symbol)[:20])
            events.extend(event for event in self.providers.earnings_events(symbol) if now.date() - timedelta(days=14) <= event.event_date.date() <= now.date() + timedelta(days=30))
            results.extend(result for result in self.providers.earnings_results(symbol) if result.source.observed_at and now.date() - timedelta(days=14) <= result.source.observed_at.date() <= now.date())
        if len({position.currency for position in positions}) != 1:
            raise MarketBriefCompositionError("Portfolio currency is ambiguous.")
        canonical = "|".join(f"{position.symbol}:{position.quantity}:{position.current_price}" for position in positions)
        state_hash = hashlib.sha256(canonical.encode()).hexdigest()
        universe_hash = hashlib.sha256("|".join(symbols).encode()).hexdigest()
        # Holdings have no authoritative CIK field.  Never infer an issuer
        # identifier from a ticker; expose the deliberate filing limitation.
        return BriefingInput(owner_id=owner_id, portfolio_state_hash=state_hash, universe_hash=universe_hash, report_window=report_window, positions=positions, news=news, earnings_events=events, earnings_results=results, filings=self.providers.filings()[:50], composition_warnings=("SEC filings omitted: no authoritative holding-to-CIK mapping.",), generated_at=now)
