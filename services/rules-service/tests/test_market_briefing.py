"""Synthetic, deterministic tests for Phase 5 Slice 2 briefing rules."""
from datetime import UTC, datetime

from app.market_intelligence.briefing import (
    BriefingInput, DeterministicTemplateProvider, PositionInput, build_exposure_summary, build_portfolio_changes,
    select_relevant_news,
)
from app.market_intelligence.contracts import CompanyNewsItem, EarningsEvent, EarningsResult, Freshness, SecFilingEvent, SourceMetadata

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _source(url: str = "https://example.test/source") -> SourceMetadata:
    return SourceMetadata(provider="synthetic", source_url=url, retrieved_at=NOW, observed_at=NOW)


def test_decimal_changes_are_sorted_and_warn_on_unsafe_inputs() -> None:
    changes = build_portfolio_changes([
        PositionInput(symbol="MSFT", quantity="2", current_price="105", previous_close="100", currency="USD", source=_source()),
        PositionInput(symbol="AAPL", quantity="3", current_price="90", previous_close="100", currency="USD", source=_source()),
        PositionInput(symbol="BAD", quantity=None, current_price="10", previous_close="9", currency="USD", source=_source()),
        PositionInput(symbol="OLD", quantity="1", current_price="10", previous_close="9", currency="USD", source=_source(), freshness=Freshness.STALE),
    ])
    assert [row.symbol for row in changes.rows] == ["AAPL", "MSFT"]
    assert changes.rows[0].daily_change == "-30"
    assert changes.rows[1].daily_change == "10"
    assert changes.rows[0].contribution == "1.5"
    assert any("BAD" in warning for warning in changes.warnings)
    ambiguous = build_portfolio_changes([
        PositionInput(symbol="USD", quantity="1", current_price="10", previous_close="9", currency="USD", source=_source()),
        PositionInput(symbol="EUR", quantity="1", current_price="10", previous_close="9", currency="EUR", source=_source()),
    ])
    assert not ambiguous.rows and any("currency" in warning.lower() for warning in ambiguous.warnings)


def test_news_relevance_is_held_only_deduplicated_and_template_is_review_only() -> None:
    news = [
        CompanyNewsItem(symbol="AAPL", headline="Apple result", source=_source("https://n.test/a")),
        CompanyNewsItem(symbol="AAPL", headline="Duplicate", source=_source("https://n.test/a")),
        CompanyNewsItem(symbol="TSLA", headline="Not held", source=_source("https://n.test/t")),
    ]
    selected = select_relevant_news(news, held_symbols={"AAPL"})
    assert [item.headline for item in selected] == ["Apple result"]

    brief = DeterministicTemplateProvider().generate(BriefingInput(
        owner_id=1, portfolio_state_hash="a" * 64, universe_hash="b" * 64,
        report_window="2026-08-10", positions=[PositionInput(symbol="AAPL", currency="USD", source=_source())], news=selected, generated_at=NOW,
    ))
    assert brief.schema_version == "atlas-market-intelligence-brief/v1"
    assert [section.name for section in brief.sections] == [
        "executive_summary", "portfolio_changes", "material_holding_news", "earnings",
        "sec_filings", "catalyst_stream", "risks_and_opportunities", "actions_to_review",
        "sources", "data_quality",
    ]
    assert brief.actions[0].action.startswith("Review whether")
    assert brief.actions[0].approval_requirement == "explicit_user_approval_required"
    news_section = next(section for section in brief.sections if section.name == "material_holding_news")
    assert news_section.citations and news_section.citations[0].freshness == Freshness.FRESH


def test_sector_and_cash_require_authoritative_inputs() -> None:
    exposure = build_exposure_summary([
        PositionInput(symbol="AAPL", currency="USD", source=_source(), current_weight="0.3", sector="Technology", sector_authoritative=True),
        PositionInput(symbol="OTHER", currency="USD", source=_source(), current_weight="0.1", sector="Guess", sector_authoritative=False),
        PositionInput(symbol="CASH", currency="USD", source=_source(), is_cash=True, cash_value="10"),
    ])
    assert exposure.sector_weights == (("Technology", "0.3"), ("unknown", "0.1"))
    assert exposure.cash_value == "10"
    assert exposure.cash_currency == "USD"
    assert exposure.concentration_warning
    ambiguous_cash = build_exposure_summary([
        PositionInput(symbol="USD", currency="USD", source=_source(), is_cash=True, cash_value="10"),
        PositionInput(symbol="EUR", currency="EUR", source=_source(), is_cash=True, cash_value="10"),
    ])
    assert ambiguous_cash.cash_value is None and ambiguous_cash.cash_currency is None
    assert any("currency ambiguous" in warning.lower() for warning in ambiguous_cash.warnings)


def test_displayed_change_and_filing_claims_each_carry_citations() -> None:
    filing = SecFilingEvent(cik="320193", form="8-K", accession_number="0001-01", filing_date=NOW,
                            source=_source("https://sec.test/filing"))
    brief = DeterministicTemplateProvider().generate(BriefingInput(
        owner_id=1, portfolio_state_hash="6" * 64, universe_hash="7" * 64, report_window="2026-08-10",
        positions=[PositionInput(symbol="AAPL", quantity="1", current_price="11", previous_close="10", currency="USD", source=_source("https://quote.test/aapl"))],
        filings=[filing], held_ciks={"320193"}, generated_at=NOW,
    ))
    for name in ("portfolio_changes", "sec_filings"):
        section = next(section for section in brief.sections if section.name == name)
        assert section.claims and all(claim.citation.source_url for claim in section.claims)
        assert section.citations == tuple(claim.citation for claim in section.claims)


def test_earnings_section_is_portfolio_scoped_deduplicated_and_source_cited() -> None:
    event_source = SourceMetadata(provider="synthetic", source_url="https://earnings.test/calendar", retrieved_at=NOW)
    result_source = SourceMetadata(provider="synthetic", source_url="https://earnings.test/result", retrieved_at=NOW, observed_at=NOW)
    event = EarningsEvent(symbol="AAPL", event_date=datetime(2026, 8, 11, tzinfo=UTC), source=event_source)
    result = EarningsResult(symbol="AAPL", actual="2", estimate="1", source=result_source)
    brief = DeterministicTemplateProvider().generate(BriefingInput(
        owner_id=1, portfolio_state_hash="8" * 64, universe_hash="9" * 64, report_window="2026-08-10",
        positions=[PositionInput(symbol="AAPL", currency="USD", source=_source())],
        earnings_events=[event, event, EarningsEvent(symbol="TSLA", event_date=NOW, source=event_source)],
        earnings_results=[result, result, EarningsResult(symbol="TSLA", actual="1", estimate="1", source=result_source)], generated_at=NOW,
    ))
    section = next(section for section in brief.sections if section.name == "earnings")
    assert section.content == ("recent result: AAPL period 2026-08-10", "upcoming: AAPL earnings on 2026-08-11")
    assert len(section.claims) == len(section.citations) == 2
    assert all(claim.citation.freshness is Freshness.FRESH for claim in section.claims)
    assert all("TSLA" not in claim.text for claim in section.claims)


def test_public_generate_route_never_accepts_client_financial_facts(client, monkeypatch) -> None:
    from app.config import settings
    from app.market_intelligence.composition import TrustedMarketBriefComposer

    dangerous = {"owner_id": 999, "portfolio_state_hash": "a" * 64, "universe_hash": "b" * 64,
                 "positions": [{"symbol": "AAPL", "quantity": "999999"}], "news": [{"headline": "buy"}]}
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", False)
    disabled = client.post("/api/v1/market-briefs/generate", json=dangerous)
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    unassembled = client.post("/api/v1/market-briefs/generate", json=dangerous)
    assert disabled.status_code == unassembled.status_code == 503
    assert disabled.json()["reason_code"] == unassembled.json()["reason_code"] == "provider_configuration_missing"
    assert "server" in disabled.json()["message"].lower()
    assert "retry" in disabled.json()["recovery"].lower()


class _RecordingMarketProviders:
    """Hermetic trusted-provider double: no adapter or network is involved."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.now = NOW
        self.quote_source = _source("https://quotes.test/aapl")
        self.earnings_source = _source("https://earnings.test/aapl")

    def quote(self, symbol: str):
        self.calls.append(("quote", symbol))
        if symbol == "AAPL":
            from app.market_intelligence.contracts import MarketQuoteSnapshot
            return MarketQuoteSnapshot(symbol=symbol, currency="USD", current_price="110", previous_close="100", source=self.quote_source)
        return None

    def news(self, symbol: str):
        self.calls.append(("news", symbol))
        return [CompanyNewsItem(symbol=symbol, headline="Apple update", source=_source("https://news.test/aapl"))]

    def earnings_events(self, symbol: str):
        self.calls.append(("earnings_events", symbol))
        return [
            EarningsEvent(symbol=symbol, event_date=datetime(2026, 8, 11, tzinfo=UTC), source=self.earnings_source),
            EarningsEvent(symbol=symbol, event_date=datetime(2026, 7, 26, tzinfo=UTC), source=self.earnings_source),
            EarningsEvent(symbol=symbol, event_date=datetime(2026, 9, 10, tzinfo=UTC), source=self.earnings_source),
        ]

    def earnings_results(self, symbol: str):
        self.calls.append(("earnings_results", symbol))
        return [
            EarningsResult(symbol=symbol, actual="2", estimate="1", source=SourceMetadata(provider="synthetic", source_url="https://earnings.test/result", retrieved_at=NOW, observed_at=NOW)),
            EarningsResult(symbol=symbol, actual="1", estimate="1", source=SourceMetadata(provider="synthetic", source_url="https://earnings.test/old-result", retrieved_at=NOW, observed_at=datetime(2026, 7, 26, tzinfo=UTC))),
        ]

    def filings(self):
        self.calls.append(("filings", None))
        return []

    def profile(self, symbol: str):
        self.calls.append(("profile", symbol))
        return None

    def analyst_recommendations(self, symbol: str):
        self.calls.append(("analyst_recommendations", symbol))
        return []

    def price_target(self, symbol: str):
        self.calls.append(("price_target", symbol))
        return None

    def dividends(self, symbol: str):
        self.calls.append(("dividends", symbol))
        return []

    def filings_for_cik(self, cik: str):
        self.calls.append(("filings_for_cik", cik))
        return []


def test_generate_route_rejects_authoritative_client_fields_before_composition_or_persistence(client, db_session, monkeypatch) -> None:
    from app.config import settings
    from app.market_intelligence.composition import TrustedMarketBriefComposer
    from app.models.market_brief import MarketBrief as StoredBrief
    from app.routes.market_briefs import configure_market_brief_composer

    providers = _RecordingMarketProviders()
    configure_market_brief_composer(TrustedMarketBriefComposer(providers, now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest", "positions": [{"symbol": "AAPL"}], "owner_id": 999})
    finally:
        configure_market_brief_composer(None)
    assert response.status_code == 422
    assert response.json() == {"code": "invalid_market_brief_control"}
    assert providers.calls == []
    assert db_session.query(StoredBrief).count() == 0


def test_enabled_generation_uses_only_owner_holdings_and_cites_in_window_earnings(client, db_session, make_account, monkeypatch) -> None:
    """The route composes server-side state; body financial facts cannot alter it."""
    from app.config import settings
    from app.market_intelligence.composition import TrustedMarketBriefComposer
    from app.models import Holding, User
    from app.routes.market_briefs import configure_market_brief_composer
    from app.routes.shared import get_or_create_family_member_self, get_or_create_institution
    from app.models import Account

    owner_account = make_account(account_name="Owner brokerage", account_type="brokerage")
    owner_second_account = make_account(account_name="Owner second brokerage", account_type="brokerage")
    inactive_account = make_account(account_name="Closed brokerage", account_type="brokerage")
    inactive_account.is_active = False
    db_session.add_all((owner_account, owner_second_account, inactive_account))
    db_session.flush()
    other = User(local_user_sub="other-market-owner", email="other-market-owner@test.local", hashed_password="x")
    db_session.add(other)
    db_session.flush()
    other_account = Account(
        user_id=other.id,
        institution_id=get_or_create_institution(db_session, "Other market bank").id,
        family_member_id=get_or_create_family_member_self(db_session, other).id,
        account_name="Other brokerage", account_type="brokerage", is_active=True,
    )
    db_session.add_all((
        other_account,
        Holding(account_id=owner_account.id, symbol="aapl", quantity=2, current_value=200, type="Stock"),
        Holding(account_id=owner_second_account.id, symbol="AAPL", quantity=3, current_value=300, type="Stock"),
        Holding(account_id=inactive_account.id, symbol="MSFT", quantity=99, current_value=999, type="Stock"),
    ))
    db_session.flush()
    db_session.add(Holding(account_id=other_account.id, symbol="MSFT", quantity=99, current_value=999, type="Stock"))
    db_session.commit()

    providers = _RecordingMarketProviders()
    configure_market_brief_composer(TrustedMarketBriefComposer(providers, now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    # The browser can send only this control; all portfolio facts are read
    # from authenticated server-side state.
    control = {"report_window": "latest"}
    try:
        response = client.post("/api/v1/market-briefs/generate", json=control)
        replay = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        configure_market_brief_composer(None)

    assert response.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["brief_id"] == response.json()["brief_id"]
    from app.models.market_brief import MarketBrief as StoredBrief
    assert db_session.query(StoredBrief).filter_by(id=response.json()["brief_id"]).one().user_id != other.id
    monkeypatch.setattr(settings, "atlas_market_brief_read_api_enabled", True)
    assert client.get(f"/api/v1/market-briefs/{response.json()['brief_id']}").status_code == 200
    brief = response.json()["brief"]
    assert brief["owner_id"] != other.id
    assert "MSFT" not in str(brief)
    assert {symbol for _, symbol in providers.calls if symbol} == {"AAPL"}
    changes = next(section for section in brief["sections"] if section["name"] == "portfolio_changes")
    assert changes["content"] == ["AAPL: 50"]
    earnings = next(section for section in brief["sections"] if section["name"] == "earnings")
    # The collection window keeps the trailing four reported quarters and the
    # upcoming quarter; the older July result and September event are retained
    # (a 14-day window would have silently discarded both).
    assert earnings["content"] == [
        "recent result: AAPL period 2026-07-26",
        "recent result: AAPL period 2026-08-10",
        "upcoming: AAPL earnings on 2026-08-11",
        "upcoming: AAPL earnings on 2026-09-10",
    ]
    assert {citation["source_url"] for citation in earnings["citations"]} == {"https://earnings.test/aapl", "https://earnings.test/result", "https://earnings.test/old-result"}
    assert "SEC filings omitted: no authoritative holding-to-CIK mapping." in brief["warnings"]
    quality = next(section for section in brief["sections"] if section["name"] == "data_quality")
    assert "SEC filings omitted: no authoritative holding-to-CIK mapping." in quality["content"]


def test_generation_unavailable_for_missing_composer_or_flags_without_provider_calls(client, monkeypatch) -> None:
    from app.config import settings
    from app.market_intelligence.composition import TrustedMarketBriefComposer
    from app.routes.market_briefs import configure_market_brief_composer

    providers = _RecordingMarketProviders()
    unavailable_reason = "provider_configuration_missing"
    configure_market_brief_composer(TrustedMarketBriefComposer(providers, now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", False)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    try:
        assert client.post("/api/v1/market-briefs/generate", json={"positions": [{"symbol": "MSFT"}]}).json()["reason_code"] == unavailable_reason
        monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
        monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", False)
        assert client.post("/api/v1/market-briefs/generate", json={"positions": [{"symbol": "MSFT"}]}).json()["reason_code"] == unavailable_reason
        configure_market_brief_composer(None)
        assert client.post("/api/v1/market-briefs/generate").json()["reason_code"] == unavailable_reason
    finally:
        configure_market_brief_composer(None)
    assert providers.calls == []


def test_unsupported_symbol_generation_error_lists_omitted_symbols(client, db_session, make_account, monkeypatch) -> None:
    """When composition fails because every eligible holding is unsupported,
    the error response must name the offending symbols so the UI can show
    the user exactly which holdings to correct (not a dead "review details").
    """
    from app.config import settings
    from app.market_intelligence.composition import TrustedMarketBriefComposer
    from app.models import Holding, User
    from app.routes.market_briefs import configure_market_brief_composer
    from app.routes.shared import get_or_create_family_member_self, get_or_create_institution
    from app.models import Account

    owner_account = make_account(account_name="Owner", account_type="brokerage")
    owner_account.is_active = True
    db_session.add(owner_account)
    db_session.flush()
    db_session.add_all((
        Holding(account_id=owner_account.id, symbol="NON40OJJ2", quantity=1, current_value=100, type=None),
        Holding(account_id=owner_account.id, symbol="NON40OXLT", quantity=1, current_value=100, type=None),
    ))
    db_session.commit()

    class _RejectingProviders(_RecordingMarketProviders):
        def quote(self, symbol: str):
            self.calls.append(("quote", symbol))
            return None  # provider cannot resolve these plan codes

    configure_market_brief_composer(TrustedMarketBriefComposer(_RejectingProviders(), now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        configure_market_brief_composer(None)
    assert response.status_code == 503
    payload = response.json()
    assert payload["reason_code"] == "unsupported_symbol"
    assert set(payload["omitted_symbols"]) == {"NON40OJJ2", "NON40OXLT"}


def test_rate_limited_optional_data_stops_collection_and_aggregates_warning(client, db_session, make_account, monkeypatch) -> None:
    """Once an optional provider call is rate limited, composition fails fast:
    no further optional calls are attempted and exactly ONE aggregated warning
    is emitted instead of a per-holding/per-category flood.
    """
    from app.config import settings
    from app.market_intelligence.composition import MarketBriefCompositionError, TrustedMarketBriefComposer
    from app.market_intelligence.contracts import MarketBriefReasonCode, MarketQuoteSnapshot
    from app.models import Account, Holding
    from app.routes.market_briefs import configure_market_brief_composer

    owner_account = make_account(account_name="Owner", account_type="brokerage")
    owner_account.is_active = True
    db_session.add(owner_account)
    db_session.flush()
    db_session.add_all((
        Holding(account_id=owner_account.id, symbol="AAPL", quantity=1, current_value=100, type="Stock"),
        Holding(account_id=owner_account.id, symbol="MSFT", quantity=1, current_value=100, type="Stock"),
    ))
    db_session.commit()

    class _RateLimitedProviders(_RecordingMarketProviders):
        def quote(self, symbol: str):
            self.calls.append(("quote", symbol))
            return MarketQuoteSnapshot(symbol=symbol, currency="USD", current_price="110", previous_close="100", source=self.quote_source)

        def news(self, symbol: str):
            self.calls.append(("news", symbol))
            raise MarketBriefCompositionError("rate limited", MarketBriefReasonCode.PROVIDER_RATE_LIMITED)

    providers = _RateLimitedProviders()
    configure_market_brief_composer(TrustedMarketBriefComposer(providers, now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        configure_market_brief_composer(None)
    assert response.status_code == 201
    brief = response.json()["brief"]
    rate_warnings = [warning for warning in brief["warnings"] if "provider_rate_limited" in warning]
    assert len(rate_warnings) == 1
    assert "remaining holdings" in rate_warnings[0]
    # The first rate limit (AAPL news) stops ALL further optional collection:
    # no AAPL earnings/profile calls and no MSFT optional calls at all.
    assert ("news", "MSFT") not in providers.calls
    assert ("earnings_events", "AAPL") not in providers.calls
    assert ("profile", "AAPL") not in providers.calls
    assert ("earnings_events", "MSFT") not in providers.calls


def test_priority_news_and_earnings_survive_enrichment_rate_limit(client, db_session, make_account, monkeypatch) -> None:
    """News and earnings are collected across ALL holdings before enrichment
    extras, so a rate limit hit during the enrichment pass (profile/analyst/
    price target/dividends/filings) does not discard the earnings evidence the
    Earnings & Events tab renders.
    """
    from app.config import settings
    from app.market_intelligence.composition import MarketBriefCompositionError, TrustedMarketBriefComposer
    from app.market_intelligence.contracts import MarketBriefReasonCode, MarketQuoteSnapshot
    from app.models import Account, Holding
    from app.routes.market_briefs import configure_market_brief_composer

    owner_account = make_account(account_name="Owner", account_type="brokerage")
    owner_account.is_active = True
    db_session.add(owner_account)
    db_session.flush()
    db_session.add_all((
        Holding(account_id=owner_account.id, symbol="AAPL", quantity=1, current_value=100, type="Stock"),
        Holding(account_id=owner_account.id, symbol="MSFT", quantity=1, current_value=100, type="Stock"),
    ))
    db_session.commit()

    class _EnrichmentRateLimitedProviders(_RecordingMarketProviders):
        def quote(self, symbol: str):
            self.calls.append(("quote", symbol))
            return MarketQuoteSnapshot(symbol=symbol, currency="USD", current_price="110", previous_close="100", source=self.quote_source)

        def profile(self, symbol: str):
            self.calls.append(("profile", symbol))
            raise MarketBriefCompositionError("rate limited", MarketBriefReasonCode.PROVIDER_RATE_LIMITED)

    providers = _EnrichmentRateLimitedProviders()
    configure_market_brief_composer(TrustedMarketBriefComposer(providers, now=lambda: NOW))
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    monkeypatch.setattr(settings, "atlas_market_brief_external_provider_enabled", True)
    try:
        response = client.post("/api/v1/market-briefs/generate", json={"report_window": "latest"})
    finally:
        configure_market_brief_composer(None)
    assert response.status_code == 201
    brief = response.json()["brief"]
    packets = {packet["symbol"]: packet for packet in brief["holding_evidence"]}
    # The priority pass ran for BOTH holdings before the enrichment pass
    # tripped, so earnings/news are present for both.
    for symbol in ("AAPL", "MSFT"):
        assert packets[symbol]["news"]
        assert packets[symbol]["earnings_events"]
        assert packets[symbol]["earnings_results"]
    # The enrichment pass tripped on the first profile call and stopped there.
    assert ("profile", "MSFT") not in providers.calls
    assert ("analyst_recommendations", "AAPL") not in providers.calls
    rate_warnings = [warning for warning in brief["warnings"] if "provider_rate_limited" in warning]
    assert len(rate_warnings) == 1


def test_repository_idempotency_is_owner_scoped_and_never_mutates(db_session) -> None:
    from app.market_intelligence.brief_repository import MarketBriefRepository
    from app.models import User

    db_session.add_all([
        User(local_user_sub="brief-owner", email="brief-owner@test.local", hashed_password="x"),
        User(local_user_sub="brief-other", email="brief-other@test.local", hashed_password="x"),
    ])
    db_session.commit()
    first_owner = db_session.query(User).filter_by(local_user_sub="brief-owner").one()
    second_owner = db_session.query(User).filter_by(local_user_sub="brief-other").one()
    base = BriefingInput(owner_id=first_owner.id, portfolio_state_hash="c" * 64, universe_hash="d" * 64,
                         report_window="2026-08-10", positions=[], generated_at=NOW)
    provider = DeterministicTemplateProvider()
    repository = MarketBriefRepository(db_session)
    row, replayed = repository.get_or_create(provider.generate(base))
    duplicate, duplicate_replayed = repository.get_or_create(provider.generate(base))
    other, other_replayed = repository.get_or_create(provider.generate(base.model_copy(update={"owner_id": second_owner.id})))
    assert not replayed and duplicate_replayed and not other_replayed
    assert row.id == duplicate.id and other.id != row.id
    assert row.payload_json == duplicate.payload_json


def test_read_route_is_owner_scoped_and_hides_bad_storage(client, db_session, monkeypatch) -> None:
    from app.config import settings
    from app.market_intelligence.brief_repository import MarketBriefRepository
    from app.models import User

    monkeypatch.setattr(settings, "atlas_market_brief_read_api_enabled", True)
    owner = User(local_user_sub="alex", email="route-owner@test.local", hashed_password="x")
    other = User(local_user_sub="other", email="route-other@test.local", hashed_password="x")
    db_session.add_all((owner, other))
    db_session.commit()
    base = BriefingInput(owner_id=owner.id, portfolio_state_hash="1" * 64, universe_hash="2" * 64,
                         report_window="2026-08-10", positions=[], generated_at=NOW)
    row, _ = MarketBriefRepository(db_session).get_or_create(DeterministicTemplateProvider().generate(base))
    cross, _ = MarketBriefRepository(db_session).get_or_create(DeterministicTemplateProvider().generate(base.model_copy(update={"owner_id": other.id, "portfolio_state_hash": "3" * 64})))
    from app.models.market_brief import MarketBrief as StoredBrief
    corrupt = StoredBrief(id="00000000-0000-4000-8000-000000000999", user_id=owner.id,
                          portfolio_state_hash="4" * 64, universe_hash="5" * 64, report_window="2026-08-10",
                          schema_version="atlas-market-intelligence-brief/v1", calculation_version="market-impact/v1",
                          generated_at=NOW, payload_json='{"not":"a brief"}')
    db_session.add(corrupt)
    db_session.commit()
    assert client.get(f"/api/v1/market-briefs/{row.id}").status_code == 200
    missing = client.get("/api/v1/market-briefs/missing")
    assert client.get(f"/api/v1/market-briefs/{cross.id}").json() == missing.json() == {"code": "market_brief_not_found"}
    assert client.get(f"/api/v1/market-briefs/{cross.id}").status_code == missing.status_code == 404
    assert client.get("/api/v1/market-briefs/" + "x" * 37).status_code == 404
    assert client.get("/api/v1/market-briefs/00000000-0000-4000-8000-000000000999").json() == missing.json()
