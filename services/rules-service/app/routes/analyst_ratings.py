"""Phase 9 analyst-ratings endpoint.

Wraps Finnhub's free-tier
``GET https://finnhub.io/api/v1/stock/recommendation`` and
``GET https://finnhub.io/api/v1/stock/price-target`` endpoints behind
a JWT-auth-guarded FastAPI route so the Next.js recommendations page
can render real-time sell-side consensus + price targets without
exposing the Finnhub API key in the browser bundle.

Architectural decisions (locked in by the Phase 9 design review):

1. **Finnhub over Alpha Vantage / Polygon / FMP.** Free tier is 60
   calls/min (vs 25/day for Alpha Vantage and 5/min for Polygon), no
   credit card required, and the two endpoints we need
   (``/stock/recommendation`` + ``/stock/price-target``) are part of
   the standard free-tier surface.

2. **24-hour in-memory TTL cache.** Analyst ratings move slowly --
   end-of-day is the right refresh boundary. ``cachetools.TTLCache``
   with ``maxsize=100`` keeps the cache bounded for a single-user
   local-first app (avoids needing Redis). Cache key is the ticker
   symbol uppercased; case-insensitive lookup is implicit because we
   uppercase before keying.

3. **Fail loud on missing API key.** ``FINNHUB_API_KEY`` env var is
   REQUIRED at runtime. We surface a 500 (not a confusing upstream
   401) so an operator can grep ``finnhub`` in uvicorn logs and find
   the missing-env hint immediately. The same key is consumed in
   tests via ``monkeypatch.setenv``.

4. **502 NOT 500 for upstream errors.** A 502 Bad Gateway is what
   the FE should treat as "Finnhub's problem" (and show a friendly
   retry banner). Distinguishing upstream-failure from our own
   crash is critical for triage.

5. **Cache invalidation is purely time-based.** No manual flush.
   Operators who want a forced refresh can restart the rules-service
   process. For a single-user MVP this is simpler than wiring an
   admin endpoint that competes with future signin flows.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.auth import require_user
from app.config import settings
# Phase 42 -- ``BatchRatingsRequest`` / ``BatchRatingsResponse`` /
# ``BatchRatingsResultItem`` are the request+response shapes for the
# new ``POST /api/analyst-ratings/batch`` route. Defined in
# ``schemas/__init__.py`` alongside every other Phase-X schema so the
# route module doesn't carry Pydantic class bodies.
from app.schemas import (
    BatchRatingsRequest,
    BatchRatingsResponse,
    BatchRatingsResultItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analyst-ratings", tags=["analyst-ratings"])

# 24-hour TTL is the only sane choice for analyst ratings: endpoints
# refresh end-of-day, intraday fetches would burn the 60-calls/min
# limit with no information gain. ``maxsize=100`` covers a generous
# portfolio size for a single user without unbounded memory growth.
_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=100, ttl=86400)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# Ticker grammar per real-world exchanges + Finnhub's accepted shapes:
#   - 1-10 characters (longest universally accepted ticker)
#   - uppercase letters + digits
#   - '.' class-share separator (e.g. BRK.B Berkshire Hathaway B)
#   - '-' preferred-share separator (e.g. RDS-A Shell)
# Naive ``str.isalnum()`` rejects both forms, breaking a common UX.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


async def _fetch_finnhub(endpoint: str, params: dict[str, str]) -> Any:
    """Internal helper: GET ``endpoint`` from Finnhub with ``params``,
    raise on non-200, return parsed JSON.

    Soft-fail exception: when the endpoint is ``stock/price-target``
    AND the upstream returns HTTP 403 (Finnhub free-tier per-ticker
    restriction), this helper returns ``None`` instead of raising --
    letting the route handler render ``price_target: null`` while
    still surfacing the recommendation_trends data the OTHER endpoint
    already returned. All other status codes (401, 429, 5xx, 403 on
    other endpoints) still raise so the FE gets the actionable error.

    The return type is ``Any`` rather than ``list[dict]`` because
    Finnhub's two endpoints differ:
      - ``/stock/recommendation`` returns a JSON array.
      - ``/stock/price-target`` returns a single JSON object (NOT wrapped).
    The route handler is responsible for recognising each shape.

    Split out so the route handler stays close to its OpenAPI shape
    and the test mockery can monkeypatch the network boundary
    without rewriting the endpoint shape.
    """
    # Phase 39.2 — read from BOTH the process env AND the pydantic
    # ``Settings`` instance. ``Settings()`` (in ``app/config.py``)
    # loads ``services/rules-service/.env`` at module-import time, so
    # a developer who pastes ``FINNHUB_API_KEY=<value>`` into the .env
    # is wired up automatically — no shell ``export`` needed.
    #
    # The ordering is ``os.environ`` FIRST so existing tests that use
    # ``monkeypatch.setenv("FINNHUB_API_KEY", ...)`` keep working
    # without code changes (monkeypatch is a runtime mutator of
    # ``os.environ`` and not of the frozen Settings model). The
    # settings-second branch covers the dev path where the .env file
    # is the canonical source AND the docker-compose path where the
    # operator-level env var flows through the worker's
    # ``os.environ`` (in which case the first branch wins and the
    # second is a no-op).
    api_key = (
        os.environ.get("FINNHUB_API_KEY") or settings.finnhub_api_key or ""
    ).strip()
    if not api_key:
        # 500 (not 401) because this is an OPERATOR misconfiguration --
        # the user cannot fix it from the UI, and we want the error
        # code to range separately from auth failures so the FE shows
        # the right banner.
        logger.error(
            "FINNHUB_API_KEY env var is unset or blank -- "
            "the analyst-ratings endpoint cannot fetch upstream data. "
            "Set it in your .env per docs/setup.md."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analyst ratings service is not configured (missing API key).",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{FINNHUB_BASE}/{endpoint}",
            params={**params, "token": api_key},
        )
        if resp.status_code == 401:
            # Distinguish "key revoked" from generic upstream-down so
            # the operator gets a clear signal in the FE banner. A 401
            # from Finnhub specifically means ``FINNHUB_API_KEY`` is
            # invalid or rate-limit exceeded; both are operator-
            # fixable, not transient.
            logger.error(
                "Finnhub %s returned 401 for %s -- check FINNHUB_API_KEY",
                endpoint, params.get("symbol"),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Finnhub rejected the API key (HTTP 401). "
                    "Verify FINNHUB_API_KEY in the BE environment."
                ),
            )
        if resp.status_code == 403 and endpoint == "stock/price-target":
            # Free-tier 403 on /stock/price-target is a per-ticker tier
            # restriction, NOT a transient upstream error -- the OTHER
            # endpoint (/stock/recommendation) just returned 200 with
            # real consensus counts. Failing hard here would discard
            # the trend data the user already has. Fail soft: return
            # None and let the route handler render ``price_target: null``
            # so the FE shows "no consensus yet" while still displaying
            # the breakdown the user came for.
            #
            # We deliberately do NOT cache the partial (price_target=None)
            # response in this file -- the existing cache logic in the
            # ROUTE HANDLER caches the full payload regardless of
            # whether price_target is null, so a 24h re-query won't
            # re-burn the rate limit against the same restricted ticker.
            logger.warning(
                "Finnhub free-tier 403 on %s for %s -- failing soft, "
                "returning price_target=None.",
                endpoint, params.get("symbol"),
            )
            return None

        if resp.status_code != 200:
            # Upstream error -- surface as 502 so the FE can render a
            # "Finnhub returned an error, try again" banner instead
            # of a generic "Network Error". Body is intentionally not
            # included; it can contain Finnhub internal markers we
            # don't want to advertise.
            logger.warning(
                "Finnhub %s returned %d for %s",
                endpoint, resp.status_code, params.get("symbol"),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Finnhub upstream returned HTTP {resp.status_code}.",
            )
        return resp.json()


async def _get_single_rating(symbol: str) -> dict[str, Any]:
    """Phase 42 -- shared single-ticker fetch used by BOTH the GET
    ``/api/analyst-ratings/{ticker}`` route AND the POST
    ``/api/analyst-ratings/batch`` route.

    Extracted so the single source-of-truth for cache lookup +
    upstream fan-out + payload shaping lives in ONE place. The GET
    route kept its original ``400`` semantics for malformed tickers
    (single-row 400s ARE appropriate for the lazy drawer), and the
    batch route wraps this helper in a try/except so one bad ticker
    shows up as a per-item ``status="error"`` row in the response
    array rather than 502'ing the whole batch.

    Returns the joined payload:
      ``{symbol, recommendation_trends: [...], price_target: {...}|null}``

    Raises:
      - ``HTTPException(400)`` if the ticker fails the regex check.
        The batch route catches this and turns it into a per-ticker
        ``status="error"`` so a single invalid input doesn't nuke
        the whole batch.
      - ``HTTPException(500)`` if the API key is missing (operator
        misconfig; the batch route ALSO catches this per-ticker but
        the WHOLE-batch misconfig fires earlier -- see route).
      - ``HTTPException(502)`` if Finnhub upstream is degraded. Same
        catch strategy on the batch side.
    """
    if not _TICKER_RE.fullmatch(symbol):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticker must be 1-10 uppercase letters, digits, '.' or '-'.",
        )

    if symbol in _cache:
        logger.debug("Analyst ratings cache HIT for %s", symbol)
        return _cache[symbol]

    logger.info("Analyst ratings cache MISS for %s -- fetching upstream", symbol)

    # Two upstream calls in parallel via asyncio.gather would shave a
    # round-trip but complicates the test mock surface; sequential is
    # fine for an MVP (both are sub-second in practice).
    trends = await _fetch_finnhub(
        "stock/recommendation", {"symbol": symbol},
    )
    targets = await _fetch_finnhub(
        "stock/price-target", {"symbol": symbol},
    )

    # Finnhub returns price-target as a single object, NOT wrapped in
    # a list. We deliberately PICKLE the four fields the FE renders
    # instead of forwarding ``targets`` verbatim -- if Finnhub ever
    # drifts to an error-shape (``{"error": "throttled"}``) or adds
    # opaque internal fields (``lastUpdated``, etc.) the BE/UI
    # boundary stays stable and the FE's optional chaining doesn't
    # silently swallow an error response as "no consensus".
    price_target_payload: dict[str, Any] | None = None
    if isinstance(targets, dict):
        price_target_payload = {
            "targetHigh": targets.get("targetHigh"),
            "targetLow": targets.get("targetLow"),
            "targetMean": targets.get("targetMean"),
            "targetMedian": targets.get("targetMedian"),
        }
        # If every field is missing, treat as "no consensus yet" so the
        # FE can render an honest empty instead of four ``None``s.
        if all(v is None for v in price_target_payload.values()):
            price_target_payload = None

    payload: dict[str, Any] = {
        "symbol": symbol,
        "recommendation_trends": trends,
        "price_target": price_target_payload,
    }
    _cache[symbol] = payload
    return payload


@router.get("/{ticker}")
async def get_analyst_ratings(
    ticker: str = Path(..., min_length=1, max_length=10),
    _user: str = Depends(require_user),
) -> dict[str, Any]:
    """Fetch sell-side analyst consensus + price targets for a ticker.

    ``ticker`` is uppercased + regex-validated BEFORE lookup to ensure
    cache hits are case-insensitive (AAPL and aapl share the same
    cache entry) and that BRK.B / RDS-A shapes are accepted.

    Response shape mirrors the Finnhub upstream joined into a single
    object so the FE makes one round-trip:

    .. code-block:: json

       {
         "symbol": "AAPL",
         "recommendation_trends": [
           {"period": "2025-05", "strongBuy": 12, "buy": 18, "hold": 7, "sell": 1, "strongSell": 0},
           ...
         ],
         "price_target": {
           "targetMean": 232.10,
           "targetMedian": 230.00,
           "targetHigh": 280.00,
           "targetLow": 165.00
         }
       }
    """
    symbol = ticker.upper().strip()
    return await _get_single_rating(symbol)


# ------------------------------------------------------------------------
# Phase 42 -- POST /api/analyst-ratings/batch
# ------------------------------------------------------------------------
# Implements the "show analyst ratings on /portfolio" requirement without
# burning Finnhub's 60-calls/min free tier on a 10-ticker portfolio load:
#
#   * Up to 50 tickers per request (Pydantic cap).
#   * ``asyncio.Semaphore(5)`` caps *in-flight* upstream calls to 5 so a
#     50-ticker batch does NOT 50 simultaneous HTTP calls against Finnhub,
#     which would blow the upstream burst tolerance.
#   * Per-ticker errors are wrapped into ``{status: "error"}`` entries
#     rather than 502'ing the WHOLE batch on the first bad ticker --
#     the FE renders 1 uncovered row gracefully instead of failing 9
#     good rows. The partial-success contract is the friendlier behaviour
#     for a UI: a single 403/502/400 should not nuke the other 49.
#   * Shares the same ``_cache`` as the GET route, so the second visit
#     within 24h is essentially free (cache hit returns the cached
#     payload without upstream traffic).
# ------------------------------------------------------------------------


@router.post("/batch")
async def get_analyst_ratings_batch(
    request: BatchRatingsRequest,
    _user: str = Depends(require_user),
) -> BatchRatingsResponse:
    """Phase 42 -- batch fetch for the /portfolio coverage card + per-row
    chips.

    ``request.tickers`` is deduplicated + uppercased server-side so a FE
    that passes ``['aapl', 'AAPL', 'AAPL']`` makes 1 upstream call, not
    3. A cap of 50 per request protects against a runaway client
    blasting the queue (Finnhub's per-minute limit translates to a
    ceiling on what we can serve in one batch).

    The response shape ``{results: [{symbol, status, data?, error?}]}``
    preserves input order via the gather ordering so the FE can
    correlate positions without an extra ``id`` field.

    Errors per-ticker:
      * ``status='error'`` + ``error='<detail>'``: the helper raised
        HTTPException with that detail string (400 invalid ticker, 502
        upstream, 500 missing API key). The FE renders an honest
        "Uncovered" chip on these rows.
      * ``status='ok'`` + ``data={...}``: full payload.

    Whole-batch errors:
      * 422: Pydantic rejects the request body (oversized list, wrong
        type) before any work runs.
    """
    # Whole-batch operator-misconfig guard: surface as 500 (NOT 401 or
    # 502) so it ranges separately from the per-ticker errors that
    # show up as ``status='error'`` rows. The same 500-vs-502-vs-400
    # discipline as the GET route applies here -- a 422 here would
    # confuse the FE "banner vs chip" route. 422 is reserved for the
    # Pydantic-level "you sent garbage" path which gets the user a
    # legible "request body" error before any ticker resolves.
    api_key = (
        os.environ.get("FINNHUB_API_KEY") or settings.finnhub_api_key or ""
    ).strip()
    if not api_key:
        logger.error(
            "FINNHUB_API_KEY env var is unset or blank -- batch ratings "
            "endpoint is unable to serve any ticker."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analyst ratings service is not configured (missing API key).",
        )

    # Deduplicate + preserve first-seen order so the response array's
    # ordering matches the user's screen position on /portfolio.
    seen: set[str] = set()
    symbols: list[str] = []
    for raw in request.tickers:
        sym = raw.strip().upper()
        if not sym:
            continue
        if sym in seen:
            continue
        seen.add(sym)
        symbols.append(sym)

    semaphore = asyncio.Semaphore(5)

    async def fetch_one(symbol: str) -> BatchRatingsResultItem:
        # ``asyncio.Semaphore`` here is the *concurrency cap per batch*,
        # NOT a rate-limiter. The 24h cache + 60/min Finnhub free tier
        # means a repeated portfolio visit eats 0 upstream calls; a
        # cold start caps at 5 simultaneous HTTP calls regardless of
        # how many tickers the user requests (within the 50-item cap).
        async with semaphore:
            try:
                payload = await _get_single_rating(symbol)
                return BatchRatingsResultItem(
                    symbol=payload["symbol"],
                    status="ok",
                    data=payload,
                )
            except HTTPException as exc:
                # Per-ticker error envelope. The FE renders an
                # "Uncovered" chip instead of bubbling a global banner.
                return BatchRatingsResultItem(
                    symbol=symbol,
                    status="error",
                    error=str(exc.detail),
                )

    tasks = [fetch_one(s) for s in symbols]
    results = await asyncio.gather(*tasks)
    return BatchRatingsResponse(results=results)


def _clear_cache_for_tests() -> None:
    """Test-only helper: blank the TTLCache so the next request re-fetches.

    Tests need this because pytest test order isn't guaranteed and
    TTLCache hits across tests would silently skip the upstream
    monkeypatch's return value (causing bogus test failures).
    """
    _cache.clear()
