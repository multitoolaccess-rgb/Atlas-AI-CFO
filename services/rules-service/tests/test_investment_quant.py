from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.investments.contracts import DataState
from app.investments.market_observations import AdjustmentBasis, MarketObservation, ObservationQuality
from app.investments.quant import QuantState, calculate_quant_research
from app.investments.securities import InstrumentType, SecurityIdentity, SecurityState
from app.investments.technicals import build_price_series

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
SECURITY = SecurityIdentity(security_id="sec:quant", state=SecurityState.RESOLVED, instrument_type=InstrumentType.EQUITY, symbol="ABC", currency="USD", as_of=NOW)
BENCHMARK = SecurityIdentity(security_id="sec:benchmark", state=SecurityState.RESOLVED, instrument_type=InstrumentType.INDEX, symbol="IDX", currency="USD", as_of=NOW)


def points(security, values):
    observations = []
    for index, close in enumerate(values):
        timestamp = NOW - timedelta(days=len(values) - index)
        observations.append(MarketObservation.with_hash(security=security, observed_value=str(close), currency="USD", observation_time=timestamp, as_of=timestamp, retrieved_at=NOW, source="fixture", source_identifier=f"fixture:{index}", freshness=DataState.OBSERVED, adjustment_basis=AdjustmentBasis.UNADJUSTED, quality=ObservationQuality.VALIDATED, observation_hash="0" * 64))
    return build_price_series(observations, adjustment_basis=AdjustmentBasis.UNADJUSTED)


def test_returns_volatility_and_drawdown_are_deterministic():
    series = points(SECURITY, [100, 110, 99, 120])
    first = calculate_quant_research(SECURITY, series, as_of=NOW, lookback=3)
    second = calculate_quant_research(SECURITY, series, as_of=NOW, lookback=3)
    assert first.research_hash == second.research_hash
    values = {metric.name: metric for metric in first.metrics}
    assert values["cumulative_return"].value == "0.2"
    assert values["maximum_drawdown"].value == "-0.1"
    assert values["volatility"].state is QuantState.AVAILABLE
    assert values["maximum_drawdown"].source_observation_hashes


def test_insufficient_history_is_explicit():
    result = calculate_quant_research(SECURITY, points(SECURITY, [100, 101]), as_of=NOW, lookback=5)
    assert next(metric for metric in result.metrics if metric.name == "volatility").state is QuantState.INSUFFICIENT_HISTORY


def test_sharpe_requires_explicit_risk_free_rate():
    series = points(SECURITY, [100, 101, 102, 103, 104, 105])
    missing = calculate_quant_research(SECURITY, series, as_of=NOW, lookback=5)
    assert next(metric for metric in missing.metrics if metric.name == "sharpe_ratio").state is QuantState.UNKNOWN
    supplied = calculate_quant_research(SECURITY, series, as_of=NOW, lookback=5, risk_free_rate=Decimal("0.001"))
    assert next(metric for metric in supplied.metrics if metric.name == "sharpe_ratio").value is not None


def test_benchmark_must_be_explicitly_aligned():
    asset = points(SECURITY, [100, 102, 101, 105])
    benchmark = points(BENCHMARK, [100, 101, 100, 102])
    result = calculate_quant_research(SECURITY, asset, as_of=NOW, lookback=3, benchmark=benchmark, benchmark_security_id=BENCHMARK.security_id)
    beta = next(metric for metric in result.metrics if metric.name == "beta")
    assert beta.state is QuantState.AVAILABLE
    mismatched = calculate_quant_research(SECURITY, asset, as_of=NOW, lookback=3, benchmark=points(BENCHMARK, [1, 2]))
    assert next(metric for metric in mismatched.metrics if metric.name == "beta").state is QuantState.UNAVAILABLE


def test_as_of_must_be_timezone_aware():
    with pytest.raises(ValueError):
        calculate_quant_research(SECURITY, points(SECURITY, [1, 2]), as_of=datetime(2026, 8, 30))
