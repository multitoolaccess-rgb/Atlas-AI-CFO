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

    def profile(self, _symbol: str):
        return None

    def analyst_recommendations(self, _symbol: str) -> list:
        return []

    def price_target(self, _symbol: str):
        return None

    def dividends(self, _symbol: str) -> list:
        return []

    def filings_for_cik(self, _cik: str) -> list:
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


def test_non_market_holding_labels_are_omitted_without_provider_requests() -> None:
    brief_input = TrustedMarketBriefComposer(Providers(), now=lambda: NOW).assemble(
        session_for(holding("AAPL", 95), holding("PENDING ACTIVITY", 5)), owner_id=1, report_window="latest"
    )
    assert brief_input.coverage is not None
    assert brief_input.coverage.coverage_percentage == "0.95"
    assert brief_input.coverage.omitted_symbols == ("UNKNOWN",)
    assert brief_input.coverage.omissions[0].reason_code is MarketBriefReasonCode.UNSUPPORTED_SYMBOL


def test_position_count_coverage_is_used_when_current_values_are_not_complete() -> None:
    holdings = [holding("AAPL", None), holding("MSFT", None), holding("NVDA", None), holding("TSLA", None), holding("BAD", None)]
    brief_input = TrustedMarketBriefComposer(Providers(missing={"BAD"}), now=lambda: NOW).assemble(
        session_for(*holdings), owner_id=1, report_window="latest"
    )
    assert brief_input.coverage is not None
    assert brief_input.coverage.coverage_basis.value == "position_count"
    assert brief_input.coverage.coverage_percentage == "0.8"


def test_below_threshold_coverage_still_generates_partial_brief_with_disclosure() -> None:
    """Below-threshold coverage no longer blocks generation: the brief is
    built from covered holdings and discloses every omission with its reason.
    """
    brief_input = TrustedMarketBriefComposer(Providers(missing={"MSFT"}), now=lambda: NOW).assemble(
        session_for(holding("AAPL", 50), holding("MSFT", 50)), owner_id=1, report_window="latest"
    )
    assert brief_input.coverage is not None
    assert brief_input.coverage.coverage_percentage == "0.5"
    assert brief_input.coverage.covered_holding_count == 1
    assert brief_input.coverage.omitted_holding_count == 1
    assert brief_input.coverage.omitted_symbols == ("MSFT",)
    assert brief_input.coverage.omissions[0].reason_code is MarketBriefReasonCode.UNSUPPORTED_SYMBOL
    # The brief renders only the covered position and carries the omissions.
    assert [position.symbol for position in brief_input.positions] == ["AAPL"]
    assert brief_input.provider_readiness.status == "degraded"


def test_no_covered_holdings_and_mixed_currency_fail_closed() -> None:
    with pytest.raises(MarketBriefCompositionError) as none:
        TrustedMarketBriefComposer(Providers(missing={"AAPL"}), now=lambda: NOW).assemble(
            session_for(holding("AAPL", 100)), owner_id=1, report_window="latest"
        )
    assert none.value.reason_code is MarketBriefReasonCode.UNSUPPORTED_SYMBOL
    assert none.value.omitted_symbols == ("AAPL",)

    with pytest.raises(MarketBriefCompositionError) as currency:
        TrustedMarketBriefComposer(Providers(currencies={"AAPL": "USD", "MSFT": "EUR"}), now=lambda: NOW).assemble(
            session_for(holding("AAPL", 50), holding("MSFT", 50)), owner_id=1, report_window="latest"
        )
    assert currency.value.reason_code is MarketBriefReasonCode.AMBIGUOUS_CURRENCY


def test_all_unsupported_symbols_report_an_actionable_reason() -> None:
    with pytest.raises(MarketBriefCompositionError) as unsupported:
        TrustedMarketBriefComposer(Providers(missing={"AAPL", "MSFT"}), now=lambda: NOW).assemble(
            session_for(holding("AAPL", 50), holding("MSFT", 50)), owner_id=1, report_window="latest"
        )
    assert unsupported.value.reason_code is MarketBriefReasonCode.UNSUPPORTED_SYMBOL
    assert unsupported.value.omitted_symbols == ("AAPL", "MSFT")


def test_evidence_ranking_marks_high_impact_for_upcoming_earnings() -> None:
    from app.market_intelligence.composition import TrustedMarketBriefComposer
    from app.market_intelligence.contracts import EarningsEvent

    composer = TrustedMarketBriefComposer(Providers(), now=lambda: NOW)
    packet = composer._rank_evidence(
        symbol="AAPL",
        quote=None,
        profile=None,
        news=(),
        earnings_events=(EarningsEvent(symbol="AAPL", event_date=datetime(2026, 8, 15, tzinfo=UTC), source=source("AAPL")),),
        earnings_results=(),
        filings=(),
        recommendations=(),
        price_target=None,
        dividends=(),
        now=NOW,
    )
    assert packet.materiality == "high"
    assert "7 days" in (packet.materiality_reason or "")


def test_evidence_ranking_marks_watch_for_large_price_movement() -> None:
    from app.market_intelligence.composition import TrustedMarketBriefComposer

    composer = TrustedMarketBriefComposer(Providers(), now=lambda: NOW)
    packet = composer._rank_evidence(
        symbol="AAPL",
        quote=MarketQuoteSnapshot(symbol="AAPL", currency="USD", current_price="104", previous_close="100", source=source("AAPL")),
        profile=None,
        news=(),
        earnings_events=(),
        earnings_results=(),
        filings=(),
        recommendations=(),
        price_target=None,
        dividends=(),
        now=NOW,
    )
    assert packet.materiality == "watch"
    assert "3%" in (packet.materiality_reason or "")


def test_evidence_ranking_keeps_informational_when_no_catalyst() -> None:
    from app.market_intelligence.composition import TrustedMarketBriefComposer

    composer = TrustedMarketBriefComposer(Providers(), now=lambda: NOW)
    packet = composer._rank_evidence(
        symbol="AAPL",
        quote=MarketQuoteSnapshot(symbol="AAPL", currency="USD", current_price="100.5", previous_close="100", source=source("AAPL")),
        profile=None,
        news=(),
        earnings_events=(),
        earnings_results=(),
        filings=(),
        recommendations=(),
        price_target=None,
        dividends=(),
        now=NOW,
    )
    assert packet.materiality == "informational"


def test_evidence_ranking_marks_watch_for_8k_filing() -> None:
    from app.market_intelligence.composition import TrustedMarketBriefComposer
    from app.market_intelligence.contracts import SecFilingEvent

    composer = TrustedMarketBriefComposer(Providers(), now=lambda: NOW)
    filing = SecFilingEvent(
        cik="320193", form="8-K", accession_number="0001-01",
        filing_date=datetime(2026, 8, 11, tzinfo=UTC), source=source("AAPL"),
    )
    packet = composer._rank_evidence(
        symbol="AAPL", quote=None, profile=None, news=(), earnings_events=(), earnings_results=(),
        filings=(filing,), recommendations=(), price_target=None, dividends=(), now=NOW,
    )
    assert packet.materiality == "high"
    assert "8-K" in (packet.materiality_reason or "")


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
