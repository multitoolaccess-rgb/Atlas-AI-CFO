"""Synthetic, deterministic tests for Phase 5 Slice 2 briefing rules."""
from datetime import UTC, datetime

from app.market_intelligence.briefing import (
    BriefingInput, DeterministicTemplateProvider, PositionInput, build_exposure_summary, build_portfolio_changes,
    select_relevant_news,
)
from app.market_intelligence.contracts import CompanyNewsItem, Freshness, SecFilingEvent, SourceMetadata

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _source(url: str = "https://example.test/source") -> SourceMetadata:
    return SourceMetadata(provider="synthetic", source_url=url, retrieved_at=NOW)


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
        "sec_filings", "risks_and_opportunities", "actions_to_review", "sources", "data_quality",
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


def test_public_generate_route_never_accepts_client_financial_facts(client, monkeypatch) -> None:
    from app.config import settings

    dangerous = {"owner_id": 999, "portfolio_state_hash": "a" * 64, "universe_hash": "b" * 64,
                 "positions": [{"symbol": "AAPL", "quantity": "999999"}], "news": [{"headline": "buy"}]}
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", False)
    disabled = client.post("/api/v1/market-briefs/generate", json=dangerous)
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", True)
    unassembled = client.post("/api/v1/market-briefs/generate", json=dangerous)
    assert disabled.status_code == unassembled.status_code == 503
    assert disabled.json() == unassembled.json() == {"code": "market_brief_unavailable", "message": "Market briefing is currently disabled."}


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
