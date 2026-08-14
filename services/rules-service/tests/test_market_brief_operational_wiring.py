"""Hermetic operational wiring checks; no provider request is permitted."""
from __future__ import annotations

from types import SimpleNamespace

from app.market_intelligence.composition import (
    MarketBriefCompositionError,
    TrustedMarketBriefComposer,
    build_operational_market_brief_composer,
)


def _settings(**overrides):
    base = {
        "atlas_market_brief_generation_enabled": False,
        "atlas_market_brief_external_provider_enabled": False,
        "finnhub_api_key": None,
        "sec_user_agent": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_operational_composer_is_not_wired_without_all_server_owned_controls() -> None:
    assert build_operational_market_brief_composer(_settings()) is None
    assert build_operational_market_brief_composer(_settings(atlas_market_brief_generation_enabled=True, atlas_market_brief_external_provider_enabled=True)) is None
    assert build_operational_market_brief_composer(_settings(atlas_market_brief_generation_enabled=True, atlas_market_brief_external_provider_enabled=True, finnhub_api_key="local-only")) is None
    # Construction validates configuration only; it does not contact a provider.
    assert build_operational_market_brief_composer(_settings(atlas_market_brief_generation_enabled=True, atlas_market_brief_external_provider_enabled=True, finnhub_api_key="local-only", sec_user_agent="Atlas local operator ops@example.test")) is not None


def test_composer_rejects_empty_server_side_portfolio(client, db_session) -> None:
    # ``client`` resets the DB first so holdings seeded by an earlier
    # test in the same process cannot make this portfolio appear non-empty.
    composer = TrustedMarketBriefComposer(SimpleNamespace())
    try:
        composer.assemble(db_session, owner_id=1, report_window="latest")
    except MarketBriefCompositionError as error:
        assert "No active" in str(error)
    else:
        raise AssertionError("empty portfolio must fail closed")


def test_startup_wiring_replaces_a_prior_composer_with_fail_closed_configuration(monkeypatch) -> None:
    """A warm process cannot retain a composer after configuration is withdrawn."""
    from app.routes.market_briefs import configure_market_brief_composer
    import app.routes.market_briefs as routes

    configure_market_brief_composer(TrustedMarketBriefComposer(SimpleNamespace()))
    try:
        configure_market_brief_composer(build_operational_market_brief_composer(_settings()))
        assert routes._composer is None
    finally:
        configure_market_brief_composer(None)
