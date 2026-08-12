from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.market_intelligence.composition import MarketBriefCompositionError, TrustedMarketBriefComposer
from app.market_intelligence.contracts import (
    EarningsEvent,
    EarningsResult,
    Freshness,
    MarketBriefReasonCode,
    MarketQuoteSnapshot,
    PriceBasis,
    SourceMetadata,
)

NOW = datetime(2026, 8, 11, 15, 0, tzinfo=UTC)


def source(symbol: str, *, currency: str = "USD", basis: PriceBasis = PriceBasis.LIVE) -> SourceMetadata:
    return SourceMetadata(
        provider="synthetic",
        source_url=f"https://quotes.test/{symbol.lower()}",
        retrieved_at=NOW,
        observed_at=NOW,
        freshness=Freshness.FRESH,
        price_basis=basis,
    )


class Providers:
    def __init__(self, missing: set[str] | None = None, currencies: dict[str, str] | None = None) -> None:
        self.missing = missing or set()
        self.currencies = currencies or {}

    def quote(self, symbol: str):
        if symbol in self.missing:
            return None
        currency = self.currencies.get(symbol, "USD")
        return MarketQuoteSnapshot(
            symbol=symbol,
            currency=currency,
            current_price="110",
            previous_close="100",
            source=source(symbol, currency=currency),
        )

    def news(self, _symbol: str):
        return []

    def earnings_events(self, _symbol: str) -> list[EarningsEvent]:
        return []

    def earnings_results(self, _symbol: str) -> list[EarningsResult]:
        return []

    def filings(self):
        return []


def holding(symbol: str, value: float | None) -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, type="Stock", current_value=value, quantity=1, id=symbol)


def session_for(*holdings: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(scalars=lambda _query: SimpleNamespace(all=lambda: list(holdings)))


def test_value_weighted_coverage_accepts_partial_portfolio_at_documented_threshold() -> None:
    holdings = [holding("AAPL", 40), holding("MSFT", 30), holding("NVDA", 20), holding("BAD", 5), holding("TSLA", 5)]
    brief_input = TrustedMarketBriefComposer(Providers(missing={"TSLA"}), now=lambda: NOW).assemble(
        session_for(*holdings), owner_id=1, report_window="latest"
    )
    assert brief_input.coverage is not None
    assert brief_input.coverage.coverage_basis.value == "value_weighted"
    assert brief_input.coverage.coverage_percentage == "0.95"
    assert brief_input.coverage.omitted_symbols == ("TSLA",)
    assert brief_input.coverage.omissions[0].reason_code is MarketBriefReasonCode.UNSUPPORTED_SYMBOL
    assert brief_input.portfolio_state_hash != "" and len(brief_input.portfolio_state_hash) == 64


def test_position_count_coverage_is_used_when_current_values_are_not_complete() -> None:
    holdings = [holding("AAPL", None), holding("MSFT", None), holding("NVDA", None), holding("TSLA", None), holding("BAD", None)]
    brief_input = TrustedMarketBriefComposer(Providers(missing={"BAD"}), now=lambda: NOW).assemble(
        session_for(*holdings), owner_id=1, report_window="latest"
    )
    assert brief_input.coverage is not None
    assert brief_input.coverage.coverage_basis.value == "position_count"
    assert brief_input.coverage.coverage_percentage == "0.8"


def test_below_threshold_no_coverage_and_mixed_currency_fail_closed() -> None:
    with pytest.raises(MarketBriefCompositionError) as below:
        TrustedMarketBriefComposer(Providers(missing={"MSFT"}), now=lambda: NOW).assemble(
            session_for(holding("AAPL", 50), holding("MSFT", 50)), owner_id=1, report_window="latest"
        )
    assert below.value.reason_code is MarketBriefReasonCode.INSUFFICIENT_PORTFOLIO_COVERAGE

    with pytest.raises(MarketBriefCompositionError) as none:
        TrustedMarketBriefComposer(Providers(missing={"AAPL"}), now=lambda: NOW).assemble(
            session_for(holding("AAPL", 100)), owner_id=1, report_window="latest"
        )
    assert none.value.reason_code is MarketBriefReasonCode.NO_MARKET_ADDRESSABLE_HOLDINGS

    with pytest.raises(MarketBriefCompositionError) as currency:
        TrustedMarketBriefComposer(Providers(currencies={"AAPL": "USD", "MSFT": "EUR"}), now=lambda: NOW).assemble(
            session_for(holding("AAPL", 50), holding("MSFT", 50)), owner_id=1, report_window="latest"
        )
    assert currency.value.reason_code is MarketBriefReasonCode.AMBIGUOUS_CURRENCY


def test_canonical_identity_includes_price_basis_and_coverage() -> None:
    holdings = [holding("AAPL", 100)]
    live = TrustedMarketBriefComposer(Providers(), now=lambda: NOW).assemble(session_for(*holdings), owner_id=1, report_window="latest")
    class PriorProviders(Providers):
        def quote(self, symbol: str):
            return MarketQuoteSnapshot(
                symbol=symbol,
                currency="USD",
                current_price="110",
                previous_close="100",
                source=source(symbol, basis=PriceBasis.PRIOR_CLOSE),
            )

    prior = TrustedMarketBriefComposer(PriorProviders(), now=lambda: NOW).assemble(
        session_for(*holdings), owner_id=1, report_window="latest"
    )
    assert live.market_data_basis is PriceBasis.LIVE
    assert prior.market_data_basis is PriceBasis.PRIOR_CLOSE
    assert live.portfolio_state_hash != prior.portfolio_state_hash
    assert live.universe_hash != prior.universe_hash
