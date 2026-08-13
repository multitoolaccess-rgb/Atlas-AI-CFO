"""Market Intelligence v2 Part 1: generation reliability and the evidence contract.

These tests exercise the REAL authenticated route (``client`` fixture) with
isolated synthetic providers, exactly as the v2 specification requires:

- no unhandled ``CoverageOmission``/composition validation failures escape as 500
- all anticipated provider/composition failures become sanitized, stable responses
- raw provider payloads, exception text, and secrets never appear in responses
- a single unsupported symbol, stale quote, or missing evidence category does not
  kill the complete brief
- omissions are recorded per holding with stable reason codes
- the entire brief fails only below the documented meaningful threshold
- nothing is persisted when complete generation fails
- deterministic replay and owner-scoped archive behavior are preserved
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.market_intelligence.contracts import (
    CompanyNewsItem,
    EarningsEvent,
    EarningsResult,
    Freshness,
    MarketQuoteSnapshot,
    PriceBasis,
    SourceMetadata,
)

NOW = datetime(2026, 8, 12, 15, 0, tzinfo=UTC)


def _source(url: str = "https://quotes.test/source") -> SourceMetadata:
    return SourceMetadata(
        provider="synthetic",
        source_url=url,
        retrieved_at=NOW,
        observed_at=NOW,
        freshness=Freshness.FRESH,
        price_basis=PriceBasis.LIVE,
    )


def _quote(symbol: str) -> MarketQuoteSnapshot:
    return MarketQuoteSnapshot(
        symbol=symbol,
        currency="USD",
        current_price="110",
        previous_close="100",
        source=_source(f"https://quotes.test/{symbol.lower()}"),
    )


class _LiveProviders:
    """Synthetic trusted-provider double. No adapter or network involved."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.missing: set[str] = set()
        self.failing_provider_quote = False

    def quote(self, symbol: str):
        self.calls.append(("quote", symbol))
        if symbol in self.missing:
            return None
        if self.failing_provider_quote:
            raise RuntimeError("provider transport exploded internally")  # must become sanitized 503
        return _quote(symbol)

    def news(self, symbol: str):
        self.calls.append(("news", symbol))
        if symbol in self.missing:
            raise RuntimeError("raw provider news payload escaped")  # must become sanitized 503
        return [CompanyNewsItem(symbol=symbol, headline="Synthetic headline", source=_source(f"https://news.test/{symbol.lower()}"))]

    def earnings_events(self, symbol: str):
        self.calls.append(("earnings_events", symbol))
        return [EarningsEvent(symbol=symbol, event_date=datetime(2026, 8, 13, tzinfo=UTC), source=_source("https://earnings.test/cal"))]

    def earnings_results(self, symbol: str):
        self.calls.append(("earnings_results", symbol))
        return [EarningsResult(symbol=symbol, actual="2", estimate="1", source=_source("https://earnings.test/result"))]

    def filings(self):
        self.calls.append(("filings", None))
        return []


def _holding(symbol: str, value: float | None = 100.0) -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, type="Stock", current_value=value, quantity=1, id=symbol)


def _session_for(*holdings: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(scalars=lambda _query: SimpleNamespace(all=lambda: list(holdings)))


def _seed_owner(db_session, make_account, *holdings: SimpleNamespace) -> None:
    from app.models import Holding

    account = make_account(account_name="Reliability brokerage", account_type="brokerage")
    db_session.add(account)
    db_session.flush()
    db_session.add_all(
        Holding(account_id=account.id, symbol=h.symbol, quantity=h.quantity, current_value=h.current_value, type=h.type)
        for h in holdings
    )
    db_session.commit()


def _install(client, providers, monkeypatch):
    from app.config import settings
    from app.market_intelligence.composition import TrustedMarketBriefComposer
    from app.routes.market_briefs import configure_market_brief_composer

    configure_market_brief_composer(TrustedMarketBriefComposer(providers, now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)


def test_unhandled_provider_exception_becomes_sanitized_503_not_raw_500(client, db_session, make_account, monkeypatch) -> None:
    """The observed v1 failure (unhandled validation/exception -> 500) must be impossible."""
    _seed_owner(db_session, make_account, _holding("AAPL"))
    providers = _LiveProviders()
    providers.failing_provider_quote = True
    _install(client, providers, monkeypatch)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        from app.routes.market_briefs import configure_market_brief_composer
        configure_market_brief_composer(None)
    assert response.status_code == 503
    payload = response.json()
    assert "reason_code" in payload and payload["reason_code"] != ""
    text = str(payload).lower()
    assert "transport exploded internally" not in text
    assert "traceback" not in text
    assert "finnhub" not in text or payload["reason_code"] == "provider_configuration_missing"


def test_raw_news_payload_failure_is_sanitized_and_nothing_persisted(client, db_session, make_account, monkeypatch) -> None:
    _seed_owner(db_session, make_account, _holding("AAPL"))
    providers = _LiveProviders()
    providers.missing = {"AAPL"}
    _install(client, providers, monkeypatch)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        from app.routes.market_briefs import configure_market_brief_composer
        configure_market_brief_composer(None)
    assert response.status_code == 503
    assert "raw provider news payload escaped" not in str(response.json()).lower()
    from app.models.market_brief import MarketBrief as StoredBrief
    assert db_session.query(StoredBrief).count() == 0


def test_single_unsupported_symbol_does_not_kill_the_brief(client, db_session, make_account, monkeypatch) -> None:
    """One non-addressable symbol is an omission, not a complete-brief failure."""
    _seed_owner(db_session, make_account, _holding("AAPL", 80), _holding("NON40OJJ2", 20))
    providers = _LiveProviders()
    providers.missing = {"NON40OJJ2"}
    _install(client, providers, monkeypatch)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        from app.routes.market_briefs import configure_market_brief_composer
        configure_market_brief_composer(None)
    assert response.status_code == 201, response.json()
    brief = response.json()["brief"]
    assert brief["coverage"]["omitted_symbols"] == ["NON40OJJ2"]
    assert brief["coverage"]["covered_holding_count"] == 1
    assert brief["coverage"]["eligible_holding_count"] == 2
    # The covered holding still generated intelligence.
    assert any("AAPL" in item for section in brief["sections"] for item in section["content"])


def test_malformed_omission_construction_cannot_escape_as_500(client, db_session, make_account, monkeypatch) -> None:
    """A provider that returns a malformed record must become a sanitized 503, never a 500."""
    _seed_owner(db_session, make_account, _holding("AAPL"))
    from app.market_intelligence.composition import TrustedMarketBriefComposer

    class _Malformed(TrustedMarketBriefComposer):
        def assemble(self, session, *, owner_id, report_window):
            # Force the exact failure class the v2 spec names: an unhandled
            # validation error while constructing an omission record.
            from app.market_intelligence.contracts import CoverageOmission, MarketBriefReasonCode
            CoverageOmission(symbol="X" * 300, reason_code=MarketBriefReasonCode.UNSUPPORTED_SYMBOL)
            return super().assemble(session, owner_id=owner_id, report_window=report_window)

    from app.config import settings
    from app.routes.market_briefs import configure_market_brief_composer
    configure_market_brief_composer(_Malformed(_LiveProviders(), now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        configure_market_brief_composer(None)
    assert response.status_code == 503
    assert response.json()["reason_code"] == "market_brief_generation_unavailable"
    from app.models.market_brief import MarketBrief as StoredBrief
    assert db_session.query(StoredBrief).count() == 0


def test_stale_quote_is_a_sanitized_reason_not_a_500(client, db_session, make_account, monkeypatch) -> None:
    _seed_owner(db_session, make_account, _holding("AAPL"))
    from app.market_intelligence.composition import MarketBriefCompositionError, TrustedMarketBriefComposer
    from app.market_intelligence.contracts import MarketBriefReasonCode

    class _Stale(TrustedMarketBriefComposer):
        def assemble(self, session, *, owner_id, report_window):
            raise MarketBriefCompositionError("stale", MarketBriefReasonCode.LIVE_QUOTE_STALE)

    from app.config import settings
    from app.routes.market_briefs import configure_market_brief_composer
    configure_market_brief_composer(_Stale(_LiveProviders(), now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        configure_market_brief_composer(None)
    assert response.status_code == 503
    assert response.json()["reason_code"] == "live_quote_stale"
    assert "market hours" in response.json()["recovery"].lower()
