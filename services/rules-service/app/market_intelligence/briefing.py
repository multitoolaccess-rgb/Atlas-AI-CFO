"""Deterministic Phase 5 briefing contracts, relevance, and Decimal calculations."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field, field_validator

from .contracts import (
    CompanyNewsItem,
    CoverageSummary,
    EarningsEvent,
    EarningsResult,
    Freshness,
    MarketBriefReasonCode,
    PriceBasis,
    ProviderReadiness,
    SecFilingEvent,
    SourceMetadata,
    StrictModel,
)
from .controls import deduplicate_records

BRIEF_SCHEMA_VERSION = "atlas-market-intelligence-brief/v1"
CALCULATION_VERSION = "market-impact/v2"


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _canonical(value: Decimal) -> str:
    return format(value.normalize(), "f")


class PositionInput(StrictModel):
    symbol: str
    quantity: str | None = None
    current_price: str | None = None
    previous_close: str | None = None
    week_start_price: str | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source: SourceMetadata
    freshness: Freshness = Freshness.FRESH
    price_basis: PriceBasis = PriceBasis.UNKNOWN
    current_value: str | None = None
    current_weight: str | None = None
    baseline_weight: str | None = None
    sector: str | None = None
    sector_authoritative: bool = False
    is_cash: bool = False
    cash_value: str | None = None


class PositionChange(StrictModel):
    symbol: str
    daily_change: str
    weekly_change: str | None = None
    contribution: str | None = None
    allocation_movement: str | None = None
    source: SourceMetadata


class PortfolioChanges(StrictModel):
    rows: tuple[PositionChange, ...]
    total_daily_change: str | None = None
    warnings: tuple[str, ...] = ()


class ExposureSummary(StrictModel):
    sector_weights: tuple[tuple[str, str], ...]
    concentration_warning: str | None = None
    cash_value: str | None = None
    cash_currency: str | None = None
    warnings: tuple[str, ...] = ()


def build_exposure_summary(positions: list[PositionInput], *, concentration_threshold: Decimal = Decimal("0.25")) -> ExposureSummary:
    sectors: dict[str, Decimal] = {}
    warnings: list[str] = []
    cash_total = Decimal(0)
    has_cash = False
    cash_currencies: set[str] = set()
    for position in positions:
        if position.is_cash:
            value = _decimal(position.cash_value)
            if value is None or value < 0:
                warnings.append("Cash omitted: no authoritative cash value.")
            else:
                cash_currencies.add(position.currency)
                cash_total += value
                has_cash = True
            continue
        weight = _decimal(position.current_weight)
        if weight is None:
            continue
        sector = position.sector if position.sector_authoritative and position.sector else "unknown"
        sectors[sector] = sectors.get(sector, Decimal(0)) + weight
    ordered = tuple((sector, _canonical(weight)) for sector, weight in sorted(sectors.items()))
    concentration = next((f"Concentration review: {sector} weight {weight}." for sector, weight in ordered if Decimal(weight) >= concentration_threshold), None)
    if len(cash_currencies) > 1:
        warnings.append("Cash omitted: currency ambiguous.")
        has_cash = False
    return ExposureSummary(sector_weights=ordered, concentration_warning=concentration, cash_value=_canonical(cash_total) if has_cash else None, cash_currency=next(iter(cash_currencies)) if has_cash else None, warnings=tuple(warnings))


def build_portfolio_changes(positions: list[PositionInput]) -> PortfolioChanges:
    rows: list[PositionChange] = []
    warnings: list[str] = []
    currencies: set[str] = set()
    for position in positions:
        if position.is_cash:
            if position.cash_value is None:
                warnings.append("Cash omitted: no authoritative cash value.")
            continue
        quantity, current, previous = (_decimal(position.quantity), _decimal(position.current_price), _decimal(position.previous_close))
        if position.freshness is not Freshness.FRESH:
            warnings.append(f"{position.symbol}: stale quote excluded.")
            continue
        if quantity is None or current is None or previous is None or quantity < 0 or current <= 0 or previous <= 0:
            warnings.append(f"{position.symbol}: missing or invalid comparable price/quantity.")
            continue
        currencies.add(position.currency)
        weekly = None
        start = _decimal(position.week_start_price)
        if start is not None and start > 0:
            weekly = _canonical(quantity * (current - start))
        elif position.week_start_price is not None:
            warnings.append(f"{position.symbol}: stale or invalid weekly baseline excluded.")
        current_weight, baseline_weight = _decimal(position.current_weight), _decimal(position.baseline_weight)
        allocation = _canonical(current_weight - baseline_weight) if current_weight is not None and baseline_weight is not None else None
        rows.append(PositionChange(symbol=position.symbol, daily_change=_canonical(quantity * (current - previous)), weekly_change=weekly, allocation_movement=allocation, source=position.source))
    if len(currencies) > 1:
        return PortfolioChanges(rows=(), warnings=tuple(warnings + ["Currency ambiguous: portfolio changes omitted."]))
    total = sum((_decimal(row.daily_change) or Decimal(0) for row in rows), Decimal(0))
    enriched = [row.model_copy(update={"contribution": _canonical((_decimal(row.daily_change) or Decimal(0)) / total) if total else None}) for row in rows]
    enriched.sort(key=lambda row: (-abs(_decimal(row.daily_change) or Decimal(0)), row.symbol))
    return PortfolioChanges(rows=tuple(enriched), total_daily_change=_canonical(total), warnings=tuple(warnings))


def select_relevant_news(items: list[CompanyNewsItem], *, held_symbols: set[str]) -> list[CompanyNewsItem]:
    kept = [item for item in items if item.symbol in held_symbols]
    return deduplicate_records(kept, lambda item: item.source.source_url)


def select_relevant_filings(items: list[SecFilingEvent], *, held_ciks: set[str]) -> list[SecFilingEvent]:
    kept = [item for item in items if item.cik in held_ciks]
    return deduplicate_records(kept, lambda item: (item.cik, item.accession_number))


def select_relevant_earnings(events: list[EarningsEvent], results: list[EarningsResult], *, held_symbols: set[str]) -> tuple[list[EarningsEvent], list[EarningsResult]]:
    """Portfolio-only normalized earnings, keyed by event date or reported period."""
    selected_events = deduplicate_records((event for event in events if event.symbol in held_symbols and event.source.freshness is Freshness.FRESH), lambda event: (event.symbol, event.event_date))
    selected_results = deduplicate_records((result for result in results if result.symbol in held_symbols and result.source.freshness is Freshness.FRESH), lambda result: (result.symbol, result.source.observed_at, result.actual, result.estimate))
    return sorted(selected_events, key=lambda event: (event.event_date, event.symbol)), sorted(selected_results, key=lambda result: (result.source.observed_at or datetime.min.replace(tzinfo=timezone.utc), result.symbol), reverse=True)


class Citation(StrictModel):
    provider: str
    source_url: str
    retrieved_at: datetime
    published_at: datetime | None = None
    freshness: Freshness

    @classmethod
    def from_source(cls, source: SourceMetadata) -> "Citation":
        return cls(provider=source.provider, source_url=source.source_url, retrieved_at=source.retrieved_at, published_at=source.published_at or source.observed_at, freshness=source.freshness)


class BriefSection(StrictModel):
    name: str
    content: tuple[str, ...]
    citations: tuple[Citation, ...] = ()
    claims: tuple["BriefClaim", ...] = ()


class BriefClaim(StrictModel):
    """A displayed claim cannot exist without its source and freshness."""
    text: str
    citation: Citation


class ActionToReview(StrictModel):
    action: str
    why: str
    goal_linkage: str
    evidence: tuple[str, ...]
    expected_impact: str
    risks: tuple[str, ...]
    alternatives: tuple[str, ...]
    confidence: Literal["low", "medium", "high"]
    approval_requirement: Literal["explicit_user_approval_required"]


class BriefingInput(StrictModel):
    owner_id: int
    portfolio_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    universe_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    report_window: str = Field(min_length=1, max_length=64)
    positions: list[PositionInput]
    news: list[CompanyNewsItem] = []
    filings: list[SecFilingEvent] = []
    earnings_events: list[EarningsEvent] = []
    earnings_results: list[EarningsResult] = []
    held_ciks: set[str] = set()
    composition_warnings: tuple[str, ...] = ()
    generated_at: datetime
    coverage: CoverageSummary | None = None
    market_data_basis: PriceBasis = PriceBasis.UNKNOWN
    provider_readiness: ProviderReadiness = ProviderReadiness(provider="market_data", status="ready")


class MarketBrief(StrictModel):
    schema_version: Literal["atlas-market-intelligence-brief/v1"] = BRIEF_SCHEMA_VERSION
    calculation_version: str = CALCULATION_VERSION
    owner_id: int
    portfolio_state_hash: str
    universe_hash: str
    report_window: str
    generated_at: datetime
    as_of: datetime
    sections: tuple[BriefSection, ...]
    actions: tuple[ActionToReview, ...]
    warnings: tuple[str, ...]
    coverage: CoverageSummary | None = None
    market_data_basis: PriceBasis = PriceBasis.UNKNOWN
    provider_readiness: ProviderReadiness = ProviderReadiness(provider="market_data", status="unavailable", reason_code=MarketBriefReasonCode.MARKET_BRIEF_GENERATION_UNAVAILABLE)
    portfolio_daily_change: str | None = None


class DeterministicTemplateProvider:
    """The only enabled v1 generator; produces review-only prose with no model call."""
    def generate(self, input: BriefingInput) -> MarketBrief:
        changes = build_portfolio_changes(input.positions)
        news = select_relevant_news(input.news, held_symbols={p.symbol for p in input.positions})
        filings = select_relevant_filings(input.filings, held_ciks=input.held_ciks)
        earnings_events, earnings_results = select_relevant_earnings(input.earnings_events, input.earnings_results, held_symbols={p.symbol for p in input.positions})
        news_citations = tuple(Citation.from_source(item.source) for item in news)
        portfolio_claims = tuple(BriefClaim(text=f"{row.symbol}: {row.daily_change}", citation=Citation.from_source(row.source)) for row in changes.rows)
        filing_claims = tuple(BriefClaim(text=f"{item.form}: {item.accession_number}", citation=Citation.from_source(item.source)) for item in filings)
        today = input.generated_at.date()
        earnings_claims: list[BriefClaim] = []
        for event in earnings_events:
            label = "today" if event.event_date.date() == today else "upcoming" if event.event_date.date() > today else "recent"
            earnings_claims.append(BriefClaim(text=f"{label}: {event.symbol} earnings on {event.event_date.date().isoformat()}", citation=Citation.from_source(event.source)))
        for result in earnings_results:
            period = result.source.observed_at.date().isoformat() if result.source.observed_at else "recent"
            earnings_claims.append(BriefClaim(text=f"recent result: {result.symbol} period {period}", citation=Citation.from_source(result.source)))
        earnings_claims.sort(key=lambda claim: (claim.text, claim.citation.source_url))
        citations = tuple((*news_citations, *(claim.citation for claim in portfolio_claims), *(claim.citation for claim in filing_claims), *(claim.citation for claim in earnings_claims)))
        coverage_warnings = tuple(
            f"{omission.symbol}: {omission.reason_code.value}."
            for omission in (input.coverage.omissions if input.coverage else ())
        )
        action = ActionToReview(action="Review whether material portfolio changes warrant follow-up.", why="The briefing reports deterministic market data only.", goal_linkage="No goal linkage is inferred.", evidence=tuple(row.symbol for row in changes.rows), expected_impact="No execution or return is implied.", risks=("Market data may be incomplete or stale.",), alternatives=("Do nothing.",), confidence="low", approval_requirement="explicit_user_approval_required")
        sections = (
            BriefSection(name="executive_summary", content=("Portfolio-specific market briefing; review-only.",)),
            BriefSection(name="portfolio_changes", content=tuple(claim.text for claim in portfolio_claims), citations=tuple(claim.citation for claim in portfolio_claims), claims=portfolio_claims),
            BriefSection(name="material_holding_news", content=tuple(item.headline for item in news), citations=news_citations),
            BriefSection(name="earnings", content=tuple(claim.text for claim in earnings_claims), citations=tuple(claim.citation for claim in earnings_claims), claims=tuple(earnings_claims)),
            BriefSection(name="sec_filings", content=tuple(claim.text for claim in filing_claims), citations=tuple(claim.citation for claim in filing_claims), claims=filing_claims),
            BriefSection(name="risks_and_opportunities", content=("Missing or stale inputs are disclosed.",)),
            BriefSection(name="actions_to_review", content=(action.action,)),
            BriefSection(name="sources", content=tuple(c.source_url for c in citations), citations=citations),
            BriefSection(name="data_quality", content=tuple((*changes.warnings, *input.composition_warnings, *coverage_warnings))),
        )
        warnings = tuple((*changes.warnings, *input.composition_warnings, *coverage_warnings))
        provider_readiness = input.provider_readiness
        if warnings and provider_readiness.status == "ready":
            provider_readiness = provider_readiness.model_copy(update={"status": "degraded"})
        return MarketBrief(
            owner_id=input.owner_id,
            portfolio_state_hash=input.portfolio_state_hash,
            universe_hash=input.universe_hash,
            report_window=input.report_window,
            generated_at=input.generated_at,
            as_of=input.generated_at,
            sections=sections,
            actions=(action,),
            warnings=warnings,
            coverage=input.coverage,
            market_data_basis=input.market_data_basis,
            provider_readiness=provider_readiness,
            portfolio_daily_change=changes.total_daily_change,
        )


class OllamaProvider:
    enabled = False


class CloudLLMProvider:
    enabled = False
