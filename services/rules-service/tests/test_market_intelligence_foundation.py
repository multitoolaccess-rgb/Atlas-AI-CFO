"""Hermetic contract tests for the Phase 5 research-data foundation."""
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from app.market_intelligence import (
    BoundedCache,
    CompanyNewsItem,
    EndpointClass,
    FinnhubAdapter,
    MarketQuoteSnapshot,
    PortfolioHolding,
    PortfolioUniverse,
    ProviderConfigurationError,
    SecAdapter,
    SourceMetadata,
    SyntheticMarketTransport,
    UsageLedger,
)
from app.market_intelligence.contracts import Freshness


NOW = datetime(2026, 8, 10, 16, 0, tzinfo=UTC)


def test_portfolio_universe_is_sorted_deduplicated_and_non_sensitive() -> None:
    universe = PortfolioUniverse.from_holdings([
        PortfolioHolding(symbol="msft", instrument_type="equity", quantity="2", value="100"),
        PortfolioHolding(symbol="AAPL", instrument_type="equity", quantity="1", value="50"),
        PortfolioHolding(symbol="MSFT", instrument_type="equity", quantity="9", value="999"),
        PortfolioHolding(symbol=None, instrument_type="cash", quantity="1", value="5"),
    ])

    assert [holding.symbol for holding in universe.holdings] == ["AAPL", "MSFT"]
    assert len(universe.universe_hash) == 64
    assert "account" not in universe.model_dump_json().lower()


def test_contracts_forbid_unknown_fields_and_bound_untrusted_text() -> None:
    with pytest.raises(ValidationError):
        SourceMetadata(provider="finnhub", source_url="https://example.test", retrieved_at=NOW, leaked="no")

    quote = MarketQuoteSnapshot(
        symbol="aapl", currency="USD", current_price="12.34", previous_close="11.00",
        source=SourceMetadata(provider="finnhub", source_url="https://example.test", retrieved_at=NOW),
    )
    assert quote.symbol == "AAPL"


@pytest.mark.parametrize("url", [
    "https://user:pass@example.test/report",
    "https://example.test/report?api_key=secret",
    "https://example.test/report?access-token=secret",
    "https://example.test/report?auth_token=secret",
    "https://example.test/report?client_secret=secret",
    "https://example.test/report?authorization=secret",
    "https://example.test/report#credential=secret",
])
def test_source_metadata_rejects_url_credentials(url: str) -> None:
    with pytest.raises(ValidationError, match="credential-free"):
        SourceMetadata(provider="finnhub", source_url=url, retrieved_at=NOW)


def test_control_only_news_headline_is_rejected_after_sanitization() -> None:
    with pytest.raises(ValidationError, match="visible text"):
        CompanyNewsItem(
            symbol="AAPL", headline="\x00\n\t", source=SourceMetadata(
                provider="finnhub", source_url="https://example.test", retrieved_at=NOW,
            ),
        )


def test_cache_is_bounded_and_usage_never_records_sensitive_values() -> None:
    cache = BoundedCache[str](max_entries=1, clock=lambda: 1.0)
    cache.put("one", "value", ttl_seconds=60)
    cache.put("two", "other", ttl_seconds=60)
    assert cache.get("one") is None
    assert cache.get("two") == "other"

    ledger = UsageLedger(now=lambda: NOW)
    ledger.record("finnhub", EndpointClass.QUOTE, cache_hit=False)
    assert ledger.records[0].model_dump() == {
        "provider": "finnhub", "endpoint_class": "quote", "cache_hit": False,
        "count": 1, "period": "2026-08",
    }


def test_finnhub_paid_or_disabled_requests_fail_without_network() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=False, transport=httpx.MockTransport(handler), now=lambda: NOW)
    result = adapter.quote("AAPL")
    assert result.failure and result.failure.failure_class == "disabled"
    assert called is False

    enabled = FinnhubAdapter(api_key="synthetic-key", enabled=True, paid_endpoints={EndpointClass.QUOTE}, transport=httpx.MockTransport(handler), now=lambda: NOW)
    result = enabled.quote("AAPL")
    assert result.failure and result.failure.failure_class == "paid_endpoint"
    assert called is False


def test_finnhub_normalizes_cache_and_retries_transient_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["token"] == "synthetic-key"
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"c": 101.5, "pc": 100, "t": 1_786_032_000})

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW, sleep=lambda _: None)
    first = adapter.quote("aapl")
    second = adapter.quote("AAPL")
    assert first.value and first.value.current_price == "101.5"
    assert second.value and second.cache_hit is True
    assert calls == 2


@pytest.mark.parametrize(("timestamp", "expected"), [
    (int(NOW.timestamp()), Freshness.FRESH),
    (int((NOW.replace(hour=15, minute=44)).timestamp()), Freshness.STALE),
])
def test_finnhub_quote_freshness_uses_market_timestamp(timestamp, expected) -> None:
    payload = {"c": 101.5, "pc": 100, "t": timestamp}
    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=SyntheticMarketTransport({"/api/v1/quote": payload}), now=lambda: NOW)
    result = adapter.quote("AAPL")
    assert result.value and result.value.source.freshness is expected


def test_finnhub_missing_quote_timestamp_is_invalid() -> None:
    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=SyntheticMarketTransport({"/api/v1/quote": {"c": 101.5, "pc": 100}}), now=lambda: NOW)
    result = adapter.quote("AAPL")
    assert result.failure and result.failure.failure_class == "invalid_quote"


def test_synthetic_transport_never_uses_network() -> None:
    adapter = FinnhubAdapter(
        api_key="synthetic-key", enabled=True,
        transport=SyntheticMarketTransport({"/api/v1/quote": {"c": 12, "pc": 11, "t": 1_786_032_000}}),
        now=lambda: NOW,
    )
    assert adapter.quote("AAPL").value is not None


def test_finnhub_never_exceeds_48_actual_calls_per_minute() -> None:
    adapter = FinnhubAdapter(
        api_key="synthetic-key", enabled=True,
        transport=SyntheticMarketTransport({"/api/v1/quote": {"c": 12, "pc": 11, "t": 1_786_032_000}}),
        now=lambda: NOW,
    )
    for index in range(48):
        assert adapter.quote(f"A{index}").value is not None
    result = adapter.quote("LAST")
    assert result.failure and result.failure.failure_class == "rate_limited"


def test_finnhub_rate_limit_429_triggers_cooldown_without_rehitting_network() -> None:
    calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        return httpx.Response(429, json={"error": "Too Many Requests"})

    adapter = FinnhubAdapter(
        api_key="synthetic-key", enabled=True,
        transport=httpx.MockTransport(handler), now=lambda: NOW,
        clock=lambda: 100.0,
    )
    first = adapter.company_news("AAPL", from_date="2026-08-01", to_date="2026-08-10")
    assert first.failure and first.failure.failure_class == "rate_limited"
    # The 429 armed the cooldown; the next call must fail locally without
    # any network attempt (same frozen clock keeps the cooldown active).
    second = adapter.earnings_calendar("AAPL")
    assert second.failure and second.failure.failure_class == "rate_limited"
    assert sum(calls.values()) == 1


def test_finnhub_normalized_records_are_deduplicated_and_cached() -> None:
    calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        if path.endswith("company-news"):
            return httpx.Response(200, json=[
                {"headline": "A\x00 story", "summary": "safe", "source": "Wire", "url": "https://news.test/a", "datetime": 1_786_032_000},
                {"headline": "Same story", "summary": "safe", "source": "Wire", "url": "https://news.test/a", "datetime": 1_786_032_000},
            ])
        if path.endswith("calendar/earnings"):
            return httpx.Response(200, json={"earningsCalendar": [
                {"symbol": "AAPL", "date": "2026-08-11"},
                {"symbol": "AAPL", "date": "2026-08-11"},
            ]})
        return httpx.Response(200, json=[
            {"actual": 2, "estimate": 1, "period": "2026-06-30"},
            {"actual": 2, "estimate": 1, "period": "2026-06-30"},
        ])

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    news = adapter.company_news("AAPL", from_date="2026-08-01", to_date="2026-08-10")
    calendar = adapter.earnings_calendar("AAPL")
    surprises = adapter.earnings_surprises("AAPL")
    assert news.value and len(news.value) == 1 and "\x00" not in news.value[0].headline
    assert calendar.value and len(calendar.value) == 1
    assert surprises.value and len(surprises.value) == 1
    assert adapter.company_news("AAPL", from_date="2026-08-01", to_date="2026-08-10").cache_hit
    assert adapter.earnings_calendar("AAPL").cache_hit
    assert adapter.earnings_surprises("AAPL").cache_hit
    assert all(count == 1 for count in calls.values())


def test_finnhub_earnings_calendar_sends_bounded_from_to_dates() -> None:
    """The earnings calendar is requested with an explicit from/to window.

    Without these bounds the free tier returns an empty payload even when
    earnings are scheduled, so scheduled events never reach the brief.
    """
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["from"] = request.url.params.get("from")
        captured["to"] = request.url.params.get("to")
        return httpx.Response(200, json={"earningsCalendar": [{"symbol": "AAPL", "date": "2026-09-05"}]})

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    result = adapter.earnings_calendar("AAPL")
    assert result.value is not None
    # NOW is 2026-08-10 → window is 2026-07-27 .. 2026-11-08.
    assert captured["from"] == "2026-07-27"
    assert captured["to"] == "2026-11-08"


def test_finnhub_company_profile_resolves_bounded_company_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cik": "0000320193", "name": "Apple Inc", "exchange": "NASDAQ", "finnhubIndustry": "Technology"})

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    result = adapter.company_profile("AAPL")
    assert result.value is not None
    assert result.value.cik == "320193"
    assert result.value.company_name == "Apple Inc"
    assert result.value.exchange == "NASDAQ"
    assert result.value.sector == "Technology"
    assert adapter.company_profile("AAPL").cache_hit


def test_finnhub_analyst_recommendation_and_price_target_are_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("stock/recommendation"):
            return httpx.Response(200, json=[
                {"period": "2026-08", "strongBuy": 12, "buy": 18, "hold": 7, "sell": 1, "strongSell": 0},
                {"period": "2026-08", "strongBuy": 99, "buy": 99, "hold": 99, "sell": 99, "strongSell": 99},
                {"period": "2026-07", "strongBuy": 10, "buy": 15, "hold": 9, "sell": 2, "strongSell": 1},
            ])
        return httpx.Response(200, json={"targetHigh": 300.0, "targetLow": 150.0, "targetMean": 220.0, "targetMedian": 230.0})

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    recs = adapter.analyst_recommendation("AAPL")
    target = adapter.price_target("AAPL")
    assert recs.value and len(recs.value) == 2  # deduplicated by period
    assert recs.value[0].strong_buy == 12
    assert target.value and target.value.target_mean == "220"
    assert adapter.analyst_recommendation("AAPL").cache_hit
    assert adapter.price_target("AAPL").cache_hit


def test_finnhub_price_target_soft_fails_on_free_tier_restriction() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Forbidden"})

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    result = adapter.price_target("BRK.B")
    # A free-tier 403 on price-target is a per-ticker restriction: the brief
    # continues with an empty target rather than failing the holding.
    assert result.value is not None and result.value.target_mean is None


def test_finnhub_dividends_are_normalized_and_cached() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"symbol": "AAPL", "exDate": "2026-08-14", "declaredDate": "2026-08-01", "amount": 0.25},
            {"symbol": "AAPL", "exDate": "2026-08-14", "amount": 0.25},
        ])

    adapter = FinnhubAdapter(api_key="synthetic-key", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    events = adapter.dividends("AAPL")
    assert events.value and len(events.value) == 1
    assert events.value[0].amount == "0.25"
    assert events.value[0].ex_date is not None
    assert adapter.dividends("AAPL").cache_hit


def test_sec_requires_identifying_user_agent_and_normalizes_submission() -> None:
    with pytest.raises(ProviderConfigurationError):
        SecAdapter(user_agent="", enabled=True)
    with pytest.raises(ProviderConfigurationError):
        SecAdapter(user_agent="x", enabled=True)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "Atlas test contact@example.test"
        return httpx.Response(200, json={"filings": {"recent": {
            "accessionNumber": ["0001-01"], "form": ["8-K"], "filingDate": ["2026-08-09"],
            "primaryDocument": ["report.htm"], "items": ["2.02"],
        }}})

    adapter = SecAdapter(user_agent="Atlas test contact@example.test", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    result = adapter.submissions("320193")
    assert result.value and result.value[0].form == "8-K"
    assert result.value[0].accession_number == "0001-01"


def test_sec_invalid_cik_fails_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    adapter = SecAdapter(user_agent="Atlas test contact@example.test", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    result = adapter.submissions("320193/../../etc")
    assert result.failure and result.failure.failure_class == "invalid_payload"
    too_long = adapter.company_facts("00000000001")
    assert too_long.failure and too_long.failure.failure_class == "invalid_payload"
    assert calls == 0


def test_sec_per_second_cap_includes_retries() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 200, json={"filings": {"recent": {
            "accessionNumber": [], "form": [], "filingDate": [], "primaryDocument": [],
        }}})

    adapter = SecAdapter(
        user_agent="Atlas test contact@example.test", enabled=True,
        transport=httpx.MockTransport(handler), now=lambda: NOW, sleep=lambda _: None,
        clock=lambda: 1.0,
    )
    # The first logical request takes two actual calls (503 then retry), then
    # three more distinct CIKs consume the remaining per-second budget.
    assert adapter.submissions("1").value == []
    for cik in ("2", "3", "4"):
        assert adapter.submissions(cik).value == []
    result = adapter.submissions("5")
    assert result.failure and result.failure.failure_class == "rate_limited"
    assert calls == 5


def test_sec_normalized_records_are_deduplicated_and_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if "/submissions/" in request.url.path:
            return httpx.Response(200, json={"filings": {"recent": {
                "accessionNumber": ["0001-01", "0001-01"], "form": ["8-K", "8-K"],
                "filingDate": ["2026-08-09", "2026-08-09"], "primaryDocument": ["report.htm", "report.htm"],
            }}})
        return httpx.Response(200, json={"facts": {"us-gaap": {"Revenue": {"units": {"USD": [
            {"val": 100, "filed": "2026-08-09"}, {"val": 100, "filed": "2026-08-09"},
        ]}}}}})

    adapter = SecAdapter(user_agent="Atlas test contact@example.test", enabled=True, transport=httpx.MockTransport(handler), now=lambda: NOW)
    filings = adapter.submissions("320193")
    facts = adapter.company_facts("320193")
    assert filings.value and len(filings.value) == 1
    assert facts.value and len(facts.value) == 1
    assert adapter.submissions("320193").cache_hit
    assert adapter.company_facts("320193").cache_hit
    assert calls == 2
