from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from app.market_intelligence.adapters import FinnhubAdapter
from app.market_intelligence.contracts import FailureClass, Freshness, PriceBasis
from app.market_intelligence.market_calendar import (
    MarketSession,
    classify_quote,
    is_trading_day,
    latest_completed_session,
    us_market_holidays,
)


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_regular_session_requires_bounded_live_quote() -> None:
    now = utc(2026, 8, 11, 15, 0)  # 11:00 America/New_York
    fresh = classify_quote(observed_at=utc(2026, 8, 11, 14, 50), now=now)
    stale = classify_quote(observed_at=utc(2026, 8, 11, 14, 44), now=now)
    assert fresh == type(fresh)(Freshness.FRESH, PriceBasis.LIVE, MarketSession.REGULAR)
    assert stale.freshness is Freshness.STALE
    assert stale.price_basis is PriceBasis.UNUSABLE
    assert stale.reason_code == "live_quote_stale"


def test_premarket_after_close_weekend_and_holiday_accept_prior_close() -> None:
    prior_close = utc(2026, 8, 10, 20, 0)
    premarket = classify_quote(observed_at=prior_close, now=utc(2026, 8, 11, 13, 0))
    after_close = classify_quote(observed_at=utc(2026, 8, 11, 20, 0), now=utc(2026, 8, 11, 21, 0))
    weekend = classify_quote(observed_at=utc(2026, 8, 14, 20, 0), now=utc(2026, 8, 15, 15, 0))
    holiday = classify_quote(observed_at=utc(2026, 9, 4, 20, 0), now=utc(2026, 9, 7, 15, 0))
    assert all(item.freshness is Freshness.FRESH for item in (premarket, after_close, weekend, holiday))
    assert all(item.price_basis is PriceBasis.PRIOR_CLOSE for item in (premarket, after_close, weekend, holiday))
    assert all(item.reason_code == "prior_close_accepted" for item in (premarket, after_close, weekend, holiday))


def test_known_holidays_and_long_weekend_session_bound_are_deterministic() -> None:
    assert not is_trading_day(date(2026, 9, 7))
    assert date(2026, 9, 7) in us_market_holidays(2026)
    assert latest_completed_session(utc(2026, 9, 7, 15, 0)).isoformat() == "2026-09-04"
    accepted = classify_quote(observed_at=utc(2026, 9, 3, 20, 0), now=utc(2026, 9, 7, 15, 0))
    too_old = classify_quote(observed_at=utc(2026, 8, 28, 20, 0), now=utc(2026, 9, 7, 15, 0))
    assert accepted.price_basis is PriceBasis.PRIOR_CLOSE
    assert too_old.freshness is Freshness.STALE
    assert too_old.reason_code == "prior_close_too_old"


@pytest.mark.parametrize(
    "observed_at",
    [None, utc(2026, 8, 11, 16, 0) + timedelta(minutes=1), utc(2026, 8, 10, 19, 59)],
)
def test_missing_future_or_non_close_timestamp_fails_closed(observed_at: datetime | None) -> None:
    result = classify_quote(observed_at=observed_at, now=utc(2026, 8, 11, 15, 0))
    assert result.price_basis is PriceBasis.UNUSABLE
    assert result.reason_code == "invalid_quote" if observed_at is None or observed_at > utc(2026, 8, 11, 15, 0) else result.reason_code == "live_quote_stale"


def test_adapter_maps_auth_invalid_and_unsupported_quote_failures() -> None:
    def auth_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    auth = FinnhubAdapter(
        api_key="synthetic-key",
        enabled=True,
        transport=httpx.MockTransport(auth_handler),
        now=lambda: utc(2026, 8, 11, 15, 0),
    )
    assert auth.quote("AAPL").failure.failure_class is FailureClass.AUTHENTICATION_FAILED

    def invalid_handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["symbol"] == "BAD":
            return httpx.Response(200, json={"c": 0, "pc": 0, "t": int(utc(2026, 8, 11, 14, 59).timestamp())})
        return httpx.Response(200, json={"c": -1, "pc": 100, "t": int(utc(2026, 8, 11, 14, 59).timestamp())})

    adapter = FinnhubAdapter(
        api_key="synthetic-key",
        enabled=True,
        transport=httpx.MockTransport(invalid_handler),
        now=lambda: utc(2026, 8, 11, 15, 0),
    )
    assert adapter.quote("BAD").failure.failure_class is FailureClass.NOT_FOUND
    assert adapter.quote("NEG").failure.failure_class is FailureClass.INVALID_QUOTE
