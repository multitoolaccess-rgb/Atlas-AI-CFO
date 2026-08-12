"""Trusted server-only market brief input assembly; no client financial payloads."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.holding import Holding
from .adapters import FinnhubAdapter, ProviderConfigurationError, SecAdapter
from .briefing import BriefingInput, PositionInput
from .contracts import (
    CompanyNewsItem,
    CoverageBasis,
    CoverageOmission,
    CoverageSummary,
    EarningsEvent,
    EarningsResult,
    FailureClass,
    Freshness,
    MarketBriefReasonCode,
    MarketQuoteSnapshot,
    PriceBasis,
    ProviderReadiness,
    SecFilingEvent,
)

MINIMUM_COVERAGE = Decimal("0.80")

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


class MarketBriefCompositionError(ValueError):
    """A server-owned market input was incomplete or not safe to brief."""

    def __init__(
        self,
        message: str,
        reason_code: MarketBriefReasonCode = MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code


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

    def filings(self) -> list[SecFilingEvent]:
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
                omissions.append(CoverageOmission(symbol="UNKNOWN", reason_code=MarketBriefReasonCode.UNSUPPORTED_SYMBOL))
                continue
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
                omissions.append(CoverageOmission(symbol=symbol, reason_code=quote_errors[symbol]))
            else:
                covered.append(holding)

        coverage = self._coverage(eligible, covered, omissions)
        percentage = _decimal(coverage.coverage_percentage) or Decimal(0)
        if coverage.covered_holding_count == 0:
            raise MarketBriefCompositionError(
                "No trustworthy priced holdings remain for this brief.",
                MarketBriefReasonCode.NO_MARKET_ADDRESSABLE_HOLDINGS,
            )
        if percentage < MINIMUM_COVERAGE:
            raise MarketBriefCompositionError(
                "Portfolio coverage is below the minimum meaningful threshold.",
                MarketBriefReasonCode.INSUFFICIENT_PORTFOLIO_COVERAGE,
            )

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

        optional_warnings: list[str] = []
        news: list[CompanyNewsItem] = []
        earnings_events: list[EarningsEvent] = []
        earnings_results: list[EarningsResult] = []
        now = self._now()
        for symbol in sorted(grouped):
            for label, loader, target in (
                ("news", self.providers.news, news),
                ("earnings_events", self.providers.earnings_events, earnings_events),
                ("earnings_results", self.providers.earnings_results, earnings_results),
            ):
                try:
                    records = loader(symbol)
                    if label == "news":
                        target.extend(records[:20])
                    elif label == "earnings_events":
                        target.extend(
                            event for event in records
                            if now.date() - timedelta(days=14) <= event.event_date.date() <= now.date() + timedelta(days=30)
                        )
                    else:
                        target.extend(
                            result for result in records
                            if result.source.observed_at
                            and now.date() - timedelta(days=14) <= result.source.observed_at.date() <= now.date()
                        )
                except MarketBriefCompositionError as error:
                    optional_warnings.append(f"{error.reason_code.value}: optional {label} unavailable.")

        composition_warnings = tuple(
            (
                "SEC filings omitted: no authoritative holding-to-CIK mapping.",
                *optional_warnings,
            )
        )
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
            filings=self.providers.filings()[:50],
            composition_warnings=composition_warnings,
            generated_at=now,
            coverage=coverage,
            market_data_basis=market_data_basis,
            provider_readiness=readiness,
        )
