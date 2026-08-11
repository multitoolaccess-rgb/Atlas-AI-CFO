"""Server-only Finnhub Free and SEC adapters with bounded failure behavior."""
from __future__ import annotations

import time
import re
from datetime import UTC, datetime
from typing import Any, Callable, Generic, TypeVar

import httpx

from .contracts import (
    CompanyNewsItem, EarningsEvent, EarningsResult, FailureClass, MarketQuoteSnapshot,
    NormalizedProviderFailure, ProviderResult, SecCompanyFact, SecFilingEvent, SourceMetadata, normalize_cik,
)
from .controls import BoundedCache, EndpointClass, PerSecondPacer, RateLimitExceeded, SlidingWindowPacer, UsageLedger, deduplicate_records

T = TypeVar("T")


class ProviderConfigurationError(ValueError):
    pass


class _Adapter:
    def __init__(self, provider: str, *, enabled: bool, transport: httpx.BaseTransport | None,
                 now: Callable[[], datetime] | None, sleep: Callable[[float], None] | None,
                 calls_per_minute: int, calls_per_second: int | None = None,
                 clock: Callable[[], float] | None = None,
                 paid_endpoints: set[EndpointClass] | None = None) -> None:
        self.provider, self.enabled = provider, enabled
        self._now = now or (lambda: datetime.now(UTC))
        self._sleep = sleep or time.sleep
        self._transport = transport
        self._paid_endpoints = paid_endpoints or set()
        self._pacer = SlidingWindowPacer(calls_per_minute, clock=clock)
        self._second_pacer = PerSecondPacer(calls_per_second, clock=clock) if calls_per_second else None
        self.cache: BoundedCache[Any] = BoundedCache(max_entries=128)
        self.usage = UsageLedger(now=self._now)

    def _failure(self, endpoint: EndpointClass, failure_class: FailureClass, message: str, *, retryable: bool = False) -> ProviderResult[Any]:
        self.usage.record(self.provider, endpoint, cache_hit=False)
        return ProviderResult(failure=NormalizedProviderFailure(provider=self.provider, endpoint_class=endpoint.value, failure_class=failure_class, occurred_at=self._now(), retryable=retryable, message=message))

    def _permitted(self, endpoint: EndpointClass) -> ProviderResult[Any] | None:
        if not self.enabled:
            return self._failure(endpoint, FailureClass.DISABLED, "External provider access is disabled.")
        if endpoint in self._paid_endpoints:
            return self._failure(endpoint, FailureClass.PAID_ENDPOINT, "Endpoint is marked paid and is rejected.")
        return None

    def _request(self, endpoint: EndpointClass, url: str, *, params: dict[str, str] | None = None,
                 headers: dict[str, str] | None = None) -> tuple[dict[str, Any] | list[Any] | None, ProviderResult[Any] | None]:
        # Two retries, only transport/5xx; clients are closed every call and
        # timeout is deliberately short so a briefing cannot hang indefinitely.
        for attempt in range(3):
            try:
                # A retry is a real upstream call and must consume quota too.
                if self._second_pacer:
                    self._second_pacer.acquire()
                self._pacer.acquire()
            except RateLimitExceeded:
                return None, self._failure(endpoint, FailureClass.RATE_LIMITED, "Provider pacing ceiling reached.")
            try:
                with httpx.Client(transport=self._transport, timeout=httpx.Timeout(3.0, connect=1.0)) as client:
                    response = client.get(url, params=params, headers=headers)
            except httpx.TimeoutException:
                if attempt < 2:
                    self._sleep(0.05 * (attempt + 1))
                    continue
                return None, self._failure(endpoint, FailureClass.TIMEOUT, "Provider request timed out.", retryable=True)
            except httpx.HTTPError:
                if attempt < 2:
                    self._sleep(0.05 * (attempt + 1))
                    continue
                return None, self._failure(endpoint, FailureClass.UPSTREAM, "Provider transport failed.", retryable=True)
            if response.status_code == 404:
                return None, self._failure(endpoint, FailureClass.NOT_FOUND, "Provider record was not found.")
            if response.status_code == 429:
                return None, self._failure(endpoint, FailureClass.RATE_LIMITED, "Provider rate limited the request.", retryable=True)
            if response.status_code >= 500:
                if attempt < 2:
                    self._sleep(0.05 * (attempt + 1))
                    continue
                return None, self._failure(endpoint, FailureClass.UPSTREAM, "Provider returned a server error.", retryable=True)
            if response.status_code != 200:
                return None, self._failure(endpoint, FailureClass.UPSTREAM, "Provider returned an unavailable response.")
            try:
                payload = response.json()
            except ValueError:
                return None, self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "Provider returned invalid JSON.")
            if not isinstance(payload, (dict, list)):
                return None, self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "Provider returned an invalid payload.")
            return payload, None
        raise AssertionError("unreachable")


class FinnhubAdapter(_Adapter):
    """Only Phase-5 confirmed-Free endpoints are exposed by this adapter."""
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, *, api_key: str | None, enabled: bool, transport: httpx.BaseTransport | None = None,
                 now: Callable[[], datetime] | None = None, sleep: Callable[[float], None] | None = None,
                 clock: Callable[[], float] | None = None,
                 paid_endpoints: set[EndpointClass] | None = None) -> None:
        super().__init__("finnhub", enabled=enabled, transport=transport, now=now, sleep=sleep,
                         calls_per_minute=48, clock=clock, paid_endpoints=paid_endpoints)
        self._api_key = (api_key or "").strip()

    def quote(self, symbol: str) -> ProviderResult[MarketQuoteSnapshot]:
        endpoint = EndpointClass.QUOTE
        blocked = self._permitted(endpoint)
        if blocked:
            return blocked
        if not self._api_key:
            return self._failure(endpoint, FailureClass.UNCONFIGURED, "Finnhub API key is not configured.")
        symbol = symbol.strip().upper()
        key = f"quote:{symbol}"
        cached = self.cache.get(key)
        if cached is not None:
            self.usage.record(self.provider, endpoint, cache_hit=True)
            return ProviderResult(value=cached, cache_hit=True)
        payload, failure = self._request(endpoint, f"{self.BASE_URL}/quote", params={"symbol": symbol, "token": self._api_key})
        if failure:
            return failure
        try:
            assert isinstance(payload, dict)
            source = SourceMetadata(provider=self.provider, source_url=f"{self.BASE_URL}/quote?symbol={symbol}", retrieved_at=self._now(), observed_at=datetime.fromtimestamp(int(payload["t"]), UTC) if payload.get("t") else None)
            quote = MarketQuoteSnapshot(symbol=symbol, currency="USD", current_price=str(payload["c"]), previous_close=str(payload["pc"]) if payload.get("pc") is not None else None, source=source)
        except (KeyError, TypeError, ValueError):
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "Finnhub quote payload was invalid.")
        self.cache.put(key, quote, ttl_seconds=60)
        self.usage.record(self.provider, endpoint, cache_hit=False)
        return ProviderResult(value=quote)

    def company_news(self, symbol: str, *, from_date: str, to_date: str) -> ProviderResult[list[CompanyNewsItem]]:
        endpoint = EndpointClass.COMPANY_NEWS
        blocked = self._permitted(endpoint)
        if blocked:
            return blocked
        if not self._api_key:
            return self._failure(endpoint, FailureClass.UNCONFIGURED, "Finnhub API key is not configured.")
        symbol = symbol.strip().upper()
        key = f"news:{symbol}:{from_date}:{to_date}"
        cached = self.cache.get(key)
        if cached is not None:
            self.usage.record(self.provider, endpoint, cache_hit=True)
            return ProviderResult(value=cached, cache_hit=True)
        payload, failure = self._request(endpoint, f"{self.BASE_URL}/company-news", params={"symbol": symbol, "from": from_date, "to": to_date, "token": self._api_key})
        if failure:
            return failure
        try:
            assert isinstance(payload, list)
            items = [CompanyNewsItem(symbol=symbol, headline=str(row["headline"]), summary=str(row["summary"]) if row.get("summary") else None, publisher=str(row["source"]) if row.get("source") else None, source=SourceMetadata(provider=self.provider, source_url=str(row["url"]), retrieved_at=self._now(), published_at=datetime.fromtimestamp(int(row["datetime"]), UTC) if row.get("datetime") else None)) for row in payload[:50] if isinstance(row, dict)]
            items = deduplicate_records(items, lambda item: item.source.source_url or (item.symbol, item.source.published_at, item.headline.casefold()))
        except (KeyError, TypeError, ValueError):
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "Finnhub news payload was invalid.")
        self.cache.put(key, items, ttl_seconds=900)
        self.usage.record(self.provider, endpoint, cache_hit=False)
        return ProviderResult(value=items)

    def earnings_calendar(self, symbol: str) -> ProviderResult[list[EarningsEvent]]:
        endpoint = EndpointClass.EARNINGS_CALENDAR
        blocked = self._permitted(endpoint)
        if blocked:
            return blocked
        if not self._api_key:
            return self._failure(endpoint, FailureClass.UNCONFIGURED, "Finnhub API key is not configured.")
        symbol = symbol.strip().upper()
        key = f"earnings-calendar:{symbol}"
        cached = self.cache.get(key)
        if cached is not None:
            self.usage.record(self.provider, endpoint, cache_hit=True)
            return ProviderResult(value=cached, cache_hit=True)
        payload, failure = self._request(endpoint, f"{self.BASE_URL}/calendar/earnings", params={"symbol": symbol, "token": self._api_key})
        if failure:
            return failure
        try:
            assert isinstance(payload, dict)
            events = [EarningsEvent(symbol=str(row["symbol"]), event_date=datetime.fromisoformat(f"{row['date']}T00:00:00+00:00"), source=SourceMetadata(provider=self.provider, source_url=f"{self.BASE_URL}/calendar/earnings", retrieved_at=self._now())) for row in payload.get("earningsCalendar", [])[:20] if isinstance(row, dict)]
            events = deduplicate_records(events, lambda event: (event.symbol, event.event_date))
        except (KeyError, TypeError, ValueError):
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "Finnhub earnings calendar payload was invalid.")
        self.cache.put(key, events, ttl_seconds=3600)
        self.usage.record(self.provider, endpoint, cache_hit=False)
        return ProviderResult(value=events)

    def earnings_surprises(self, symbol: str) -> ProviderResult[list[EarningsResult]]:
        endpoint = EndpointClass.EARNINGS_SURPRISE
        blocked = self._permitted(endpoint)
        if blocked:
            return blocked
        if not self._api_key:
            return self._failure(endpoint, FailureClass.UNCONFIGURED, "Finnhub API key is not configured.")
        symbol = symbol.strip().upper()
        key = f"earnings-surprise:{symbol}"
        cached = self.cache.get(key)
        if cached is not None:
            self.usage.record(self.provider, endpoint, cache_hit=True)
            return ProviderResult(value=cached, cache_hit=True)
        payload, failure = self._request(endpoint, f"{self.BASE_URL}/stock/earnings", params={"symbol": symbol, "token": self._api_key})
        if failure:
            return failure
        try:
            assert isinstance(payload, list)
            results = [EarningsResult(symbol=symbol, actual=str(row["actual"]) if row.get("actual") is not None else None, estimate=str(row["estimate"]) if row.get("estimate") is not None else None, source=SourceMetadata(provider=self.provider, source_url=f"{self.BASE_URL}/stock/earnings", retrieved_at=self._now(), observed_at=datetime.fromisoformat(f"{row['period']}T00:00:00+00:00") if row.get("period") else None)) for row in payload[:20] if isinstance(row, dict)]
            results = deduplicate_records(results, lambda result: (result.symbol, result.source.observed_at, result.actual, result.estimate))
        except (KeyError, TypeError, ValueError):
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "Finnhub earnings payload was invalid.")
        self.cache.put(key, results, ttl_seconds=3600)
        self.usage.record(self.provider, endpoint, cache_hit=False)
        return ProviderResult(value=results)


class SecAdapter(_Adapter):
    BASE_URL = "https://data.sec.gov"
    _ALLOWED_FORMS = {"8-K", "10-Q", "10-K", "20-F", "40-F", "6-K"}

    def __init__(self, *, user_agent: str, enabled: bool, transport: httpx.BaseTransport | None = None,
                 now: Callable[[], datetime] | None = None, sleep: Callable[[float], None] | None = None,
                 clock: Callable[[], float] | None = None,
                 paid_endpoints: set[EndpointClass] | None = None) -> None:
        normalized_user_agent = user_agent.strip()
        contact = re.search(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", normalized_user_agent)
        if len(normalized_user_agent) > 256 or not contact:
            raise ProviderConfigurationError("SEC User-Agent must include a bounded contact email identifier.")
        super().__init__("sec", enabled=enabled, transport=transport, now=now, sleep=sleep,
                         calls_per_minute=300, calls_per_second=5, clock=clock, paid_endpoints=paid_endpoints)
        self._user_agent = normalized_user_agent

    def submissions(self, cik: str) -> ProviderResult[list[SecFilingEvent]]:
        endpoint = EndpointClass.SEC_SUBMISSIONS
        blocked = self._permitted(endpoint)
        if blocked:
            return blocked
        try:
            normalized_cik = normalize_cik(cik)
        except ValueError:
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "SEC CIK was invalid.")
        key = f"submissions:{normalized_cik}"
        cached = self.cache.get(key)
        if cached is not None:
            self.usage.record(self.provider, endpoint, cache_hit=True)
            return ProviderResult(value=cached, cache_hit=True)
        payload, failure = self._request(endpoint, f"{self.BASE_URL}/submissions/CIK{normalized_cik.zfill(10)}.json", headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"})
        if failure:
            return failure
        try:
            assert isinstance(payload, dict)
            recent = payload["filings"]["recent"]
            rows = zip(recent["accessionNumber"], recent["form"], recent["filingDate"], recent["primaryDocument"], strict=True)
            filings = []
            for accession, form, date, document in rows:
                if form not in self._ALLOWED_FORMS:
                    continue
                source = SourceMetadata(provider=self.provider, source_url=f"https://www.sec.gov/Archives/edgar/data/{normalized_cik}/{str(accession).replace('-', '')}/{document}", retrieved_at=self._now(), published_at=datetime.fromisoformat(f"{date}T00:00:00+00:00"))
                filings.append(SecFilingEvent(cik=normalized_cik, form=form, accession_number=str(accession), filing_date=source.published_at, source=source))
        except (KeyError, TypeError, ValueError):
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "SEC submissions payload was invalid.")
        filings = deduplicate_records(filings, lambda filing: (filing.cik, filing.accession_number))
        self.cache.put(key, filings, ttl_seconds=3600)
        self.usage.record(self.provider, endpoint, cache_hit=False)
        return ProviderResult(value=filings)

    def company_facts(self, cik: str) -> ProviderResult[list[SecCompanyFact]]:
        endpoint = EndpointClass.SEC_COMPANY_FACTS
        blocked = self._permitted(endpoint)
        if blocked:
            return blocked
        try:
            normalized_cik = normalize_cik(cik)
        except ValueError:
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "SEC CIK was invalid.")
        key = f"company-facts:{normalized_cik}"
        cached = self.cache.get(key)
        if cached is not None:
            self.usage.record(self.provider, endpoint, cache_hit=True)
            return ProviderResult(value=cached, cache_hit=True)
        payload, failure = self._request(endpoint, f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{normalized_cik.zfill(10)}.json", headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"})
        if failure:
            return failure
        try:
            assert isinstance(payload, dict)
            facts: list[SecCompanyFact] = []
            for taxonomy in ("us-gaap", "dei"):
                for tag, fact in list(payload.get("facts", {}).get(taxonomy, {}).items())[:100]:
                    units = fact.get("units", {})
                    unit, observations = next(iter(units.items()))
                    if not observations:
                        continue
                    observation = observations[-1]
                    facts.append(SecCompanyFact(cik=normalized_cik, taxonomy=taxonomy, tag=tag, unit=unit, value=str(observation["val"]), filed_at=datetime.fromisoformat(f"{observation['filed']}T00:00:00+00:00") if observation.get("filed") else None, source=SourceMetadata(provider=self.provider, source_url=f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{normalized_cik.zfill(10)}.json", retrieved_at=self._now())))
        except (KeyError, StopIteration, TypeError, ValueError):
            return self._failure(endpoint, FailureClass.INVALID_PAYLOAD, "SEC company facts payload was invalid.")
        facts = deduplicate_records(facts, lambda fact: (fact.cik, fact.taxonomy, fact.tag, fact.unit, fact.filed_at, fact.value))
        self.cache.put(key, facts, ttl_seconds=86400)
        self.usage.record(self.provider, endpoint, cache_hit=False)
        return ProviderResult(value=facts)
