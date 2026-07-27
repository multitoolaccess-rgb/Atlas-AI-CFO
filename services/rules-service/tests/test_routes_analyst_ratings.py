"""Phase 9 analyst-ratings route tests.

Mocks ``httpx.AsyncClient.get`` so tests don't depend on a real
Finnhub API key + tier-quota. Tests cover:

- happy path (matching real Finnhub upstream shape: trends=array, price_target=object).
- cache hit: second call for same ticker skips upstream.
- ticker validation: BRK.B and RDS-A class-share shapes ARE accepted.
- missing ``FINNHUB_API_KEY`` returns 500 (operator misconfig).
- upstream 5xx propagates as 502 (not 500 -- distinguishable by FE).
- auth: ``require_user`` is wired.
"""
from __future__ import annotations

import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# ---- httpx.AsyncClient.get shim -----------------------------------------
# We monkeypatch the AsyncClient.get method via a wrapper so each call
# can return a customisable response. The wrapper records calls so the
# assertion stage can verify the ticker was forwarded correctly.

_CALLS: list[dict] = []


class _FakeResponse:
    """A response object that quacks like httpx.Response for the
    route handler's ``resp.status_code`` + ``resp.json()`` usage."""

    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _install_mock(monkeypatch, *, trends_payload, targets_payload,
                  trends_status=200, targets_status=200):
    """Replace httpx.AsyncClient.get with a stub that returns the
    canned payloads. Records every call so tests can assert.

    ``trends_payload`` MUST be a JSON array (matches Finnhub
    /stock/recommendation). ``targets_payload`` MUST be a JSON object
    NOT wrapped in an array (matches Finnhub /stock/price-target's
    real shape).
    """

    _CALLS.clear()

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            _CALLS.append({"url": url, "params": params or {}})
            if url.endswith("/stock/recommendation"):
                return _FakeResponse(trends_status, trends_payload)
            if url.endswith("/stock/price-target"):
                return _FakeResponse(targets_status, targets_payload)
            return _FakeResponse(404, [])

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


# ---- tests --------------------------------------------------------------

def test_get_analyst_ratings_happy_path(client, monkeypatch):
    """First call to a ticker fetches upstream and joins both endpoints
    into a single response keyed on the symbol.

    Real Finnhub returns trends as ARRAY and price-target as OBJECT
    (NOT wrapped). The route passes them through unchanged after
    joining under the symbol key."""

    trends = [{
        "period": "2025-05",
        "strongBuy": 12, "buy": 18, "hold": 7, "sell": 1, "strongSell": 0,
    }]
    # Real shape: a SINGLE object, not wrapped in a list.
    targets = {
        "symbol": "AAPL",
        "targetMean": 232.10,
        "targetMedian": 230.0,
        "targetHigh": 280.0,
        "targetLow": 165.0,
        "lastUpdated": "2025-05-30",
    }
    _install_mock(monkeypatch, trends_payload=trends, targets_payload=targets)
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key-abc")
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r = client.get("/api/analyst-ratings/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["recommendation_trends"] == trends
    assert body["price_target"] == {
        "targetHigh": 280.0,
        "targetLow": 165.0,
        "targetMean": 232.1,
        "targetMedian": 230.0,
    }


def test_get_analyst_ratings_accepts_class_share_tickers(client, monkeypatch):
    """``BRK.B`` (Berkshire Hathaway B) and ``RDS-A`` (Shell) must NOT 400.

    Locks the Phase-9 code-review fix that expanded the ticker
    validator from ``str.isalnum()`` to a regex allowing ``.`` and ``-``."""

    _install_mock(
        monkeypatch,
        trends_payload=[{"period": "2025-05"}],
        targets_payload={"targetMean": 100},
    )
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    for ticker in ("BRK.B", "RDS-A", "AAPL", "MSFT"):
        _clear_cache_for_tests()
        r = client.get(f"/api/analyst-ratings/{ticker}")
        assert r.status_code == 200, (
            f"ticker {ticker} unexpectedly rejected: {r.status_code} {r.text}"
        )


def test_get_analyst_ratings_is_case_insensitive(client, monkeypatch):
    """``AAPL`` and ``aapl`` share the same cache entry."""

    _install_mock(
        monkeypatch,
        trends_payload=[{"period": "2025-05"}],
        targets_payload={"targetMean": 200},
    )
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r1 = client.get("/api/analyst-ratings/AAPL")
    r2 = client.get("/api/analyst-ratings/aapl")
    assert r1.status_code == 200
    assert r2.status_code == 200

    # The cache should make r2 skip the upstream entirely -- so the
    # recorded calls count is exactly 2 (one trends + one targets
    # from r1 only).
    assert len(_CALLS) == 2


def test_get_analyst_ratings_rejects_invalid_characters(client, monkeypatch):
    """``@`` passes Starlette's default path-segment matching but is NOT
    a real ticker shape -- the regex validator returns 400."""

    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    r = client.get("/api/analyst-ratings/AAPL@BAD")
    assert r.status_code == 400, f"unexpected {r.status_code}: {r.text}"
    assert "letters" in r.json()["detail"].lower()


def test_get_analyst_ratings_500_when_api_key_missing(client, monkeypatch):
    """Operator-misconfig surfaced as 500 (NOT 401 or 502) so it can
    be distinguished from auth and upstream failures.

    Phase 39.2 — ``monkeypatch.delenv`` only clears the worker's
    ``os.environ``; the pydantic ``Settings`` instance in
    ``app.config`` was populated from ``services/rules-service/.env``
    at module import time, so we ALSO monkeypatch
    ``settings.finnhub_api_key`` to ``None`` here. Without that, the
    new ``os.environ OR settings.finnhub_api_key`` fallback chain in
    ``routes/analyst_ratings.py`` would still find the key (loaded
    from a developer-laptop ``.env``) and the test would 200 instead
    of 500.
    """

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    from app.config import settings
    monkeypatch.setattr(settings, "finnhub_api_key", None)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()
    r = client.get("/api/analyst-ratings/AAPL")
    assert r.status_code == 500
    assert "api key" in r.json()["detail"].lower()


def test_get_analyst_ratings_succeeds_when_key_only_in_settings_layer(
    client, monkeypatch,
):
    """Phase 39.2 regression test — proves the new fallback chain.

    Scenario: ``FINNHUB_API_KEY`` is NOT in ``os.environ`` (developer
    didn't ``export`` it from the launching shell) and the host has
    it ONLY in ``services/rules-service/.env`` (which pydantic-settings
    reads at module-import time).

    Before this fix, ``routes/analyst_ratings.py`` read
    ``os.environ.get("FINNHUB_API_KEY")`` only -- so the .env value
    was invisible and the endpoint returned 500. The Phase 39.2 fix
    adds a fallback to ``settings.finnhub_api_key`` so the dev path
    (``.env`` is canonical) Just Works.

    We simulate the dev path by ``monkeypatch.delenv`` (clear shell
    side) + ``monkeypatch.setattr(settings, "finnhub_api_key", X)``
    (set the pydantic-side value). Then we assert the route uses ``X``
    in the upstream ``?token=`` parameter (not ``None`` and not the
    empty string).
    """

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    from app.config import settings
    monkeypatch.setattr(settings, "finnhub_api_key", "settings-only-key")

    trends = [{
        "period": "2026-06", "strongBuy": 1, "buy": 2, "hold": 3,
        "sell": 0, "strongSell": 0,
    }]
    targets = {"targetMean": 100.0, "targetHigh": 120.0,
               "targetLow": 80.0, "targetMedian": 100.0}
    _install_mock(monkeypatch, trends_payload=trends, targets_payload=targets)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r = client.get("/api/analyst-ratings/AAPL")
    assert r.status_code == 200, (
        f"Phase 39.2 fallback broken -- expected 200, got "
        f"{r.status_code} {r.text}"
    )
    # Confirm the upstream WAS called with the settings-layer key, not
    # the empty string. Both /stock/recommendation and
    # /stock/price-target should carry ?token=settings-only-key.
    tokens_sent = [c["params"].get("token") for c in _CALLS]
    assert "settings-only-key" in tokens_sent, (
        f"settings.finnhub_api_key never reached Finnhub call: "
        f"tokens={tokens_sent!r}"
    )
    # And no None / empty-string token leaked to upstream.
    assert None not in tokens_sent, (
        f"None token leaked to Finnhub call: {tokens_sent!r}"
    )
    assert "" not in tokens_sent, (
        f"empty-string token leaked to Finnhub call: {tokens_sent!r}"
    )


def test_get_analyst_ratings_fails_soft_on_price_target_403(client, monkeypatch):
    """Free-tier 403 on /stock/price-target fails soft: the route
    returns 200, recommendation_trends carries the real data from
    /stock/recommendation, and price_target is None so the FE renders
    "no consensus yet" for the price-target grid instead of discarding
    the entire signal because one of two endpoints is tier-restricted.
    """

    _install_mock(
        monkeypatch,
        trends_payload=[{"period": "2025-05", "strongBuy": 14, "buy": 24, "hold": 15, "sell": 2, "strongSell": 0}],
        targets_payload={"error": "You don't have access to this resource."},
        trends_status=200,
        targets_status=403,
    )
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r = client.get("/api/analyst-ratings/AAPL")
    assert r.status_code == 200, f"unexpected {r.status_code}: {r.text}"
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["recommendation_trends"] == [
        {"period": "2025-05", "strongBuy": 14, "buy": 24, "hold": 15, "sell": 2, "strongSell": 0},
    ]
    assert body["price_target"] is None


def test_get_analyst_ratings_502_on_upstream_error(client, monkeypatch):
    """Finnhub returning 500 is propagated as 502 (Bad Gateway) so the
    FE shows a "Finnhub is having issues" banner, not a "your
    request was malformed" one."""

    _install_mock(
        monkeypatch,
        trends_payload=[],
        targets_payload=[],
        trends_status=500,
        targets_status=200,
    )
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()
    r = client.get("/api/analyst-ratings/TSLA")
    assert r.status_code == 502
    detail = r.json()["detail"].lower()
    assert "upstream" in detail or "finnhub" in detail


def test_get_analyst_ratings_requires_authentication():
    """An unauthenticated request is rejected with 401 -- the route is
    JWT-guarded even though the data is public upstream data."""

    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)  # no Cookie header at all
    r = c.get("/api/analyst-ratings/MSFT")
    assert r.status_code == 401
