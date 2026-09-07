"""Atlas Daily Investment Brief (redesigned) — summary view over Market Intelligence data.

The brief is a scannable consumer surface over the SAME server-owned evidence
the Market Intelligence workspace renders (quotes, news, earnings, coverage).
It shares the configured ``TrustedMarketBriefComposer`` (see
``app.routes.market_briefs.get_market_brief_composer``), so:

- News and earnings populate from the same per-holding evidence pipeline
  (priority collection across holdings, rate-limit aware, source-cited).
- Coverage omissions (unsupported symbols, internal position labels, cash)
  are disclosed through the same coverage summary instead of silently
  returning an empty section.
- No parallel Finnhub rate budget is maintained here; the adapter's
  bounded cache keeps repeated brief loads cheap.

The response shape is unchanged from the redesigned UI contract
(``BriefSummary`` in ``ui/lib/marketBriefs.ts``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_user_id
from app.database import get_db
from app.models import Account, Holding
from app.market_intelligence.briefing import PositionInput
from app.market_intelligence.composition import MarketBriefCompositionError
from app.market_intelligence.contracts import (
    CompanyNewsItem,
    EarningsEvent,
    MarketBriefReasonCode,
    MarketQuoteSnapshot,
)
from app.routes.market_briefs import get_market_brief_composer, get_market_pulse_composer

logger = logging.getLogger(__name__)

router = APIRouter()

# Index ETF proxies for the market-context pills. Same proxies Market
# Intelligence uses for its pulse; adapter-cached, so three cheap calls.
INDEX_PROXIES = ("SPY", "QQQ", "VTI")

_MATERIALITY_WEIGHT = {"high": 1.0, "watch": 0.6, "informational": 0.3}


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _float(value: Any) -> Optional[float]:
    d = _decimal(value)
    return float(d) if d is not None else None


def _quarter_label(event_date: datetime) -> str:
    return f"Q{(event_date.month - 1) // 3 + 1} {event_date.year}"


def _error_detail(reason_code: MarketBriefReasonCode, omitted_symbols: tuple[str, ...] = ()) -> str:
    detail = f"Market data unavailable: {reason_code.value}."
    if omitted_symbols:
        detail += " Omitted symbols: " + ", ".join(sorted(omitted_symbols)[:10]) + "."
    return detail


def _portfolio_holdings(db: Session, user_id: int) -> tuple[set[str], list[str]]:
    """Return (all held symbols, top ~8 symbols by current value).

    Excludes cash rows and empty/internal position labels (the same
    exclusions the Market Intelligence composer applies).
    """
    rows = (
        db.query(Holding.symbol, Holding.current_value, Holding.type)
        .join(Account, Holding.account_id == Account.id)
        .filter(Account.user_id == user_id)
        .all()
    )
    entries: list[tuple[str, float]] = []
    for symbol, value, holding_type in rows:
        normalized = (symbol or "").strip().upper()
        if not normalized or (holding_type or "").lower() == "cash":
            continue
        entries.append((normalized, float(value or 0.0)))
    entries.sort(key=lambda item: (-item[1], item[0]))
    all_symbols = {symbol for symbol, _ in entries}
    top_symbols = [symbol for symbol, _ in entries[:8]]
    return all_symbols, top_symbols


def _index_changes(composer) -> dict[str, Optional[float]]:
    """Change percentages for the SPY/QQQ/VTI proxy quotes (best effort)."""
    changes: dict[str, Optional[float]] = {}
    for symbol in INDEX_PROXIES:
        try:
            quote: MarketQuoteSnapshot = composer.providers.quote(symbol)
            prev, cur = _float(quote.previous_close), _float(quote.current_price)
            changes[symbol] = ((cur - prev) / prev * 100.0) if (prev and cur and prev > 0) else None
        except Exception:  # noqa: BLE001 - an index pill failing must not kill the brief
            logger.warning("brief market-context quote failed for %s", symbol)
            changes[symbol] = None
    return changes


def _compose_brief(user_id: int, db: Session) -> dict[str, Any]:
    """Compose the brief summary JSON from the shared Market Intelligence pipeline."""
    composer = get_market_brief_composer()
    if composer is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Market data is not configured. Enable Market Intelligence "
                "(FINNHUB_API_KEY + SEC_USER_AGENT) to populate the daily brief."
            ),
        )

    now = datetime.now(timezone.utc)
    all_symbols, top_symbols = _portfolio_holdings(db, user_id)

    # ---- Market context pills (SPY / QQQ / VTI) - best effort -------
    index_changes = _index_changes(composer)
    market_context = {
        "spy_change": index_changes.get("SPY"),
        "qqq_change": index_changes.get("QQQ"),
        "vti_change": index_changes.get("VTI"),
        "market_sentiment": None,
    }

    # ---- Portfolio news + earnings: collected BEFORE the quote pass so the
    # free-tier rate budget (48 calls/min) cannot starve them. Bounded to the
    # top ~8 holdings by value; junk/internal symbols simply return nothing.
    collected_news: list[CompanyNewsItem] = []
    collected_earnings: list[EarningsEvent] = []
    for symbol in top_symbols:
        try:
            collected_news.extend(composer.providers.news(symbol) or [])
        except Exception:  # noqa: BLE001 - one symbol failing must not kill the brief
            logger.info("brief news unavailable for %s", symbol)
        try:
            collected_earnings.extend(composer.providers.earnings_events(symbol) or [])
        except Exception:  # noqa: BLE001
            logger.info("brief earnings unavailable for %s", symbol)

    # ---- Earnings horizon: 60 days captures the next reporting wave (the
    # free-tier calendar returns per-symbol next-earnings dates, which for
    # large caps cluster 4-10 weeks out). The market-wide calendar (single
    # call on the pulse provider's own adapter) adds any held symbols that
    # happen to report in the window.
    window_end = now + timedelta(days=60)
    pulse = get_market_pulse_composer()
    calendar_events: list[EarningsEvent] = []
    if pulse is not None:
        try:
            calendar_events = pulse.providers.market_earnings_calendar(
                from_date=now.date().isoformat(),
                to_date=window_end.date().isoformat(),
            )
        except Exception:  # noqa: BLE001
            calendar_events = []
    held_calendar_events = [event for event in calendar_events if event.symbol in all_symbols]

    try:
        assembled = composer.assemble(db, owner_id=user_id, report_window="latest")
    except MarketBriefCompositionError as error:
        raise HTTPException(
            status_code=503,
            detail=_error_detail(error.reason_code, error.omitted_symbols),
        ) from error
    except Exception as error:  # noqa: BLE001 - sanitize the composition boundary
        logger.warning("bounded brief composition failure: %s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail=_error_detail(MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE),
        ) from error

    # ---- Hero: daily P&L + top movers from server-owned positions ----
    name_by_symbol = {
        packet.symbol: (packet.profile.company_name if packet.profile and packet.profile.company_name else packet.symbol)
        for packet in assembled.holding_evidence
    }
    materiality_by_symbol = {
        packet.symbol: _MATERIALITY_WEIGHT.get(packet.materiality, 0.3)
        for packet in assembled.holding_evidence
    }

    movers: list[dict[str, Any]] = []
    total_value = Decimal(0)
    daily_pnl = Decimal(0)
    for position in assembled.positions:
        if position.is_cash:
            continue
        quantity = _decimal(position.quantity)
        current = _decimal(position.current_price)
        previous = _decimal(position.previous_close)
        if quantity is None or current is None or previous is None or quantity < 0 or current <= 0 or previous <= 0:
            continue
        change_dollar = quantity * (current - previous)
        change_pct = (current - previous) / previous * Decimal(100)
        value = _decimal(position.current_value)
        if value is None:
            value = quantity * current
        total_value += value
        daily_pnl += change_dollar
        movers.append(
            {
                "symbol": position.symbol,
                "name": name_by_symbol.get(position.symbol, position.symbol),
                "change_pct": float(change_pct),
                "change_dollar": float(change_dollar),
                "current_price": float(current),
                "materiality": "informational",
                "value": float(value),
            }
        )

    daily_pct = float(daily_pnl / total_value * Decimal(100)) if total_value else 0.0

    def _mover_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": row["symbol"],
            "name": row["name"],
            "change_pct": row["change_pct"],
            "change_dollar": row["change_dollar"],
            "current_price": row["current_price"],
            "materiality": "high" if abs(row["change_pct"]) >= 3.0 else ("watch" if abs(row["change_pct"]) >= 1.0 else "informational"),
        }

    top_gainer: Optional[dict[str, Any]] = None
    top_loser: Optional[dict[str, Any]] = None
    nonzero = [row for row in movers if row["change_pct"] != 0.0]
    pick_from = nonzero or movers
    if pick_from:
        gainer = max(pick_from, key=lambda row: row["change_pct"])
        loser = min(pick_from, key=lambda row: row["change_pct"])
        top_gainer = _mover_payload(gainer)
        top_loser = _mover_payload(loser)

    # ---- News: route-collected portfolio news merged with whatever the
    # composer's optional pass also captured (rate-permitting), deduped.
    news_by_symbol: dict[str, list[CompanyNewsItem]] = {}
    for item in [*collected_news, *assembled.news]:
        news_by_symbol.setdefault(item.symbol, []).append(item)

    ranked_news: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for symbol, items in news_by_symbol.items():
        base = materiality_by_symbol.get(symbol, 0.3)
        for item in items:
            url = item.source.source_url or ""
            if url and url in seen_urls:
                continue
            seen_urls.add(url)
            published_at = item.source.published_at or now
            hours_old = max(0.0, (now - published_at).total_seconds() / 3600)
            recency = max(0.0, 1.0 - hours_old / (7 * 24))  # decay over 7 days
            ranked_news.append(
                {
                    "id": str(uuid4()),
                    "symbols": [item.symbol],
                    "headline": item.headline,
                    "summary": item.summary or "",
                    "source": item.publisher or "Unknown",
                    "published_at": published_at.isoformat(),
                    "url": url,
                    "materiality_score": round(base * 0.7 + recency * 0.3, 4),
                }
            )
    ranked_news.sort(key=lambda item: item["materiality_score"], reverse=True)
    ranked_news = ranked_news[:5]

    # ---- Earnings: upcoming events within the horizon, from per-holding
    # collection + market-wide calendar + the composer's events, deduped.
    merged_earnings = [*collected_earnings, *held_calendar_events, *assembled.earnings_events]
    deduped: dict[tuple[str, datetime], EarningsEvent] = {}
    for event in merged_earnings:
        if now - timedelta(days=1) <= event.event_date <= window_end:
            deduped.setdefault((event.symbol, event.event_date), event)
    upcoming_earnings = sorted(deduped.values(), key=lambda event: event.event_date)
    earnings: list[dict[str, Any]] = [
        {
            "symbol": event.symbol,
            "name": name_by_symbol.get(event.symbol, event.symbol),
            "date": event.event_date.isoformat(),
            "eps_estimate": None,
            "eps_whisper": None,
            "confidence": "low",
            "quarter": _quarter_label(event.event_date),
            "previous_eps": None,
        }
        for event in upcoming_earnings[:5]
    ]

    # ---- Quality: coverage + warnings disclosed exactly like Market Intelligence ----
    coverage = assembled.coverage
    omission_warnings = [
        f"{omission.symbol}: {omission.reason_code.value}."
        for omission in (coverage.omissions if coverage else ())
    ]
    warnings = list(assembled.composition_warnings) + omission_warnings
    freshness = "fresh" if not warnings else "partial"

    quality = {
        "freshness": freshness,
        "coverage_eligible": coverage.eligible_holding_count if coverage else 0,
        "coverage_covered": coverage.covered_holding_count if coverage else 0,
        "coverage_basis": coverage.coverage_basis.value if coverage else "unknown",
        "warnings": warnings,
    }

    top_movers = sorted(movers, key=lambda row: -abs(row["change_dollar"]))[:5]
    top_movers_payload = [_mover_payload(row) for row in top_movers]

    hero = {
        "daily_pnl": float(daily_pnl),
        "daily_pct": daily_pct,
        "ytd_pnl": 0.0,
        "ytd_pct": 0.0,
        "top_gainer": top_gainer,
        "top_loser": top_loser,
        "market_context": market_context,
        "updated_at": now.isoformat(),
    }

    return {
        "id": str(uuid4()),
        "hero": hero,
        "market": market_context,
        "top_movers": top_movers_payload,
        "news": ranked_news,
        "earnings": earnings,
        "alerts": [],
        "quality": quality,
        "generated_at": now.isoformat(),
        "warnings": warnings,
    }


@router.get("/summary")
def get_brief_summary(
    user_id: int = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Compose the daily brief summary from Market Intelligence evidence."""
    return JSONResponse(content=_compose_brief(user_id, db))


@router.get("/news")
def get_brief_news(
    limit: int = Query(default=5, ge=1, le=10),
    user_id: int = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Top material news for the portfolio (same evidence as the summary)."""
    brief = _compose_brief(user_id, db)
    return JSONResponse(content=brief["news"][:limit])


@router.get("/earnings")
def get_brief_earnings(
    days: int = Query(default=30, ge=1, le=60),
    user_id: int = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Upcoming earnings events for the portfolio (same evidence as the summary)."""
    brief = _compose_brief(user_id, db)
    return JSONResponse(content=brief["earnings"][:days])


@router.get("/alerts")
def get_brief_alerts(
    user_id: int = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Portfolio alerts (currently none; Market Intelligence owns catalysts)."""
    return JSONResponse(content=[])


@router.post("/refresh")
def refresh_brief_summary(
    user_id: int = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Force a fresh composition of the daily brief."""
    return JSONResponse(content=_compose_brief(user_id, db))