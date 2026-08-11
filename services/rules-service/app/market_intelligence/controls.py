"""Deterministic in-memory controls for bounded provider access."""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Generic, Hashable, Iterable, TypeVar

from .contracts import StrictModel


class EndpointClass(StrEnum):
    QUOTE = "quote"
    COMPANY_NEWS = "company_news"
    EARNINGS_CALENDAR = "earnings_calendar"
    EARNINGS_SURPRISE = "earnings_surprise"
    SEC_SUBMISSIONS = "sec_submissions"
    SEC_COMPANY_FACTS = "sec_company_facts"


class UsageRecord(StrictModel):
    provider: str
    endpoint_class: EndpointClass
    cache_hit: bool
    count: int = 1
    period: str


class UsageLedger:
    """Memory-only, aggregate-safe provider usage records."""
    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self.records: list[UsageRecord] = []

    def record(self, provider: str, endpoint_class: EndpointClass, *, cache_hit: bool) -> None:
        now = self._now()
        self.records.append(UsageRecord(provider=provider, endpoint_class=endpoint_class, cache_hit=cache_hit, period=f"{now.year:04d}-{now.month:02d}"))


T = TypeVar("T")


class BoundedCache(Generic[T]):
    def __init__(self, max_entries: int = 128, clock: Callable[[], float] | None = None) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        import time
        self._max_entries, self._clock = max_entries, clock or time.monotonic
        self._values: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        item = self._values.get(key)
        if item is None or item[0] <= self._clock():
            self._values.pop(key, None)
            return None
        self._values.move_to_end(key)
        return item[1]

    def put(self, key: str, value: T, *, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._values[key] = (self._clock() + ttl_seconds, value)
        self._values.move_to_end(key)
        while len(self._values) > self._max_entries:
            self._values.popitem(last=False)


class RateLimitExceeded(Exception):
    pass


class SlidingWindowPacer:
    """Reject excess calls instead of sleeping unbounded in a request path."""
    def __init__(self, calls_per_minute: int, clock: Callable[[], float] | None = None) -> None:
        if not 1 <= calls_per_minute <= 600:
            raise ValueError("calls_per_minute must be between 1 and 600")
        import time
        self._ceiling, self._clock = calls_per_minute, clock or time.monotonic
        self._timestamps: deque[float] = deque()

    def acquire(self) -> None:
        now = self._clock()
        while self._timestamps and self._timestamps[0] <= now - 60:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._ceiling:
            raise RateLimitExceeded("provider call ceiling reached")
        self._timestamps.append(now)


def deduplicate_records(records: Iterable[T], identity: Callable[[T], Hashable]) -> list[T]:
    """Keep the first item for each stable normalized identity, deterministically."""
    seen: set[Hashable] = set()
    unique: list[T] = []
    for record in records:
        key = identity(record)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique
