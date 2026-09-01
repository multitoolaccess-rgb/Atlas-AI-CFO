from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.investments.cio_reports import ReportEvidence, ReportSectionKind, ReportType, generate_cio_report
from app.investments.committee_contracts import EvidenceCategory
from app.investments.fundamentals import FactKind, FactStatus, FundamentalFact, PeriodBasis, derive_metrics
from app.investments.contracts import DataState, EvidenceKind, EvidenceReference
from app.investments.market_observations import AdjustmentBasis
from app.investments.portfolio_intelligence import build_portfolio_snapshot
from app.investments.quant import QuantState, calculate_quant_research
from app.investments.securities import InstrumentType, SecurityIdentity, SecurityState, security_id_for
from app.investments.technicals import PriceSeriesPoint, TechnicalState, calculate_technical_research

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)

def security(symbol):
    return SecurityIdentity(security_id=security_id_for(namespace="atlas-security", value=f"equity:{symbol}"), state=SecurityState.RESOLVED, instrument_type=InstrumentType.EQUITY, symbol=symbol, as_of=NOW)

def evidence(eid, *, as_of=NOW - timedelta(days=1)):
    return EvidenceReference(evidence_id=eid, kind=EvidenceKind.SOURCE, source="fixture", content_hash="a" * 64, as_of=as_of, retrieved_at=NOW, state=DataState.OBSERVED)

def point(ts, close, h):
    return PriceSeriesPoint(timestamp=ts, close=str(close), currency="USD", adjustment_basis=AdjustmentBasis.UNADJUSTED, source_observation_hash=h * 64)

def fact(fid, kind, value, basis, known, end):
    return FundamentalFact(fact_id=fid, security=security("AAPL"), kind=kind, value=str(value), unit="USD", currency="USD", period_basis=basis, period_end=end, as_known_at=known, retrieved_at=NOW, status=FactStatus.REPORTED, source=evidence(fid, as_of=known))

def test_portfolio_identity_is_independent_of_holding_and_account_ids():
    account_a = SimpleNamespace(id=1, user_id=7)
    account_b = SimpleNamespace(id=2, user_id=7)
    h1 = SimpleNamespace(id=10, account_id=1, symbol="AAPL", type="stock", quantity=1, current_value=100, cost_basis_total=90, last_price=100)
    h2 = SimpleNamespace(id=99, account_id=2, symbol="AAPL", type="stock", quantity=2, current_value=200, cost_basis_total=180, last_price=100)
    one = build_portfolio_snapshot(owner_id=7, accounts=(account_a,), holdings=(h1,), as_of=NOW)
    two = build_portfolio_snapshot(owner_id=7, accounts=(account_b,), holdings=(h2,), as_of=NOW)
    assert one.positions[0].security.security_id == two.positions[0].security.security_id
    assert one.positions[0].source_holding_id != two.positions[0].source_holding_id

def test_unresolved_symbol_does_not_fabricate_resolved_identity():
    account = SimpleNamespace(id=1, user_id=7)
    holding = SimpleNamespace(id=10, account_id=1, symbol=None, type="stock", quantity=1, current_value=100, cost_basis_total=None, last_price=100)
    snapshot = build_portfolio_snapshot(owner_id=7, accounts=(account,), holdings=(holding,), as_of=NOW)
    assert snapshot.positions[0].security.state is SecurityState.UNRESOLVED

def test_fundamental_selection_is_point_in_time_period_compatible_and_order_invariant():
    annual_end = datetime(2025, 12, 31, tzinfo=UTC)
    quarter_end = datetime(2026, 6, 30, tzinfo=UTC)
    known = NOW - timedelta(days=30)
    future_known = NOW + timedelta(days=1)
    future = FundamentalFact(fact_id="future", security=security("AAPL"), kind=FactKind.REVENUE, value="999", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL, period_end=annual_end, as_known_at=future_known, retrieved_at=future_known, status=FactStatus.REPORTED, source=evidence("future", as_of=future_known))
    revenue = fact("annual-revenue", FactKind.REVENUE, 100, PeriodBasis.ANNUAL, known, annual_end)
    gross = fact("annual-gross", FactKind.GROSS_PROFIT, 40, PeriodBasis.ANNUAL, known, annual_end)
    quarter = fact("quarter-revenue", FactKind.REVENUE, 25, PeriodBasis.QUARTERLY, known, quarter_end)
    first = derive_metrics((future, quarter, gross, revenue), as_of=NOW)
    second = derive_metrics((revenue, gross, quarter, future), as_of=NOW)
    assert first == second
    assert first[0].value == "0.4"
    assert "future" not in first[0].source_fact_ids

def test_zero_previous_close_fails_closed_in_technical_and_quant_returns():
    points = tuple(point(datetime(2026, 8, 25 + i, tzinfo=UTC), close, chr(97 + i)) for i, close in enumerate((100, 0, 110, 111, 112, 113)))
    technical = calculate_technical_research(security("AAPL"), points, as_of=NOW, sma_period=3, rsi_period=3)
    assert next(signal for signal in technical.signals if signal.name == "rolling_volatility").state is TechnicalState.UNAVAILABLE
    with pytest.raises(ValueError, match="zero close denominator"):
        calculate_quant_research(security("AAPL"), points, as_of=NOW)

def test_benchmark_identity_is_canonical_and_hashes_remain_provenance():
    target = tuple(point(datetime(2026, 8, 25 + i, tzinfo=UTC), 100 + i, chr(97 + i)) for i in range(6))
    benchmark_hashes = "abcdef"
    benchmark = tuple(point(datetime(2026, 8, 25 + i, tzinfo=UTC), 200 + i, benchmark_hashes[i]) for i in range(6))
    benchmark_id = security("SPY").security_id
    result = calculate_quant_research(security("AAPL"), target, as_of=NOW, benchmark=benchmark, benchmark_security_id=benchmark_id)
    assert result.benchmark_security_id == benchmark_id
    assert result.benchmark_security_id not in result.metrics[-1].source_observation_hashes
    assert all(len(item) == 64 for item in result.metrics[-1].source_observation_hashes)

def test_cio_sections_link_only_report_evidence_and_additional_future_evidence_is_rejected():
    valid = ReportEvidence(evidence_id="market:one", category="market", source_hash="a" * 64, as_of=NOW, state="observed")
    report = generate_cio_report(owner_id=7, report_type=ReportType.DAILY_BRIEF, anchor_date=NOW.date(), as_of=NOW, portfolio_snapshot_hash="b" * 64, additional_evidence=(valid,), market_items=("Market moved.",))
    by_kind = {section.kind: section for section in report.sections}
    assert "market:one" in by_kind[ReportSectionKind.MARKET].evidence_ids
    assert set(by_kind[ReportSectionKind.MARKET].evidence_ids) <= {item.evidence_id for item in report.evidence}
    future = valid.model_copy(update={"evidence_id": "market:future", "as_of": NOW + timedelta(seconds=1)})
    with pytest.raises(ValueError, match="future additional evidence"):
        generate_cio_report(owner_id=7, report_type=ReportType.DAILY_BRIEF, anchor_date=NOW.date(), as_of=NOW, portfolio_snapshot_hash="b" * 64, additional_evidence=(future,))
