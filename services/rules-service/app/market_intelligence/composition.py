"""Trusted server-only market brief input assembly; no client financial payloads."""
from __future__ import annotations
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Protocol
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.account import Account
from app.models.holding import Holding
from .briefing import BriefingInput, PositionInput
from .contracts import CompanyNewsItem, EarningsEvent, EarningsResult, MarketQuoteSnapshot, SecFilingEvent


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
        holdings = session.scalars(select(Holding).join(Account).where(Account.user_id == owner_id).order_by(Holding.symbol.asc(), Holding.id.asc())).all()
        symbols = sorted({holding.symbol.strip().upper() for holding in holdings if holding.symbol and (holding.type or "").lower() != "cash"})[:50]
        positions: list[PositionInput] = []
        news: list[CompanyNewsItem] = []
        events: list[EarningsEvent] = []
        results: list[EarningsResult] = []
        now = self._now()
        for symbol in symbols:
            quote = self.providers.quote(symbol)
            if quote is None:
                continue
            holding = next(item for item in holdings if (item.symbol or "").strip().upper() == symbol)
            positions.append(PositionInput(symbol=symbol, quantity=str(holding.quantity) if holding.quantity is not None else None, current_price=quote.current_price, previous_close=quote.previous_close, currency=quote.currency, source=quote.source, freshness=quote.source.freshness))
            news.extend(self.providers.news(symbol)[:20])
            events.extend(event for event in self.providers.earnings_events(symbol) if now.date() - timedelta(days=14) <= event.event_date.date() <= now.date() + timedelta(days=30))
            results.extend(result for result in self.providers.earnings_results(symbol) if result.source.observed_at and now.date() - timedelta(days=14) <= result.source.observed_at.date() <= now.date())
        canonical = "|".join(f"{position.symbol}:{position.quantity}:{position.current_price}" for position in positions)
        state_hash = hashlib.sha256(canonical.encode()).hexdigest()
        universe_hash = hashlib.sha256("|".join(symbols).encode()).hexdigest()
        return BriefingInput(owner_id=owner_id, portfolio_state_hash=state_hash, universe_hash=universe_hash, report_window=report_window, positions=positions, news=news, earnings_events=events, earnings_results=results, filings=self.providers.filings()[:50], generated_at=now)
