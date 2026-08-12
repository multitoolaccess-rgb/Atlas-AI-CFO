"""Deterministic US market-session policy for bounded quote freshness.

This deliberately uses only the Python standard library. It covers regular
NYSE-style weekday sessions and the major full-day US market holidays used by
this local-first product; it does not claim to model early closes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from .contracts import Freshness, PriceBasis

EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
LIVE_QUOTE_MAX_AGE = timedelta(minutes=15)
MAX_PRIOR_CLOSE_SESSIONS = 3


class MarketSession(StrEnum):
    REGULAR = "regular"
    PREMARKET = "premarket"
    AFTER_HOURS = "after_hours"
    CLOSED = "closed"


@dataclass(frozen=True)
class QuoteClassification:
    freshness: Freshness
    price_basis: PriceBasis
    session: MarketSession
    reason_code: str | None = None


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    actual = date(year, month, day)
    if actual.weekday() == 5:  # Saturday -> Friday
        return actual - timedelta(days=1)
    if actual.weekday() == 6:  # Sunday -> Monday
        return actual + timedelta(days=1)
    return actual


def _easter_sunday(year: int) -> date:
    """Gregorian computus, sufficient for the bounded modern calendar."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def us_market_holidays(year: int) -> frozenset[date]:
    fixed = {
        _observed_fixed_holiday(year, 1, 1),
        _observed_fixed_holiday(year, 6, 19),
        _observed_fixed_holiday(year, 7, 4),
        _observed_fixed_holiday(year, 12, 25),
    }
    new_year_previous = _observed_fixed_holiday(year - 1, 1, 1)
    new_year_next = _observed_fixed_holiday(year + 1, 1, 1)
    if new_year_previous.year == year:
        fixed.add(new_year_previous)
    if new_year_next.year == year:
        fixed.add(new_year_next)
    easter = _easter_sunday(year)
    good_friday = easter - timedelta(days=2)
    mlk = date(year, 1, 1)
    while mlk.weekday() != 0:
        mlk += timedelta(days=1)
    mlk += timedelta(days=14)
    presidents = date(year, 2, 1)
    while presidents.weekday() != 0:
        presidents += timedelta(days=1)
    presidents += timedelta(days=14)
    memorial = date(year, 5, 31)
    while memorial.weekday() != 0:
        memorial -= timedelta(days=1)
    labor = date(year, 9, 1)
    while labor.weekday() != 0:
        labor += timedelta(days=1)
    thanksgiving = date(year, 11, 1)
    while thanksgiving.weekday() != 3:
        thanksgiving += timedelta(days=1)
    thanksgiving += timedelta(days=21)
    return frozenset((*fixed, good_friday, mlk, presidents, memorial, labor, thanksgiving))


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in us_market_holidays(day.year)


def market_session_at(now: datetime) -> MarketSession:
    local = now.astimezone(EASTERN)
    if not is_trading_day(local.date()):
        return MarketSession.CLOSED
    if local.time() < MARKET_OPEN:
        return MarketSession.PREMARKET
    if local.time() < MARKET_CLOSE:
        return MarketSession.REGULAR
    return MarketSession.AFTER_HOURS


def latest_completed_session(now: datetime) -> date:
    local = now.astimezone(EASTERN)
    cursor = local.date()
    if market_session_at(now) in {MarketSession.PREMARKET, MarketSession.REGULAR}:
        cursor -= timedelta(days=1)
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def _prior_close_session(observed_at: datetime) -> date | None:
    local = observed_at.astimezone(EASTERN)
    if not is_trading_day(local.date()) or local.time() < MARKET_CLOSE:
        return None
    return local.date()


def _session_distance(observed_session: date, latest_session: date) -> int | None:
    if observed_session > latest_session:
        return None
    distance = 0
    cursor = observed_session
    while cursor < latest_session:
        cursor += timedelta(days=1)
        if is_trading_day(cursor):
            distance += 1
            if distance > MAX_PRIOR_CLOSE_SESSIONS:
                return distance
    return distance


def classify_quote(*, observed_at: datetime | None, now: datetime) -> QuoteClassification:
    """Classify a quote without using browser time or an external calendar."""
    session = market_session_at(now)
    if observed_at is None or observed_at.tzinfo is None:
        return QuoteClassification(Freshness.UNKNOWN, PriceBasis.UNUSABLE, session, "invalid_quote")
    if observed_at > now:
        return QuoteClassification(Freshness.UNKNOWN, PriceBasis.UNUSABLE, session, "invalid_quote")

    local_now = now.astimezone(EASTERN)
    local_observed = observed_at.astimezone(EASTERN)
    if session is MarketSession.REGULAR:
        age = now - observed_at
        if (
            local_observed.date() == local_now.date()
            and MARKET_OPEN <= local_observed.time() < MARKET_CLOSE
            and timedelta(0) <= age <= LIVE_QUOTE_MAX_AGE
        ):
            return QuoteClassification(Freshness.FRESH, PriceBasis.LIVE, session)
        return QuoteClassification(Freshness.STALE, PriceBasis.UNUSABLE, session, "live_quote_stale")

    observed_session = _prior_close_session(observed_at)
    if observed_session is not None:
        latest = latest_completed_session(now)
        distance = _session_distance(observed_session, latest)
        if distance is not None and distance <= MAX_PRIOR_CLOSE_SESSIONS:
            return QuoteClassification(Freshness.FRESH, PriceBasis.PRIOR_CLOSE, session, "prior_close_accepted")
    return QuoteClassification(Freshness.STALE, PriceBasis.UNUSABLE, session, "prior_close_too_old")
