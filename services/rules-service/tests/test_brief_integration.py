"""Integration tests for the Market Intelligence-backed Daily Investment Brief.

The brief shares the ``TrustedMarketBriefComposer`` with the Market
Intelligence workspace. These tests stub that composer with deterministic
evidence and assert the route maps it into the redesigned ``BriefSummary``
contract (hero P&L, top movers, market context, news, earnings, coverage
quality) and fails closed when the composer is unavailable or composition
rejects the portfolio.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.market_intelligence.briefing import BriefingInput, PositionInput
from app.market_intelligence.composition import MarketBriefCompositionError
from app.market_intelligence.contracts import (
    CompanyNewsItem,
    CoverageBasis,
    CoverageOmission,
    CoverageSummary,
    EarningsEvent,
    EvidenceCategory,
    Freshness,
    MarketBriefReasonCode,
    MarketQuoteSnapshot,
    PriceBasis,
    ProviderReadiness,
    SourceMetadata,
)


def _source(url: str = "https://example.com/a") -> SourceMetadata:
    return SourceMetadata(
        provider="finnhub",
        source_url=url,
        retrieved_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc) - timedelta(hours=2),
        freshness=Freshness.FRESH,
        price_basis=PriceBasis.LIVE,
    )


def _quote(symbol: str, current: str, previous: str) -> MarketQuoteSnapshot:
    return MarketQuoteSnapshot(
        symbol=symbol,
        current_price=current,
        previous_close=previous,
        currency="USD",
        source=_source(f"https://finnhub.io/quote/{symbol}"),
    )


class FakeProviders:
    """Stub provider returning index pills plus per-holding news."""

    _PRICES = {
        "SPY": ("500.0", "495.0"),
        "QQQ": ("400.0", "405.0"),
        "VTI": ("250.0", "248.0"),
    }

    _NEWS = {
        "AAPL": [
            CompanyNewsItem(
                symbol="AAPL",
                headline="Apple earnings beat",
                summary="Strong quarter",
                publisher="Reuters",
                source=_source("https://example.com/apple"),
            )
        ],
        "MSFT": [
            CompanyNewsItem(
                symbol="MSFT",
                headline="Microsoft announces buyback",
                summary="New program",
                publisher="Bloomberg",
                source=_source("https://example.com/msft"),
            )
        ],
    }

    def quote(self, symbol: str) -> MarketQuoteSnapshot:
        current, previous = self._PRICES[symbol]
        return _quote(symbol, current, previous)

    def news(self, symbol: str) -> list[CompanyNewsItem]:
        return list(self._NEWS.get(symbol, []))

    def earnings_events(self, symbol: str) -> list[EarningsEvent]:
        # Per-holding earnings come from the pulse calendar in these tests.
        return []


def _position(symbol: str, quantity: float, current_price: float, previous_close: float, current_value: float) -> PositionInput:
    return PositionInput(
        symbol=symbol,
        quantity=str(quantity),
        current_price=str(current_price),
        previous_close=str(previous_close),
        currency="USD",
        source=_source(f"https://finnhub.io/quote/{symbol}"),
        freshness=Freshness.FRESH,
        price_basis=PriceBasis.LIVE,
        current_value=str(current_value),
    )


def _coverage(eligible: int = 2, covered: int = 2, omissions: tuple[CoverageOmission, ...] = ()) -> CoverageSummary:
    return CoverageSummary(
        eligible_holding_count=eligible,
        covered_holding_count=covered,
        omitted_holding_count=eligible - covered,
        coverage_basis=CoverageBasis.VALUE_WEIGHTED,
        coverage_percentage="0.95",
        omitted_symbols=tuple(sorted({o.symbol for o in omissions})),
        omissions=omissions,
    )


def _assembled(**overrides) -> BriefingInput:
    now = datetime.now(timezone.utc)
    base = dict(
        owner_id=1,
        portfolio_state_hash="a" * 64,
        universe_hash="b" * 64,
        report_window="latest",
        positions=[
            _position("AAPL", 10, 200.0, 190.0, 2000.0),
            _position("MSFT", 5, 300.0, 310.0, 1500.0),
        ],
        news=[
            CompanyNewsItem(
                symbol="AAPL",
                headline="Apple earnings beat",
                summary="Strong quarter",
                publisher="Reuters",
                source=_source("https://example.com/apple"),
            ),
            CompanyNewsItem(
                symbol="MSFT",
                headline="Microsoft announces buyback",
                summary="New program",
                publisher="Bloomberg",
                source=_source("https://example.com/msft"),
            ),
        ],
        earnings_events=[
            EarningsEvent(symbol="AAPL", event_date=now + timedelta(days=2), source=_source("https://example.com/aapl-earn")),
            EarningsEvent(symbol="MSFT", event_date=now + timedelta(days=5), source=_source("https://example.com/msft-earn")),
        ],
        generated_at=now,
        coverage=_coverage(),
        market_data_basis=PriceBasis.LIVE,
        provider_readiness=ProviderReadiness(provider="market_data", status="ready"),
    )
    base.update(overrides)
    return BriefingInput(**base)


class FakeComposer:
    def __init__(self, assembled: BriefingInput):
        self._assembled = assembled
        self.providers = FakeProviders()

    def assemble(self, db, *, owner_id: int, report_window: str) -> BriefingInput:
        return self._assembled


class RaisingComposer:
    providers = FakeProviders()

    def assemble(self, db, *, owner_id: int, report_window: str) -> BriefingInput:
        raise MarketBriefCompositionError(
            "No trustworthy priced holdings remain for this brief.",
            MarketBriefReasonCode.NO_MARKET_ADDRESSABLE_HOLDINGS,
        )


class FakePulseProviders:
    def __init__(self, events: list[EarningsEvent]):
        self._events = events

    def market_earnings_calendar(self, *, from_date: str, to_date: str) -> list[EarningsEvent]:
        return list(self._events)


class FakePulse:
    def __init__(self, events: list[EarningsEvent] | None = None):
        self.providers = FakePulseProviders(events or [])


@pytest.fixture
def stub_composer(monkeypatch):
    """Install a deterministic fake trusted composer for the brief route."""

    def _install(composer) -> None:
        monkeypatch.setattr(
            "app.routes.investment_brief.get_market_brief_composer",
            lambda: composer,
        )

    return _install


@pytest.fixture
def stub_pulse(monkeypatch):
    """Install a fake market-pulse composer (earnings calendar source)."""

    def _install(pulse) -> None:
        monkeypatch.setattr(
            "app.routes.investment_brief.get_market_pulse_composer",
            lambda: pulse,
        )

    return _install


def _seed_holding(db_session, account, symbol: str, value: float, quantity: float = 1.0) -> None:
    from app.models import Holding

    db_session.add(
        Holding(
            account_id=account.id,
            symbol=symbol,
            quantity=quantity,
            current_value=value,
            type="Stock",
        )
    )
    db_session.commit()


def _seed_local_user(db_session) -> None:
    from app.routes.shared import get_or_create_local_user

    get_or_create_local_user(db_session, "alex")
    db_session.commit()


class TestBriefSummary:
    def test_summary_composes_hero_news_earnings(self, client, db_session, stub_composer):
        _seed_local_user(db_session)
        stub_composer(FakeComposer(_assembled()))

        response = client.get("/api/v1/investments/brief/summary")
        assert response.status_code == 200
        body = response.json()

        # Hero P&L: AAPL 10 x (200 - 190) = +100; MSFT 5 x (300 - 310) = -50
        assert body["hero"]["daily_pnl"] == pytest.approx(50.0)
        assert body["hero"]["daily_pct"] == pytest.approx(50.0 / 3500.0 * 100.0)

        # Top gainer / loser by percent move
        assert body["hero"]["top_gainer"]["symbol"] == "AAPL"
        assert body["hero"]["top_loser"]["symbol"] == "MSFT"

        # Market context pills from the shared index proxies
        market = body["market"]
        assert market["spy_change"] == pytest.approx((500.0 - 495.0) / 495.0 * 100.0)
        assert market["qqq_change"] == pytest.approx((400.0 - 405.0) / 405.0 * 100.0)
        assert market["vti_change"] == pytest.approx((250.0 - 248.0) / 248.0 * 100.0)

        # News mapped from per-holding evidence, capped at 5
        assert len(body["news"]) == 2
        assert {item["symbols"][0] for item in body["news"]} == {"AAPL", "MSFT"}
        assert body["news"][0]["headline"]

        # Earnings within the window, sorted by date
        assert len(body["earnings"]) == 2
        assert body["earnings"][0]["symbol"] == "AAPL"
        assert body["earnings"][1]["symbol"] == "MSFT"
        aapl_event = datetime.now(timezone.utc) + timedelta(days=2)
        assert body["earnings"][0]["quarter"] == f"Q{(aapl_event.month - 1) // 3 + 1} {aapl_event.year}"

        # Quality mirrors coverage
        assert body["quality"]["coverage_eligible"] == 2
        assert body["quality"]["coverage_covered"] == 2
        assert body["quality"]["freshness"] == "fresh"

        # top_movers sorted by absolute dollar change
        assert body["top_movers"][0]["symbol"] == "AAPL"

    def test_omissions_flow_into_quality_and_warnings(self, client, db_session, stub_composer):
        _seed_local_user(db_session)
        omission = CoverageOmission(
            symbol="NON40OJJ5",
            evidence_category=EvidenceCategory.QUOTE,
            reason_code=MarketBriefReasonCode.UNSUPPORTED_SYMBOL,
            recovery="Review the holding symbol and correct it before retrying.",
        )
        stub_composer(FakeComposer(_assembled(coverage=_coverage(eligible=3, covered=2, omissions=(omission,)))))

        response = client.get("/api/v1/investments/brief/summary")
        assert response.status_code == 200
        body = response.json()

        assert body["quality"]["coverage_eligible"] == 3
        assert body["quality"]["coverage_covered"] == 2
        assert body["quality"]["freshness"] == "partial"
        assert any("NON40OJJ5" in warning for warning in body["warnings"])

    def test_market_context_pills_are_null_when_quote_fails(self, client, db_session, stub_composer):
        _seed_local_user(db_session)

        class FailingProviders(FakeProviders):
            def quote(self, symbol: str) -> MarketQuoteSnapshot:
                raise MarketBriefCompositionError("downstream unavailable", MarketBriefReasonCode.PROVIDER_TRANSPORT_FAILURE)

        composer = FakeComposer(_assembled())
        composer.providers = FailingProviders()
        stub_composer(composer)

        response = client.get("/api/v1/investments/brief/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["market"]["spy_change"] is None
        # Hero still computes from server-owned positions
        assert body["hero"]["daily_pnl"] == pytest.approx(50.0)

    def test_unconfigured_composer_returns_503(self, client, db_session, stub_composer):
        _seed_local_user(db_session)
        stub_composer(None)

        response = client.get("/api/v1/investments/brief/summary")
        assert response.status_code == 503
        assert "Market data is not configured" in response.json()["detail"]

    def test_composition_error_returns_503(self, client, db_session, stub_composer):
        _seed_local_user(db_session)
        stub_composer(RaisingComposer())

        response = client.get("/api/v1/investments/brief/summary")
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "no_market_addressable_holdings" in detail

    def test_pulse_earnings_filtered_to_held_symbols(self, client, db_session, stub_composer, stub_pulse, make_account):
        _seed_local_user(db_session)
        account = make_account()
        db_session.add(account)
        db_session.commit()
        _seed_holding(db_session, account, "AAPL", 2000.0)

        now = datetime.now(timezone.utc)
        events = [
            EarningsEvent(symbol="AAPL", event_date=now + timedelta(days=2), source=_source("https://example.com/aapl-earn")),
            EarningsEvent(symbol="GOOGL", event_date=now + timedelta(days=3), source=_source("https://example.com/googl-earn")),
        ]
        stub_composer(FakeComposer(_assembled(news=[], earnings_events=[])))
        stub_pulse(FakePulse(events))

        response = client.get("/api/v1/investments/brief/summary")
        assert response.status_code == 200
        earnings = response.json()["earnings"]
        assert [event["symbol"] for event in earnings] == ["AAPL"]  # GOOGL filtered out

    def test_route_collected_news_from_top_holdings(self, client, db_session, stub_composer, make_account):
        _seed_local_user(db_session)
        account = make_account()
        db_session.add(account)
        db_session.commit()
        # Top holding is real and newsworthy; junk internal code returns none.
        _seed_holding(db_session, account, "AAPL", 9000.0)
        _seed_holding(db_session, account, "NON40OJJ5", 100.0)

        stub_composer(FakeComposer(_assembled(news=[], earnings_events=[])))

        response = client.get("/api/v1/investments/brief/summary")
        assert response.status_code == 200
        news = response.json()["news"]
        assert len(news) == 1
        assert news[0]["symbols"] == ["AAPL"]
        assert "Apple earnings beat" in news[0]["headline"]

    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.get("/api/v1/investments/brief/summary")
        assert response.status_code == 401


class TestBriefRefresh:
    def test_refresh_returns_same_contract(self, client, db_session, stub_composer):
        _seed_local_user(db_session)
        stub_composer(FakeComposer(_assembled()))

        response = client.post("/api/v1/investments/brief/refresh")
        assert response.status_code == 200
        body = response.json()
        assert {"hero", "market", "news", "earnings", "quality"} <= set(body.keys())
        assert body["hero"]["daily_pnl"] == pytest.approx(50.0)


class TestBriefSliceEndpoints:
    def test_news_and_earnings_endpoints(self, client, db_session, stub_composer):
        _seed_local_user(db_session)
        stub_composer(FakeComposer(_assembled()))

        news = client.get("/api/v1/investments/brief/news")
        assert news.status_code == 200
        assert len(news.json()) == 2
        assert news.json()[0]["headline"]

        earnings = client.get("/api/v1/investments/brief/earnings")
        assert earnings.status_code == 200
        assert len(earnings.json()) == 2

        alerts = client.get("/api/v1/investments/brief/alerts")
        assert alerts.status_code == 200
        assert alerts.json() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])