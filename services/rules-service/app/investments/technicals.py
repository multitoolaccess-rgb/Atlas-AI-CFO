"""INV-05 deterministic technical research over canonical market data."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable

from pydantic import Field, field_validator, model_validator

from .contracts import DataState, InvestmentStrictModel
from .market_observations import AdjustmentBasis, MarketObservation
from .securities import SecurityIdentity


class TechnicalState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INSUFFICIENT_HISTORY = "insufficient_history"
    STALE = "stale"


class PriceSeriesPoint(InvestmentStrictModel):
    timestamp: datetime
    close: str = Field(max_length=48)
    volume: str | None = Field(default=None, max_length=48)
    currency: str
    adjustment_basis: AdjustmentBasis
    source_observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("series timestamp must be timezone-aware UTC")
        return value.astimezone(UTC)

    @field_validator("close", "volume")
    @classmethod
    def finite_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("series value must be decimal") from None
        if not number.is_finite() or (value != "" and number < 0):
            raise ValueError("series value must be finite and non-negative")
        return format(number.normalize(), "f")


class TechnicalSignal(InvestmentStrictModel):
    schema_version: str = "TechnicalSignal/v1"
    name: str = Field(min_length=1, max_length=48)
    value: str | None = Field(default=None, max_length=48)
    unit: str = Field(min_length=1, max_length=24)
    state: TechnicalState
    as_of: datetime
    lookback: int = Field(gt=0, le=500)
    adjustment_basis: AdjustmentBasis
    calculation_version: str = Field(min_length=1, max_length=48)
    source_observation_hashes: tuple[str, ...] = Field(min_length=1, max_length=500)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: str | None) -> str | None:
        if value is None:
            return value
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("signal must be finite")
        return format(number.normalize(), "f")

    @field_validator("as_of")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("signal as_of must be timezone-aware UTC")
        return value.astimezone(UTC)


class TechnicalResearch(InvestmentStrictModel):
    schema_version: str = "TechnicalResearch/v1"
    security: SecurityIdentity
    as_of: datetime
    signals: tuple[TechnicalSignal, ...] = Field(default=(), max_length=50)
    methodology_version: str = "technical-research/v1"
    source_observation_hashes: tuple[str, ...] = Field(min_length=1, max_length=500)
    research_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research as_of must be timezone-aware UTC")
        return value.astimezone(UTC)

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"research_hash"}), sort_keys=True, separators=(",", ":"))


def build_price_series(observations: Iterable[MarketObservation], *, adjustment_basis: AdjustmentBasis) -> tuple[PriceSeriesPoint, ...]:
    """Validate a same-basis, ordered close series without repairing source data."""
    ordered = sorted(observations, key=lambda item: item.observation_time)
    points: list[PriceSeriesPoint] = []
    previous: datetime | None = None
    for observation in ordered:
        if observation.adjustment_basis is not adjustment_basis:
            raise ValueError("mixed adjustment bases are not allowed")
        if observation.observation_time == previous:
            raise ValueError("duplicate observation timestamps are not allowed")
        if observation.observed_value is None or observation.freshness in {DataState.MISSING, DataState.UNKNOWN}:
            raise ValueError("missing observation cannot enter a price series")
        points.append(PriceSeriesPoint(timestamp=observation.observation_time, close=observation.observed_value, currency=observation.currency or "", adjustment_basis=adjustment_basis, source_observation_hash=observation.observation_hash))
        previous = observation.observation_time
    if not points:
        raise ValueError("price series is empty")
    currencies = {point.currency for point in points}
    if len(currencies) != 1 or "" in currencies:
        raise ValueError("price series currency is ambiguous")
    return tuple(points)


def _signal(name: str, value: Decimal | None, *, state: TechnicalState, as_of: datetime, lookback: int, basis: AdjustmentBasis, hashes: tuple[str, ...], unit: str = "ratio") -> TechnicalSignal:
    return TechnicalSignal(name=name, value=format(value.normalize(), "f") if value is not None else None, unit=unit, state=state, as_of=as_of, lookback=lookback, adjustment_basis=basis, calculation_version="technical-calculations/v1", source_observation_hashes=hashes)


def calculate_technical_research(security: SecurityIdentity, points: tuple[PriceSeriesPoint, ...], *, as_of: datetime, sma_period: int = 5, rsi_period: int = 14) -> TechnicalResearch:
    """Calculate a minimal auditable set of trailing SMA, RSI, and volatility."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware UTC")
    if not points:
        raise ValueError("price series is empty")
    closes = [Decimal(point.close) for point in points]
    hashes = tuple(point.source_observation_hash for point in points)
    basis = points[-1].adjustment_basis
    signals: list[TechnicalSignal] = []
    sma = sum(closes[-sma_period:], Decimal(0)) / Decimal(sma_period) if len(closes) >= sma_period else None
    signals.append(_signal("sma", sma, state=TechnicalState.AVAILABLE if sma is not None else TechnicalState.INSUFFICIENT_HISTORY, as_of=points[-1].timestamp, lookback=sma_period, basis=basis, hashes=hashes[-sma_period:], unit="price"))
    if len(closes) >= rsi_period + 1:
        changes = [closes[index] - closes[index - 1] for index in range(len(closes) - rsi_period, len(closes))]
        gains = [change for change in changes if change > 0]
        losses = [-change for change in changes if change < 0]
        average_gain = sum(gains, Decimal(0)) / Decimal(rsi_period)
        average_loss = sum(losses, Decimal(0)) / Decimal(rsi_period)
        rsi = Decimal(100) if average_loss == 0 and average_gain > 0 else Decimal(0) if average_gain == 0 else Decimal(100) - (Decimal(100) / (Decimal(1) + average_gain / average_loss))
    else:
        rsi = None
    signals.append(_signal("rsi", rsi, state=TechnicalState.AVAILABLE if rsi is not None else TechnicalState.INSUFFICIENT_HISTORY, as_of=points[-1].timestamp, lookback=rsi_period, basis=basis, hashes=hashes[-(rsi_period + 1):], unit="percent"))
    if len(closes) >= sma_period + 1 and all(closes[index - 1] != 0 for index in range(len(closes) - sma_period + 1, len(closes))):
        returns = [(closes[index] / closes[index - 1]) - Decimal(1) for index in range(len(closes) - sma_period + 1, len(closes))]
        mean = sum(returns, Decimal(0)) / Decimal(len(returns))
        variance = sum((item - mean) ** 2 for item in returns) / Decimal(len(returns))
        volatility = variance.sqrt()
    else:
        volatility = None
    if any(closes[index - 1] == 0 for index in range(1, len(closes))):
        volatility = None
        volatility_state = TechnicalState.UNAVAILABLE
    else:
        volatility_state = TechnicalState.AVAILABLE if volatility is not None else TechnicalState.INSUFFICIENT_HISTORY
    signals.append(_signal("rolling_volatility", volatility, state=volatility_state, as_of=points[-1].timestamp, lookback=sma_period, basis=basis, hashes=hashes[-(sma_period + 1):], unit="ratio"))
    payload = {"security": security.model_dump(mode="json"), "as_of": as_of.astimezone(UTC).isoformat(), "signals": [signal.model_dump(mode="json") for signal in signals], "source_observation_hashes": hashes, "methodology_version": "technical-research/v1"}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TechnicalResearch(security=security, as_of=as_of.astimezone(UTC), signals=tuple(signals), source_observation_hashes=hashes, research_hash=digest)
