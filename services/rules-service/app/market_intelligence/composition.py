"""Trusted server-only market brief input assembly; no client financial payloads."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.holding import Holding
from .adapters import FinnhubAdapter, ProviderConfigurationError, SecAdapter
from .briefing import BriefingInput, PositionInput
from .contracts import (
    AnalystRecommendation,
    CompanyNewsItem,
    CompanyProfile,
    CoverageBasis,
    CoverageOmission,
    CoverageSummary,
    DividendEvent,
    EarningsEvent,
    EarningsResult,
    EvidenceAvailability,
    EvidenceCategory,
    FailureClass,
    Freshness,
    HoldingEvidence,
    MarketBriefReasonCode,
    MarketQuoteSnapshot,
    PortfolioHolding,
    PriceBasis,
    PriceTarget,
    ProviderReadiness,
    SecFilingEvent,
)

_FAILURE_REASON_CODES = {
    FailureClass.UNCONFIGURED: MarketBriefReasonCode.PROVIDER_CONFIGURATION_MISSING,
    FailureClass.TIMEOUT: MarketBriefReasonCode.PROVIDER_TRANSPORT_FAILURE,
    FailureClass.UPSTREAM: MarketBriefReasonCode.PROVIDER_TRANSPORT_FAILURE,
    FailureClass.AUTHENTICATION_FAILED: MarketBriefReasonCode.PROVIDER_AUTHENTICATION_FAILED,
    FailureClass.RATE_LIMITED: MarketBriefReasonCode.PROVIDER_RATE_LIMITED,
    FailureClass.NOT_FOUND: MarketBriefReasonCode.UNSUPPORTED_SYMBOL,
    FailureClass.INVALID_PAYLOAD: MarketBriefReasonCode.INVALID_QUOTE,
    FailureClass.INVALID_QUOTE: MarketBriefReasonCode.INVALID_QUOTE,
    FailureClass.STALE: MarketBriefReasonCode.LIVE_QUOTE_STALE,
}

_SAFE_FAILURE_MESSAGES = {
    MarketBriefReasonCode.PROVIDER_CONFIGURATION_MISSING: "Market data configuration is incomplete.",
    MarketBriefReasonCode.PROVIDER_TRANSPORT_FAILURE: "The market-data provider could not be reached.",
    MarketBriefReasonCode.PROVIDER_AUTHENTICATION_FAILED: "The market-data provider rejected its server-side credentials.",
    MarketBriefReasonCode.PROVIDER_RATE_LIMITED: "The market-data provider is rate limiting requests.",
    MarketBriefReasonCode.UNSUPPORTED_SYMBOL: "This holding is not supported by the configured market-data provider.",
    MarketBriefReasonCode.INVALID_QUOTE: "The market-data provider returned an invalid quote.",
}

# User-safe recovery guidance per reason code, shared by omissions and the
# evidence-availability records. Never raw provider text or secrets.
_SAFE_RECOVERY_GUIDANCE = {
    MarketBriefReasonCode.PROVIDER_CONFIGURATION_MISSING: "Ask the local operator to configure market data, then retry.",
    MarketBriefReasonCode.PROVIDER_TRANSPORT_FAILURE: "Check the provider connection and retry later.",
    MarketBriefReasonCode.PROVIDER_AUTHENTICATION_FAILED: "Ask the local operator to verify server-side provider credentials.",
    MarketBriefReasonCode.PROVIDER_RATE_LIMITED: "Wait briefly, then retry.",
    MarketBriefReasonCode.UNSUPPORTED_SYMBOL: "Review the holding symbol and correct it before retrying.",
    MarketBriefReasonCode.INVALID_QUOTE: "Ask the local operator to verify the provider response, then retry.",
    MarketBriefReasonCode.LIVE_QUOTE_STALE: "Retry during market hours or use the accepted prior-close mode outside the session.",
    MarketBriefReasonCode.PRIOR_CLOSE_TOO_OLD: "Refresh provider data before generating another brief.",
    MarketBriefReasonCode.INSUFFICIENT_PORTFOLIO_COVERAGE: "Review the disclosed omitted holdings; covered holdings are briefed with their own evidence.",
    MarketBriefReasonCode.NO_MARKET_ADDRESSABLE_HOLDINGS: "Add or correct an eligible holding before generating a brief.",
    MarketBriefReasonCode.AMBIGUOUS_CURRENCY: "Resolve the portfolio currency ambiguity before generating a brief.",
    MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE: "Retry after the local operator resolves the reported readiness issue.",
}


class MarketBriefCompositionError(ValueError):
    """A server-owned market input was incomplete or not safe to brief."""

    def __init__(
        self,
        message: str,
        reason_code: MarketBriefReasonCode = MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE,
        omitted_symbols: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        # Bounded, sanitized symbols that the provider could not address.
        # Carried on the error so the API can tell the user WHICH holdings
        # blocked the brief instead of a dead "review the coverage details".
        self.omitted_symbols = omitted_symbols


class OperationalMarketResearchProviders:
    """Narrow, server-owned adapter composition for the operational route."""

    def __init__(
        self,
        *,
        finnhub_api_key: str,
        sec_user_agent: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._finnhub = FinnhubAdapter(api_key=finnhub_api_key, enabled=True, now=self._now)
        self._sec = SecAdapter(user_agent=sec_user_agent, enabled=True, now=self._now)

    @staticmethod
    def _value(result, label: str):
        if result.value is not None:
            return result.value
        failure = result.failure
        reason_code = _FAILURE_REASON_CODES.get(
            failure.failure_class if failure else FailureClass.UPSTREAM,
            MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE,
        )
        raise MarketBriefCompositionError(
            _SAFE_FAILURE_MESSAGES.get(reason_code, f"{label} is unavailable."),
            reason_code,
        )

    def quote(self, symbol: str) -> MarketQuoteSnapshot:
        return self._value(self._finnhub.quote(symbol), "Market quote")

    def news(self, symbol: str) -> list[CompanyNewsItem]:
        today = self._now().date()
        return self._value(
            self._finnhub.company_news(
                symbol,
                from_date=(today - timedelta(days=14)).isoformat(),
                to_date=today.isoformat(),
            ),
            "Market news",
        )

    def earnings_events(self, symbol: str) -> list[EarningsEvent]:
        return self._value(self._finnhub.earnings_calendar(symbol), "Earnings calendar")

    def earnings_results(self, symbol: str) -> list[EarningsResult]:
        return self._value(self._finnhub.earnings_surprises(symbol), "Earnings results")

    def profile(self, symbol: str) -> CompanyProfile:
        return self._value(self._finnhub.company_profile(symbol), "Company profile")

    def analyst_recommendations(self, symbol: str) -> list[AnalystRecommendation]:
        return self._value(self._finnhub.analyst_recommendation(symbol), "Analyst recommendation")

    def price_target(self, symbol: str) -> PriceTarget | None:
        return self._value(self._finnhub.price_target(symbol), "Analyst price target")

    def dividends(self, symbol: str) -> list[DividendEvent]:
        return self._value(self._finnhub.dividends(symbol), "Dividends")

    def filings_for_cik(self, cik: str) -> list[SecFilingEvent]:
        """SEC submissions for one resolved CIK; a bad CIK is an omission."""
        result = self._sec.submissions(cik)
        if result.value:
            return result.value
        return []

    def filings(self) -> list[SecFilingEvent]:
        """Backward-compatible aggregate for the v1 protocol (empty by default)."""
        return []


def build_operational_market_brief_composer(settings: object) -> "TrustedMarketBriefComposer | None":
    """Build only when all server-owned rollout/configuration gates are true."""
    if not (
        getattr(settings, "atlas_market_brief_generation_enabled", False)
        and getattr(settings, "atlas_market_brief_external_provider_enabled", False)
    ):
        return None
    api_key = (getattr(settings, "finnhub_api_key", None) or "").strip()
    sec_user_agent = (getattr(settings, "sec_user_agent", None) or "").strip()
    if not api_key or not sec_user_agent:
        return None
    try:
        return TrustedMarketBriefComposer(
            OperationalMarketResearchProviders(
                finnhub_api_key=api_key,
                sec_user_agent=sec_user_agent,
            )
        )
    except ProviderConfigurationError:
        return None


class MarketResearchProviders(Protocol):
    def quote(self, symbol: str) -> MarketQuoteSnapshot | None: ...
    def news(self, symbol: str) -> list[CompanyNewsItem]: ...
    def earnings_events(self, symbol: str) -> list[EarningsEvent]: ...
    def earnings_results(self, symbol: str) -> list[EarningsResult]: ...
    def filings(self) -> list[SecFilingEvent]: ...
    def profile(self, symbol: str) -> CompanyProfile: ...
    def analyst_recommendations(self, symbol: str) -> list[AnalystRecommendation]: ...
    def price_target(self, symbol: str) -> PriceTarget | None: ...
    def dividends(self, symbol: str) -> list[DividendEvent]: ...
    def filings_for_cik(self, cik: str) -> list[SecFilingEvent]: ...


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _canonical(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _hash(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TrustedMarketBriefComposer:
    def __init__(self, providers: MarketResearchProviders, *, now: Callable[[], datetime] | None = None) -> None:
        self.providers = providers
        self._now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _quote_basis(quote: MarketQuoteSnapshot) -> PriceBasis:
        if quote.source.price_basis is not PriceBasis.UNKNOWN:
            return quote.source.price_basis
        if quote.source.freshness is Freshness.FRESH:
            return PriceBasis.LIVE
        return PriceBasis.UNUSABLE

    @classmethod
    def _validate_quote(cls, quote: MarketQuoteSnapshot) -> PriceBasis:
        basis = cls._quote_basis(quote)
        if quote.source.freshness is not Freshness.FRESH:
            reason = (
                MarketBriefReasonCode.PRIOR_CLOSE_TOO_OLD
                if basis is PriceBasis.PRIOR_CLOSE
                else MarketBriefReasonCode.LIVE_QUOTE_STALE
            )
            raise MarketBriefCompositionError(_SAFE_FAILURE_MESSAGES.get(reason, reason.value), reason)
        if basis not in {PriceBasis.LIVE, PriceBasis.PRIOR_CLOSE}:
            raise MarketBriefCompositionError("The market-data quote basis was not usable.", MarketBriefReasonCode.INVALID_QUOTE)
        if basis is PriceBasis.PRIOR_CLOSE and quote.previous_close is None:
            raise MarketBriefCompositionError("The accepted prior close was incomplete.", MarketBriefReasonCode.INVALID_QUOTE)
        if quote.source.observed_at is None or quote.source.observed_at > quote.source.retrieved_at:
            raise MarketBriefCompositionError("The market-data timestamp was invalid.", MarketBriefReasonCode.INVALID_QUOTE)
        return basis

    @classmethod
    def _rank_evidence(
        cls,
        *,
        symbol: str,
        quote: MarketQuoteSnapshot | None,
        profile: CompanyProfile | None,
        news: tuple[CompanyNewsItem, ...],
        earnings_events: tuple[EarningsEvent, ...],
        earnings_results: tuple[EarningsResult, ...],
        filings: tuple[SecFilingEvent, ...],
        recommendations: tuple[AnalystRecommendation, ...],
        price_target: PriceTarget | None,
        dividends: tuple[DividendEvent, ...],
        now: datetime,
    ) -> HoldingEvidence:
        """Deterministic, evidence-only materiality ranking.

        Ranks the packet High impact / Watch / Informational using only
        bounded evidence windows and price movement. It never fabricates a
        reason, never predicts a move, and never becomes a trade instruction.
        """
        materiality: Literal["high", "watch", "informational"] = "informational"
        reason: str | None = None
        today = now.date()

        upcoming = [event for event in earnings_events if event.event_date.date() >= today]
        reported = [event for event in earnings_events if event.event_date.date() < today]
        fresh_results = [r for r in earnings_results if r.source.observed_at and r.source.observed_at.date() >= today - timedelta(days=14)]
        fresh_filings = [f for f in filings if f.filing_date.date() >= today - timedelta(days=14)]
        fresh_dividends = [d for d in dividends if (d.ex_date or d.declared_date or d.payable_date) is not None]

        if upcoming and (upcoming[0].event_date.date() - today).days <= 7:
            materiality = "high"
            reason = f"Earnings on {upcoming[0].event_date.date().isoformat()} within 7 days."
        elif fresh_results and reported:
            materiality = "high"
            reason = f"Recent earnings reported for {symbol}."
        elif any(f.form == "8-K" for f in fresh_filings):
            materiality = "high"
            reason = "Recent 8-K filing."
        elif fresh_results:
            materiality = "watch"
            reason = "Recent earnings result in window."
        elif fresh_filings:
            materiality = "watch"
            reason = "Recent SEC filing in window."
        elif recommendations and len(recommendations) >= 2:
            latest, prior = recommendations[0], recommendations[1]
            delta = abs((latest.strong_buy + latest.buy) - (prior.strong_buy + prior.buy)) + abs((latest.sell + latest.strong_sell) - (prior.sell + prior.strong_sell))
            if delta > 0:
                materiality = "watch"
                reason = "Analyst recommendation mix changed."

        if quote and quote.previous_close:
            previous = _decimal(quote.previous_close)
            current = _decimal(quote.current_price)
            if previous and current and previous > 0:
                movement = (current - previous) / previous
                if abs(movement) >= Decimal("0.03") and materiality != "high":
                    materiality = "watch"
                    reason = "Price moved more than 3% in the session."

        if materiality == "informational" and (fresh_dividends or news):
            reason = reason or ("Dividend event in window." if fresh_dividends else "News activity.")

        return HoldingEvidence(
            symbol=symbol,
            quote=quote,
            profile=profile,
            news=news,
            earnings_events=earnings_events,
            earnings_results=earnings_results,
            filings=filings,
            recommendations=recommendations,
            price_target=price_target,
            dividends=dividends,
            materiality=materiality,
            materiality_reason=reason,
        )

    @staticmethod
    def _coverage(
        eligible: list[Holding],
        covered: list[Holding],
        omissions: list[CoverageOmission],
    ) -> CoverageSummary:
        values = [_decimal(holding.current_value) for holding in eligible]
        use_value_basis = all(value is not None and value >= 0 for value in values) and sum(values, Decimal(0)) > 0
        if use_value_basis:
            total = sum((_decimal(holding.current_value) or Decimal(0) for holding in eligible), Decimal(0))
            covered_ids = {id(holding) for holding in covered}
            covered_value = sum(
                (_decimal(holding.current_value) or Decimal(0) for holding in eligible if id(holding) in covered_ids),
                Decimal(0),
            )
            percentage = covered_value / total if total else Decimal(0)
            basis = CoverageBasis.VALUE_WEIGHTED
        else:
            percentage = Decimal(len(covered)) / Decimal(len(eligible)) if eligible else Decimal(0)
            basis = CoverageBasis.POSITION_COUNT
        ordered_omissions = tuple(sorted(omissions, key=lambda item: (item.symbol, item.reason_code.value)))
        return CoverageSummary(
            eligible_holding_count=len(eligible),
            covered_holding_count=len(covered),
            omitted_holding_count=len(eligible) - len(covered),
            coverage_basis=basis,
            coverage_percentage=_canonical(percentage),
            omitted_symbols=tuple(sorted({item.symbol for item in ordered_omissions})),
            omissions=ordered_omissions,
        )

    def assemble(self, session: Session, *, owner_id: int, report_window: str) -> BriefingInput:
        holdings = session.scalars(
            select(Holding)
            .join(Account)
            .where(Account.user_id == owner_id, Account.is_active.is_(True))
            .order_by(Holding.symbol.asc(), Holding.id.asc())
        ).all()
        eligible = [holding for holding in holdings if (holding.type or "").lower() != "cash"]
        if not eligible:
            raise MarketBriefCompositionError(
                "No active, market-addressable portfolio holdings are available.",
                MarketBriefReasonCode.NO_MARKET_ADDRESSABLE_HOLDINGS,
            )

        quotes: dict[str, MarketQuoteSnapshot | None] = {}
        quote_errors: dict[str, MarketBriefReasonCode] = {}
        covered: list[Holding] = []
        omissions: list[CoverageOmission] = []
        covered_by_symbol: dict[str, MarketQuoteSnapshot] = {}
        for holding in eligible:
            symbol = (holding.symbol or "").strip().upper()
            if not symbol:
                omissions.append(CoverageOmission(
                    symbol="UNKNOWN",
                    evidence_category=EvidenceCategory.QUOTE,
                    reason_code=MarketBriefReasonCode.UNSUPPORTED_SYMBOL,
                    recovery=_SAFE_RECOVERY_GUIDANCE[MarketBriefReasonCode.UNSUPPORTED_SYMBOL],
                ))
                continue
            # Imported portfolios can contain human-readable pending-activity
            # labels in the symbol column. Treat those as non-addressable
            # holdings before calling the provider; never let an unbounded
            # database label violate the bounded omission contract or escape
            # into an external request.
            try:
                normalized_symbol = PortfolioHolding(symbol=symbol, instrument_type="equity").symbol
            except (TypeError, ValueError):
                normalized_symbol = None
            if not normalized_symbol:
                omissions.append(CoverageOmission(
                    symbol="UNKNOWN",
                    evidence_category=EvidenceCategory.QUOTE,
                    reason_code=MarketBriefReasonCode.UNSUPPORTED_SYMBOL,
                    recovery=_SAFE_RECOVERY_GUIDANCE[MarketBriefReasonCode.UNSUPPORTED_SYMBOL],
                ))
                continue
            symbol = normalized_symbol
            if symbol not in quotes and symbol not in quote_errors:
                try:
                    quote = self.providers.quote(symbol)
                    if quote is None:
                        raise MarketBriefCompositionError(
                            "This holding is not supported by the configured market-data provider.",
                            MarketBriefReasonCode.UNSUPPORTED_SYMBOL,
                        )
                    self._validate_quote(quote)
                    quotes[symbol] = quote
                    covered_by_symbol[symbol] = quote
                except MarketBriefCompositionError as error:
                    quote_errors[symbol] = error.reason_code
            if symbol in quote_errors:
                omissions.append(CoverageOmission(
                    symbol=symbol,
                    evidence_category=EvidenceCategory.QUOTE,
                    reason_code=quote_errors[symbol],
                    recovery=_SAFE_RECOVERY_GUIDANCE.get(quote_errors[symbol]),
                ))
            else:
                covered.append(holding)

        coverage = self._coverage(eligible, covered, omissions)
        omitted_symbols = tuple(
            sorted({item.symbol for item in omissions if item.symbol != "UNKNOWN"})
        )
        if coverage.covered_holding_count == 0:
            # Preserve the actionable provider boundary when every
            # non-empty symbol was rejected as unsupported. The old
            # generic no-priced-holdings code hid the distinction
            # between an empty portfolio and symbols Finnhub cannot
            # address (for example, fund or internal position labels).
            only_unsupported_symbols = bool(omissions) and all(
                omission.reason_code is MarketBriefReasonCode.UNSUPPORTED_SYMBOL
                for omission in omissions
            )
            if only_unsupported_symbols:
                raise MarketBriefCompositionError(
                    "No eligible holding is supported by the configured market-data provider.",
                    MarketBriefReasonCode.UNSUPPORTED_SYMBOL,
                    omitted_symbols,
                )
            raise MarketBriefCompositionError(
                "No trustworthy priced holdings remain for this brief.",
                MarketBriefReasonCode.NO_MARKET_ADDRESSABLE_HOLDINGS,
                omitted_symbols,
            )
        # Partial-coverage briefs are allowed. The coverage summary and the
        # briefing renderer disclose every omission with its stable reason
        # code (``CoveragePanel``/``data_quality`` sections), so the brief
        # never fabricates evidence for holdings the provider cannot price.
        # Provider-level failures (config, transport, auth, rate limit) and
        # currency ambiguity still fail closed above.

        currencies = {covered_by_symbol[(holding.symbol or "").strip().upper()].currency for holding in covered}
        if len(currencies) != 1:
            raise MarketBriefCompositionError(
                "Portfolio currency is ambiguous.",
                MarketBriefReasonCode.AMBIGUOUS_CURRENCY,
            )

        positions: list[PositionInput] = []
        grouped: dict[str, list[Holding]] = {}
        for holding in covered:
            grouped.setdefault((holding.symbol or "").strip().upper(), []).append(holding)
        basis_values: set[PriceBasis] = set()
        for symbol in sorted(grouped):
            quote = covered_by_symbol[symbol]
            basis = self._quote_basis(quote)
            basis_values.add(basis)
            matching = grouped[symbol]
            quantities = [_decimal(item.quantity) for item in matching]
            quantity = _canonical(sum(quantities, Decimal(0))) if all(value is not None for value in quantities) else None
            values = [_decimal(item.current_value) for item in matching]
            current_value = _canonical(sum((value or Decimal(0) for value in values), Decimal(0))) if all(value is not None for value in values) else None
            positions.append(
                PositionInput(
                    symbol=symbol,
                    quantity=quantity,
                    current_price=quote.current_price,
                    previous_close=quote.previous_close,
                    currency=quote.currency,
                    source=quote.source,
                    freshness=quote.source.freshness,
                    price_basis=basis,
                    current_value=current_value,
                )
            )

        # ---- Per-holding intelligence packets (Market Intelligence v2) ----
        # Every optional evidence category is best-effort: a failure is a
        # per-holding per-category availability record, never a brief-killer.
        optional_warnings: list[str] = []
        evidence_availability: list[EvidenceAvailability] = []
        news: list[CompanyNewsItem] = []
        earnings_events: list[EarningsEvent] = []
        earnings_results: list[EarningsResult] = []
        now = self._now()
        resolved_ciks: dict[str, str] = {}
        holding_evidence: list[HoldingEvidence] = []

        # Provider rate limiting is a provider-wide condition, not a
        # per-holding one. Once any optional call observes it, the remaining
        # optional calls are guaranteed to fail too (the pacer ceiling is
        # shared, and upstream 429s persist). Issuing them anyway burns quota
        # and produces one near-identical warning per holding per category.
        # Fail fast: stop optional collection and emit ONE aggregated warning
        # so a rate-limited brief degrades gracefully instead of flooding the
        # limitations panel.
        rate_limited = False

        def _collect(label: str, category: EvidenceCategory, loader, target, symbol: str) -> None:
            nonlocal rate_limited
            if rate_limited:
                return
            try:
                records = loader(symbol)
                if label == "news":
                    target.extend((records or [])[:20])
                elif label == "earnings_events":
                    # Upcoming earnings window: the next reported quarter
                    # (typically 30-90 days out). The lower bound keeps a small
                    # recency cushion for events that land within a couple of
                    # weeks of composition.
                    target.extend(
                        event for event in (records or [])
                        if now.date() - timedelta(days=14) <= event.event_date.date() <= now.date() + timedelta(days=90)
                    )
                else:
                    # Reported results are keyed on the period END (e.g. the
                    # quarter-end 2026-06-30), which is already weeks old when
                    # the provider publishes it. A 14-day window silently
                    # discards every quarterly result; keep the trailing four
                    # quarters so recent reported results are actually shown.
                    target.extend(
                        result for result in (records or [])
                        if result.source.observed_at
                        and now.date() - timedelta(days=365) <= result.source.observed_at.date() <= now.date()
                    )
            except MarketBriefCompositionError as error:
                if error.reason_code is MarketBriefReasonCode.PROVIDER_RATE_LIMITED:
                    rate_limited = True
                    return
                evidence_availability.append(EvidenceAvailability(
                    symbol=symbol,
                    evidence_category=category,
                    reason_code=error.reason_code,
                    recovery=_SAFE_RECOVERY_GUIDANCE.get(error.reason_code),
                ))
                optional_warnings.append(f"{error.reason_code.value}: optional {label} unavailable for {symbol}.")

        # Two-pass optional collection. The shared provider budget is far
        # smaller than the call volume a full portfolio demands (free-tier
        # Finnhub ~48 calls/min vs. ~8 optional calls per holding), so once
        # the ceiling trips, the burst-stop would otherwise discard everything
        # after the first failure. The UI renders news and earnings (the
        # Earnings & Events tab and material-news packets), so those are
        # collected FIRST across all holdings; enrichment extras (analyst
        # mix, price target, dividends, SEC filings) run second with whatever
        # budget remains.
        priority_symbols = sorted(grouped)

        for symbol in priority_symbols:
            if rate_limited:
                break
            _collect("news", EvidenceCategory.NEWS, self.providers.news, news, symbol)
            _collect("earnings_events", EvidenceCategory.EARNINGS, self.providers.earnings_events, earnings_events, symbol)
            _collect("earnings_results", EvidenceCategory.EARNINGS, self.providers.earnings_results, earnings_results, symbol)
            holding_evidence.append(self._rank_evidence(
                symbol=symbol,
                quote=covered_by_symbol.get(symbol),
                profile=None,
                news=tuple(item for item in news if item.symbol == symbol)[:10],
                earnings_events=tuple(event for event in earnings_events if event.symbol == symbol),
                earnings_results=tuple(result for result in earnings_results if result.symbol == symbol),
                filings=(),
                recommendations=(),
                price_target=None,
                dividends=(),
                now=now,
            ))

        # Enrichment pass: profile/analyst/price-target/dividends/filings are
        # best-effort additions to the priority packets. A rate limit here
        # stops only this pass — the news/earnings evidence already collected
        # in the priority pass is preserved.
        for index, symbol in enumerate(priority_symbols):
            if rate_limited:
                break
            profile: CompanyProfile | None = None
            recommendations: tuple[AnalystRecommendation, ...] = ()
            price_target: PriceTarget | None = None
            dividends: tuple[DividendEvent, ...] = ()
            filings: tuple[SecFilingEvent, ...] = ()

            try:
                profile = self.providers.profile(symbol)
                if profile and profile.cik:
                    resolved_ciks[symbol] = profile.cik
            except MarketBriefCompositionError as error:
                if error.reason_code is MarketBriefReasonCode.PROVIDER_RATE_LIMITED:
                    rate_limited = True
                else:
                    evidence_availability.append(EvidenceAvailability(
                        symbol=symbol, evidence_category=EvidenceCategory.FILINGS,
                        reason_code=error.reason_code, recovery=_SAFE_RECOVERY_GUIDANCE.get(error.reason_code),
                    ))
                    optional_warnings.append(f"{error.reason_code.value}: optional profile unavailable for {symbol}.")

            if not rate_limited:
                try:
                    recommendations = tuple(self.providers.analyst_recommendations(symbol))
                except MarketBriefCompositionError as error:
                    if error.reason_code is MarketBriefReasonCode.PROVIDER_RATE_LIMITED:
                        rate_limited = True
                    else:
                        evidence_availability.append(EvidenceAvailability(
                            symbol=symbol, evidence_category=EvidenceCategory.ANALYST,
                            reason_code=error.reason_code, recovery=_SAFE_RECOVERY_GUIDANCE.get(error.reason_code),
                        ))
                        optional_warnings.append(f"{error.reason_code.value}: optional analyst recommendation unavailable for {symbol}.")

            if not rate_limited:
                try:
                    price_target = self.providers.price_target(symbol)
                except MarketBriefCompositionError as error:
                    if error.reason_code is MarketBriefReasonCode.PROVIDER_RATE_LIMITED:
                        rate_limited = True
                    else:
                        evidence_availability.append(EvidenceAvailability(
                            symbol=symbol, evidence_category=EvidenceCategory.ANALYST,
                            reason_code=error.reason_code, recovery=_SAFE_RECOVERY_GUIDANCE.get(error.reason_code),
                        ))
                        optional_warnings.append(f"{error.reason_code.value}: optional price target unavailable for {symbol}.")

            if not rate_limited:
                try:
                    dividends = tuple(self.providers.dividends(symbol))
                except MarketBriefCompositionError as error:
                    if error.reason_code is MarketBriefReasonCode.PROVIDER_RATE_LIMITED:
                        rate_limited = True
                    else:
                        evidence_availability.append(EvidenceAvailability(
                            symbol=symbol, evidence_category=EvidenceCategory.NEWS,
                            reason_code=error.reason_code, recovery=_SAFE_RECOVERY_GUIDANCE.get(error.reason_code),
                        ))
                        optional_warnings.append(f"{error.reason_code.value}: optional dividends unavailable for {symbol}.")

            if not rate_limited and profile and profile.cik:
                try:
                    filings = tuple(self.providers.filings_for_cik(profile.cik))[:10]
                except MarketBriefCompositionError as error:
                    if error.reason_code is MarketBriefReasonCode.PROVIDER_RATE_LIMITED:
                        rate_limited = True
                    else:
                        evidence_availability.append(EvidenceAvailability(
                            symbol=symbol, evidence_category=EvidenceCategory.FILINGS,
                            reason_code=error.reason_code, recovery=_SAFE_RECOVERY_GUIDANCE.get(error.reason_code),
                        ))
                        optional_warnings.append(f"{error.reason_code.value}: optional SEC filings unavailable for {symbol}.")

            prior = holding_evidence[index]
            holding_evidence[index] = self._rank_evidence(
                symbol=symbol,
                quote=prior.quote,
                profile=profile,
                news=prior.news,
                earnings_events=prior.earnings_events,
                earnings_results=prior.earnings_results,
                filings=filings,
                recommendations=recommendations,
                price_target=price_target,
                dividends=dividends,
                now=now,
            )

        if rate_limited:
            optional_warnings.append(
                f"{MarketBriefReasonCode.PROVIDER_RATE_LIMITED.value}: optional market data unavailable for the remaining holdings; wait briefly and retry."
            )
        sec_warning = "SEC filings omitted: no authoritative holding-to-CIK mapping." if not resolved_ciks else None
        composition_warnings = tuple(
            (item for item in (sec_warning, *optional_warnings) if item)
        )
        evidence_availability_records = tuple(sorted(
            evidence_availability,
            key=lambda item: (item.symbol, item.evidence_category.value, item.reason_code.value),
        ))
        canonical_positions = [
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "current_value": position.current_value,
                "current_price": position.current_price,
                "previous_close": position.previous_close,
                "currency": position.currency,
                "freshness": position.freshness.value,
                "price_basis": position.price_basis.value,
                "observed_at": position.source.observed_at.isoformat() if position.source.observed_at else None,
            }
            for position in positions
        ]
        state_hash = _hash(
            {
                "schema": "market-brief-input/v2",
                "positions": canonical_positions,
                "coverage": coverage.model_dump(mode="json"),
                "composition_warnings": composition_warnings,
            }
        )
        universe_hash = _hash(
            {
                "symbols": sorted(grouped),
                "coverage": coverage.model_dump(mode="json"),
                "price_basis": sorted(basis.value for basis in basis_values),
            }
        )
        market_data_basis = next(iter(basis_values)) if len(basis_values) == 1 else PriceBasis.UNKNOWN
        # Aggregate per-holding filings for the v1 SEC section: only records
        # with an authoritative CIK produce requests; everything is bounded.
        all_filings = tuple(
            filing
            for packet in holding_evidence
            for filing in packet.filings
        )
        all_held_ciks = {filing.cik for filing in all_filings}

        readiness = ProviderReadiness(
            provider="market_data",
            status="degraded" if coverage.omitted_holding_count or composition_warnings else "ready",
            reason_code=(coverage.omissions[0].reason_code if coverage.omissions else None),
        )
        return BriefingInput(
            owner_id=owner_id,
            portfolio_state_hash=state_hash,
            universe_hash=universe_hash,
            report_window=report_window,
            positions=positions,
            news=news,
            earnings_events=earnings_events,
            earnings_results=earnings_results,
            filings=all_filings[:50],
            held_ciks=all_held_ciks,
            holding_evidence=tuple(sorted(holding_evidence, key=lambda packet: (packet.materiality, packet.symbol))),
            evidence_availability=evidence_availability_records,
            composition_warnings=composition_warnings,
            generated_at=now,
            coverage=coverage,
            market_data_basis=market_data_basis,
            provider_readiness=readiness,
        )
