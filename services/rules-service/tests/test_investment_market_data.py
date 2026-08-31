from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.investments.contracts import DataState
from app.investments.market_observations import (
    AdjustmentBasis,
    MarketObservation,
    ObservationQuality,
)
from app.investments.provider_adapters import (
    FixtureSecurityDataProvider,
    ProviderPayloadError,
    normalize_observation,
    normalize_security,
)
from app.investments.securities import (
    InstrumentType,
    SecurityIdentifier,
    SecurityIdentity,
    SecurityState,
    security_id_for,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


def identity(state=SecurityState.RESOLVED, symbol="aapl", exchange="nasdaq"):
    return SecurityIdentity(
        security_id=security_id_for(namespace="exchange", value=f"{exchange}:{symbol}"),
        state=state,
        instrument_type=InstrumentType.EQUITY,
        symbol=symbol,
        exchange=exchange,
        currency="USD",
        identifiers=(SecurityIdentifier(namespace="provider.finnhub", value=symbol),),
        as_of=NOW,
    )


def observation(**overrides):
    values = dict(
        security=identity(),
        observed_value="123.4500",
        currency="USD",
        observation_time=NOW - timedelta(minutes=1),
        as_of=NOW - timedelta(minutes=1),
        retrieved_at=NOW,
        source="fixture",
        source_identifier="fixture:aapl:1",
        freshness=DataState.OBSERVED,
        adjustment_basis=AdjustmentBasis.UNADJUSTED,
        quality=ObservationQuality.VALIDATED,
        observation_hash="0" * 64,
    )
    values.update(overrides)
    return MarketObservation.with_hash(**values)


def test_identity_is_exchange_aware_and_symbol_is_normalized():
    result = identity()
    assert result.symbol == "AAPL"
    assert result.exchange == "NASDAQ"
    assert result.identity_hash() == identity().identity_hash()
    assert security_id_for(namespace="exchange", value="NASDAQ:AAPL") != security_id_for(namespace="exchange", value="NYSE:AAPL")


def test_identity_states_are_explicit():
    assert {state.value for state in SecurityState} == {
        "resolved", "unresolved", "unsupported", "ambiguous", "inactive"
    }
    unresolved = identity(SecurityState.UNRESOLVED)
    assert unresolved.state is SecurityState.UNRESOLVED


def test_observation_hash_and_decimal_are_deterministic():
    first = observation()
    second = observation()
    assert first.observed_value == "123.45"
    assert first.observation_hash == second.observation_hash


def test_observation_rejects_non_finite_or_invalid_values():
    with pytest.raises(ValidationError):
        observation(observed_value="NaN")
    with pytest.raises(ValidationError):
        observation(quality=ObservationQuality.INVALID)


def test_observation_preserves_point_in_time_fields_and_state():
    stale = observation(freshness=DataState.STALE)
    assert stale.observation_time < stale.retrieved_at
    assert stale.as_of == stale.observation_time
    assert stale.freshness is DataState.STALE


def test_observation_rejects_future_as_of():
    with pytest.raises(ValidationError):
        observation(as_of=NOW + timedelta(minutes=1))


def test_missing_observation_does_not_become_zero():
    missing = observation(freshness=DataState.MISSING, observed_value=None)
    assert missing.observed_value is None
    assert missing.freshness is DataState.MISSING


def test_fixture_provider_normalizes_without_leaking_provider_fields():
    provider = FixtureSecurityDataProvider(
        {"provider": "fixture", "provider_id": "p-1", "symbol": "aapl", "exchange": "nasdaq", "instrument_type": "stock", "currency": "usd", "as_of": "2026-08-30T11:00:00Z"},
        {"p-1": {"value": "123.4500", "currency": "usd", "observed_at": "2026-08-30T11:59:00Z", "as_of": "2026-08-30T11:59:00Z", "source": "fixture", "provider_id": "p-1"}},
        {},
    )
    raw_security = provider.resolve_security("AAPL", "NASDAQ")
    canonical_security = normalize_security(raw_security)
    canonical = normalize_observation(provider.get_observation("p-1"), security=canonical_security, retrieved_at=NOW)
    assert canonical_security.symbol == "AAPL"
    assert canonical_security.instrument_type is InstrumentType.EQUITY
    assert canonical.observed_value == "123.45"
    assert canonical.source_identifier == "observation-normalizer/v1:p-1"
    assert "provider_id" not in canonical.model_dump()


def test_normalizer_rejects_bad_numeric_currency_timestamp_and_unknown_type():
    with pytest.raises(ProviderPayloadError):
        normalize_security({"provider": "fixture", "provider_id": "x", "symbol": "A", "exchange": "X", "instrument_type": "preferred", "as_of": "2026-08-30T00:00:00Z"})
    for key, value in (("value", "NaN"), ("currency", "US"), ("observed_at", "2026-08-30T00:00:00")):
        payload = {"value": "1", "currency": "USD", "observed_at": "2026-08-30T11:00:00Z", "as_of": "2026-08-30T11:00:00Z", "source": "fixture", "provider_id": "p-1"}
        payload[key] = value
        with pytest.raises(ProviderPayloadError):
            normalize_observation(payload, security=identity(), retrieved_at=NOW)


def test_freshness_is_derived_and_history_keeps_as_of():
    stale = normalize_observation(
        {"value": 1, "currency": "USD", "observed_at": "2026-08-28T11:00:00Z", "as_of": "2026-08-28T11:00:00Z", "source": "fixture", "provider_id": "p-1"},
        security=identity(), retrieved_at=NOW,
    )
    assert stale.freshness is DataState.STALE
