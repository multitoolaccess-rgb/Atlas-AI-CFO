"""Phase 42 batch analyst-ratings route tests.

Replicates the httpx.AsyncClient shim from
``test_routes_analyst_ratings.py`` so each test runs against the
exact same mocked Finnhub surface. Duplicated rather than
imported because pytest test-modules should not import other
test-modules (fixture discovery + pytest_plugins order would
need to be re-tuned); the shim is ~30 lines and the duplication
is contained.

Coverage:

* **happy_path_all_cache_hits** — every ticker is already cached,
  zero upstream calls, results list mirrors dedup'd input order.
* **happy_path_all_cache_misses** — every ticker fetched,
  upstream called exactly ``len(tickers) × 2`` times
  (trends + targets per ticker).
* **mixed_cache_hits_and_misses** — pre-warm the cache for half
  the tickers, verify upstream counts match the UNcached count
  exactly (cache reuse discipline).
* **dedup_tickers** — request ``['aapl', 'AAPL', 'AAPL']``,
  upstream called exactly 2 times (NOT 6).
* **partial_upstream_502** — one ticker's mock returns 502,
  the others return 200; the failed ticker carries
  ``status="error"`` with a detail string, the others are
  ``status="ok"`` with data. Response is 200 (whole-batch
  resilience).
* **partial_invalid_ticker** — one ticker carries an invalid
  character (``@BAD``), the others are valid; route correctly
  classifies the invalid one as ``status="error"`` rather than
  400'ing the whole batch.
* **missing_api_key_returns_500** — operator misconfig surfaces as
  a WHOLE-batch 500 (per the contract documented on the route),
  NOT a partial-success response.
* **empty_list_returns_422** — ``[]`` violates ``min_length=1``,
  Pydantic 422 before any work runs.
* **oversized_list_returns_422** — 51 tickers violates
  ``max_length=50``, 422.
* **non_list_body_returns_422** — ``{"tickers": "AAPL"}`` is the
  wrong type, 422.
* **requires_authentication** — no JWT cookie → 401.
"""
from __future__ import annotations

import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# ---- httpx.AsyncClient shim ---------------------------------------------
# Mirrors ``test_routes_analyst_ratings.py::_install_mock`` but exposes
# ``_status_for_ticker`` so per-ticker error injection (502 for one
# symbol, 200 for another) is one line. Tracking via ``_CALLS`` so
# every test can verify ``len(_CALLS) == expected``.

_CALLS: list[dict] = []


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Per-endpoint status injection via ``_status_for_endpoint_for_ticker``.

    The default returns 200 for everything. Setting
    ``_status_for_ticker = {"AAPL": 502}`` makes AAPL's /stock/recommendation
    AND /stock/price-target return 502; the rest stay 200.
    """

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        _CALLS.append({"url": url, "params": params or {}})
        symbol = (params or {}).get("symbol", "")
        # Honour per-ticker override for the WHOLE ticker (both endpoints
        # fail identically). Tests that only want to fail one endpoint
        # would need a fancier mock; current tests only need WHOLE-ticker
        # 502 injection.
        if symbol in _status_for_ticker:
            return _FakeResponse(_status_for_ticker[symbol], [])

        if url.endswith("/stock/recommendation"):
            return _FakeResponse(
                200,
                [_trends_payload_for(symbol)],
            )
        if url.endswith("/stock/price-target"):
            return _FakeResponse(
                200,
                _targets_payload_for(symbol),
            )
        return _FakeResponse(404, [])


# Default status map + default payload factories. Tests mutate these
# BEFORE calling ``_install_mock`` to inject per-ticker behaviour.

_status_for_ticker: dict[str, int] = {}


@pytest.fixture(autouse=True)
def _reset_mock_status_per_test():
    """Auto-applied fixture — clear ``_status_for_ticker`` both BEFORE
    and AFTER every test in this module.

    The earlier snapshot-restore pattern could REPLAY leaked pollution:
    if test 4 raised before reaching its cleanup ``.pop('AAPL', None)``,
    leaving ``{AAPL: 502}`` in the global, the snapshot captured that
    pollution and the post-yield ``update(snapshot)`` replayed it for
    the next test. Snapshot-restore is the right pattern for shared
    INFRASTRUCTURE you want preserved; it's the wrong pattern for
    shared state you want isolated. We want isolation -- a test
    should always see a clean dict.

    Implementation: ``clear() -> yield -> clear()``. ``autouse=True``
    keeps the test bodies clean (no per-test fixture in the signature).
    """

    _status_for_ticker.clear()
    try:
        yield
    finally:
        _status_for_ticker.clear()


def _trends_payload_for(symbol: str) -> dict:
    return {
        "period": "2026-06",
        "strongBuy": 10,
        "buy": 5,
        "hold": 3,
        "sell": 1,
        "strongSell": 0,
    }


def _targets_payload_for(symbol: str) -> dict:
    return {
        "targetMean": 200.0,
        "targetMedian": 200.0,
        "targetHigh": 220.0,
        "targetLow": 180.0,
    }


def _install_mock(monkeypatch) -> None:
    """Install the per-ticker-aware mock + clear the call log.

    All per-ticker overrides MUST be set on ``_status_for_ticker``
    BEFORE calling _install_mock.
    """
    _CALLS.clear()
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


# ---- tests --------------------------------------------------------------


def test_batch_all_cache_hits_returned_in_order(client, monkeypatch):
    """Pre-warm the cache for every ticker, then batch-fetch; ZERO
    upstream calls. Order of results mirrors the FE's input order."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    # Pre-warm via the existing single route. Each pre-warm triggers
    # 2 upstream calls (trends + targets); measured below in the
    # cache_misses path but irrelevant here, so we just clear the
    # _CALLS log after pre-warming.
    _install_mock(monkeypatch)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()
    for sym in ("AAPL", "MSFT", "TSLA"):
        client.get(f"/api/analyst-ratings/{sym}")
    _CALLS.clear()

    # Now batch-fetch — every ticker should hit the cache.
    r = client.post("/api/analyst-ratings/batch", json={"tickers": ["AAPL", "MSFT", "TSLA"]})
    assert r.status_code == 200
    body = r.json()
    assert [item["symbol"] for item in body["results"]] == ["AAPL", "MSFT", "TSLA"]
    assert all(item["status"] == "ok" for item in body["results"])
    assert len(_CALLS) == 0, (
        f"Expected 0 upstream calls for cache-hit batch, got {len(_CALLS)} -- "
        f"Phase 42 cache reuse is broken."
    )


def test_batch_all_cache_misses_call_upstream_per_ticker(client, monkeypatch):
    """Cold-start: every ticker triggers 2 upstream calls (trends + targets).
    ``len(_CALLS) == len(tickers) * 2`` enforces the cache-miss path."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r = client.post("/api/analyst-ratings/batch", json={"tickers": ["AAPL", "MSFT"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 2
    assert all(item["status"] == "ok" for item in body["results"])
    assert len(_CALLS) == 4, (
        f"Expected 4 upstream calls (2 tickers × 2 endpoints), got {len(_CALLS)}"
    )


def test_batch_mixed_cache_hits_and_misses_skip_upstream_for_hits(client, monkeypatch):
    """Cache discipline: pre-warm one ticker, batch-fetch a list
    containing it + 2 uncached tickers. Upstream is called exactly
    for the 2 uncached tickers (4 upstream calls = 2 × 2 endpoints).
    The cached ticker's batch result is still ``status='ok'`` because
    the BE's cache lookup short-circuits the upstream path entirely."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    # Pre-warm AAPL only.
    client.get("/api/analyst-ratings/AAPL")
    _CALLS.clear()

    # Batch-fetch: AAPL (cached) + MSFT + TSLA (uncached).
    r = client.post("/api/analyst-ratings/batch", json={"tickers": ["AAPL", "MSFT", "TSLA"]})
    assert r.status_code == 200
    body = r.json()
    assert [item["symbol"] for item in body["results"]] == ["AAPL", "MSFT", "TSLA"]
    assert all(item["status"] == "ok" for item in body["results"])
    assert len(_CALLS) == 4, (
        f"Expected 4 upstream calls (TSLA + MSFT only), got {len(_CALLS)} "
        f"-- the cached AAPL must NOT have triggered upstream."
    )


def test_batch_dedups_tickers(client, monkeypatch):
    """Client sends ``[aapl, AAPL, AAPL, msft]``; upstream is called
    exactly for 2 unique tickers (4 upstream calls = 2 × 2 endpoints).
    The response array has exactly 2 results in first-seen order."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r = client.post(
        "/api/analyst-ratings/batch",
        json={"tickers": ["aapl", "AAPL", "AAPL", "msft"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 2
    assert [item["symbol"] for item in body["results"]] == ["AAPL", "MSFT"]
    assert len(_CALLS) == 4, (
        f"Expected 4 upstream calls (2 unique tickers), got {len(_CALLS)} "
        f"-- dedup discipline is broken."
    )


def test_batch_partial_upstream_502_returns_status_error_per_ticker(client, monkeypatch):
    """The headline contract: one ticker upstream errors out, the OTHERS
    still succeed. Response is 200 (whole-batch resilience), the failed
    ticker carries ``status='error'`` with a detail string the FE renders
    in the per-row chip.

    Without this contract the FE's coverage card would render
    "9 of 10 failed" instead of "9 of 10 covered, 1 uncovered"."""
    _status_for_ticker["AAPL"] = 502
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r = client.post("/api/analyst-ratings/batch", json={"tickers": ["AAPL", "MSFT"]})
    assert r.status_code == 200, (
        f"Phase 42 whole-batch resilience is broken -- expected 200 even "
        f"with one ticker failing, got {r.status_code} {r.text}"
    )
    body = r.json()
    by_symbol = {item["symbol"]: item for item in body["results"]}
    assert by_symbol["AAPL"]["status"] == "error"
    assert "upstream" in by_symbol["AAPL"]["error"].lower()
    assert by_symbol["MSFT"]["status"] == "ok"
    assert by_symbol["MSFT"]["data"] is not None
    # Note: cleanup of ``_status_for_ticker`` is handled by the
    # ``_reset_mock_status_per_test`` autofixture (declared at module
    # top) so a mid-test assertion failure here can't leak state to the
    # next test.


def test_batch_partial_invalid_ticker_classified_as_error(client, monkeypatch):
    """An invalid ticker shape (``@BAD``) is ``status='error'`` + 400
    detail; valid tickers in the same batch still succeed."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    # The regex rejects ``@BAD`` so it can't be cached or fetched; the
    # per-ticket handler catches HTTPException(400) and converts to
    # ``status="error"``.
    r = client.post(
        "/api/analyst-ratings/batch",
        # Path with special chars via URL-escape. The Pydantic field
        # is a str, so the body validates; the BE handler then runs
        # the regex against ``@BAD`` and raises.
        json={"tickers": ["AAPL", "AAPL@BAD"]},
    )
    assert r.status_code == 200
    body = r.json()
    by_symbol = {item["symbol"] for item in body["results"]}
    assert "AAPL" in by_symbol
    # The invalid one carries status=error; the regex uppercases the
    # input so the symbol echo is ``AAPL@BAD``.
    error_items = [i for i in body["results"] if i["status"] == "error"]
    assert len(error_items) == 1, f"Expected exactly 1 error entry, got {len(error_items)}"
    assert "letters" in error_items[0]["error"].lower()


def test_batch_missing_api_key_returns_500(client, monkeypatch):
    """Operator misconfig: missing API key surfaces as a WHOLE-batch
    500, NOT as a partial-success response. Keeps the FE's banner-vs-
    chip distinction clear (banner = "service down"; chip = "this
    ticker uncovered")."""
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    from app.config import settings
    monkeypatch.setattr(settings, "finnhub_api_key", None)
    r = client.post("/api/analyst-ratings/batch", json={"tickers": ["AAPL"]})
    assert r.status_code == 500, f"Expected 500, got {r.status_code} {r.text}"
    assert "api key" in r.json()["detail"].lower()


def test_batch_empty_list_returns_422(client, monkeypatch):
    """Empty ``tickers`` violates Pydantic ``min_length=1``; the FE
    always sends at least 1 ticker so this 422 surfaces a code smell."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    r = client.post("/api/analyst-ratings/batch", json={"tickers": []})
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"


def test_batch_oversized_list_returns_422(client, monkeypatch):
    """51 tickers violates Pydantic ``max_length=50``; protects against
    a runaway client blasting the queue (would translate to 100+
    simultaneous upstream calls + risk of Finnhub 429)."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    r = client.post(
        "/api/analyst-ratings/batch",
        json={"tickers": [f"T{i:02d}" for i in range(51)]},
    )
    assert r.status_code == 422


def test_batch_non_list_tickers_returns_422(client, monkeypatch):
    """``tickers`` is a ``List[str]``; a string instead of a list is
    a wrong-type rejection Pydantic catches upfront."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    r = client.post("/api/analyst-ratings/batch", json={"tickers": "AAPL"})
    assert r.status_code == 422


def test_batch_requires_authentication():
    """The route is JWT-guarded; a missing JWT cookie short-circuits
    to 401 before the API-key check."""
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    r = c.post("/api/analyst-ratings/batch", json={"tickers": ["AAPL"]})
    assert r.status_code == 401


def test_batch_response_payload_shape_matches_single_route(client, monkeypatch):
    """The data shape inside ``BatchRatingsResultItem.data`` MUST
    mirror the GET route's response body so the FE can pass it into
    the existing ``getAnalystRatings``-shaped cache without
    re-coercion.

    Locks the ``recommendation_trends`` + ``price_target`` keys at
    the BE/UI boundary."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    _install_mock(monkeypatch)
    from app.routes.analyst_ratings import _clear_cache_for_tests
    _clear_cache_for_tests()

    r = client.post("/api/analyst-ratings/batch", json={"tickers": ["AAPL"]})
    assert r.status_code == 200
    item = r.json()["results"][0]
    assert item["status"] == "ok"
    data = item["data"]
    # Same keys as ``GET /api/analyst-ratings/AAPL``.
    assert "symbol" in data
    assert "recommendation_trends" in data
    assert "price_target" in data
    # price_target carries the four canonical fields.
    if data["price_target"] is not None:
        for k in ("targetHigh", "targetLow", "targetMean", "targetMedian"):
            assert k in data["price_target"]
