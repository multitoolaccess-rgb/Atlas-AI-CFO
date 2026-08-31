from datetime import UTC, datetime, timedelta

import pytest

from app.investments.contracts import DataState
from app.investments.market_observations import AdjustmentBasis, MarketObservation, ObservationQuality
from app.investments.securities import InstrumentType, SecurityIdentity, SecurityState
from app.investments.technicals import TechnicalState, build_price_series, calculate_technical_research

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
SECURITY = SecurityIdentity(security_id="sec:tech", state=SecurityState.RESOLVED, instrument_type=InstrumentType.EQUITY, symbol="ABC", currency="USD", as_of=NOW)


def observation(index: int, close: str, *, basis=AdjustmentBasis.UNADJUSTED, freshness=DataState.OBSERVED):
    timestamp = NOW - timedelta(days=20 - index)
    return MarketObservation.with_hash(
        security=SECURITY, observed_value=close, currency="USD", observation_time=timestamp,
        as_of=timestamp, retrieved_at=NOW, source="fixture", source_identifier=f"fixture:{index}",
        freshness=freshness, adjustment_basis=basis, quality=ObservationQuality.VALIDATED,
        observation_hash="0" * 64,
    )


def test_series_is_ordered_and_preserves_source_hashes():
    points = build_price_series([observation(2, "12"), observation(0, "10"), observation(1, "11")], adjustment_basis=AdjustmentBasis.UNADJUSTED)
    assert [point.close for point in points] == ["10", "11", "12"]
    assert all(len(point.source_observation_hash) == 64 for point in points)


def test_mixed_basis_and_duplicate_timestamps_fail_closed():
    with pytest.raises(ValueError):
        build_price_series([observation(0, "10"), observation(1, "11", basis=AdjustmentBasis.SPLIT_ADJUSTED)], adjustment_basis=AdjustmentBasis.UNADJUSTED)
    duplicate = observation(0, "10")
    with pytest.raises(ValueError):
        build_price_series([duplicate, duplicate], adjustment_basis=AdjustmentBasis.UNADJUSTED)


def test_sma_uses_only_observations_through_as_of_and_is_reproducible():
    points = build_price_series([observation(i, str(10 + i)) for i in range(6)], adjustment_basis=AdjustmentBasis.UNADJUSTED)
    first = calculate_technical_research(SECURITY, points, as_of=NOW)
    second = calculate_technical_research(SECURITY, points, as_of=NOW)
    assert first.research_hash == second.research_hash
    assert next(signal for signal in first.signals if signal.name == "sma").value == "13"
    assert first.source_observation_hashes == tuple(point.source_observation_hash for point in points)


def test_rsi_is_unavailable_when_history_is_insufficient_not_zero():
    points = build_price_series([observation(i, str(10 + i)) for i in range(5)], adjustment_basis=AdjustmentBasis.UNADJUSTED)
    research = calculate_technical_research(SECURITY, points, as_of=NOW)
    rsi = next(signal for signal in research.signals if signal.name == "rsi")
    assert rsi.value is None
    assert rsi.state is TechnicalState.INSUFFICIENT_HISTORY


def test_missing_observation_cannot_enter_series():
    with pytest.raises(ValueError):
        build_price_series([observation(0, "10", freshness=DataState.MISSING)], adjustment_basis=AdjustmentBasis.UNADJUSTED)


def test_constant_prices_have_zero_volatility():
    points = build_price_series([observation(i, "10") for i in range(6)], adjustment_basis=AdjustmentBasis.UNADJUSTED)
    research = calculate_technical_research(SECURITY, points, as_of=NOW)
    volatility = next(signal for signal in research.signals if signal.name == "rolling_volatility")
    assert volatility.value == "0"
