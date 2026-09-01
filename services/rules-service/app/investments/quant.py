"""INV-07 deterministic quantitative research contracts and calculations."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable, Sequence

from pydantic import Field, field_validator

from .contracts import DataState, InvestmentStrictModel
from .technicals import PriceSeriesPoint
from .securities import SecurityIdentity


class QuantState(StrEnum):
    AVAILABLE = "available"
    UNKNOWN = "unknown"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNAVAILABLE = "unavailable"


class QuantMetric(InvestmentStrictModel):
    schema_version: str = "QuantMetric/v1"
    name: str = Field(min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=64)
    unit: str = Field(min_length=1, max_length=24)
    state: QuantState
    as_of: datetime
    frequency: str = Field(min_length=1, max_length=24)
    lookback: int = Field(gt=0, le=500)
    price_basis: str = Field(min_length=1, max_length=32)
    methodology_version: str = "quant-calculations/v1"
    source_observation_hashes: tuple[str, ...] = Field(min_length=1, max_length=500)

    @field_validator("value")
    @classmethod
    def finite_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("quant metric must be decimal") from None
        if not number.is_finite():
            raise ValueError("quant metric must be finite")
        return format(number.normalize(), "f")

    @field_validator("as_of")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("quant as_of must be timezone-aware UTC")
        return value.astimezone(UTC)


class QuantResearch(InvestmentStrictModel):
    schema_version: str = "QuantResearch/v1"
    security: SecurityIdentity
    as_of: datetime
    metrics: tuple[QuantMetric, ...] = Field(default=(), max_length=50)
    benchmark_security_id: str | None = None
    benchmark_observation_hashes: tuple[str, ...] = ()
    risk_free_rate: str | None = None
    source_observation_hashes: tuple[str, ...] = Field(min_length=1, max_length=500)
    methodology_version: str = "quant-research/v1"
    research_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def _metric(name: str, value: Decimal | None, state: QuantState, points: Sequence[PriceSeriesPoint], lookback: int, unit: str) -> QuantMetric:
    return QuantMetric(name=name, value=format(value.normalize(), "f") if value is not None else None, unit=unit, state=state, as_of=points[-1].timestamp, frequency="observation", lookback=lookback, price_basis=points[-1].adjustment_basis.value, source_observation_hashes=tuple(point.source_observation_hash for point in points[-lookback:]))


def calculate_quant_research(security: SecurityIdentity, points: Sequence[PriceSeriesPoint], *, as_of: datetime, lookback: int = 5, risk_free_rate: Decimal | None = None, benchmark: Sequence[PriceSeriesPoint] | None = None, benchmark_security_id: str | SecurityIdentity | None = None) -> QuantResearch:
    """Calculate returns, volatility, drawdown and optional benchmark beta."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware UTC")
    points = tuple(points)
    if not points:
        raise ValueError("quant series is empty")
    closes = [Decimal(point.close) for point in points]
    hashes = tuple(point.source_observation_hash for point in points)
    if any(closes[index - 1] == 0 for index in range(1, len(closes))):
        raise ValueError("zero close denominator makes returns unavailable")
    returns = [(closes[index] / closes[index - 1]) - Decimal(1) for index in range(1, len(closes))]
    state = QuantState.AVAILABLE if len(returns) >= lookback else QuantState.INSUFFICIENT_HISTORY
    recent = returns[-lookback:] if len(returns) >= lookback else []
    cumulative = (closes[-1] / closes[0]) - Decimal(1) if len(closes) >= 2 and closes[0] != 0 else None
    mean = sum(recent, Decimal(0)) / Decimal(len(recent)) if recent else None
    variance = sum((item - mean) ** 2 for item in recent) / Decimal(len(recent)) if recent and mean is not None else None
    volatility = variance.sqrt() if variance is not None else None
    running_peak = closes[0]
    max_drawdown = Decimal(0)
    for close in closes:
        running_peak = max(running_peak, close)
        max_drawdown = min(max_drawdown, (close / running_peak) - Decimal(1))
    metrics = [_metric("cumulative_return", cumulative, QuantState.AVAILABLE if cumulative is not None else QuantState.INSUFFICIENT_HISTORY, points, max(1, len(points)), "ratio"), _metric("mean_return", mean, state, points, lookback, "ratio"), _metric("volatility", volatility, state, points, lookback, "ratio"), _metric("maximum_drawdown", max_drawdown if len(points) >= 2 else None, QuantState.AVAILABLE if len(points) >= 2 else QuantState.INSUFFICIENT_HISTORY, points, max(1, len(points)), "ratio")]
    if risk_free_rate is not None and volatility not in (None, Decimal(0)) and mean is not None:
        metrics.append(_metric("sharpe_ratio", (mean - risk_free_rate) / volatility, QuantState.AVAILABLE, points, lookback, "ratio"))
    else:
        metrics.append(_metric("sharpe_ratio", None, QuantState.UNKNOWN, points, lookback, "ratio"))
    benchmark_id = None
    if benchmark is not None:
        benchmark = tuple(benchmark)
        if len(benchmark) >= 2 and tuple(point.timestamp for point in benchmark[-len(points):]) == tuple(point.timestamp for point in points[-len(benchmark):]):
            if any(Decimal(benchmark[index - 1].close) == 0 for index in range(1, len(benchmark))):
                raise ValueError("zero benchmark close denominator makes beta unavailable")
            benchmark_returns = [(Decimal(benchmark[index].close) / Decimal(benchmark[index - 1].close)) - Decimal(1) for index in range(1, len(benchmark))]
            paired = list(zip(returns[-len(benchmark_returns):], benchmark_returns, strict=True))
            bmean = sum(item[1] for item in paired) / Decimal(len(paired)) if paired else Decimal(0)
            amean = sum(item[0] for item in paired) / Decimal(len(paired)) if paired else Decimal(0)
            covariance = sum((asset - amean) * (market - bmean) for asset, market in paired)
            variance_b = sum((market - bmean) ** 2 for _, market in paired)
            beta = covariance / variance_b if variance_b else None
            metrics.append(_metric("beta", beta, QuantState.AVAILABLE if beta is not None else QuantState.UNAVAILABLE, points, lookback, "ratio"))
            benchmark_id = benchmark_security_id.security_id if isinstance(benchmark_security_id, SecurityIdentity) else benchmark_security_id
            if benchmark_id is None:
                benchmark_id = "unresolved"
        else:
            metrics.append(_metric("beta", None, QuantState.UNAVAILABLE, points, lookback, "ratio"))
    payload = {"security": security.model_dump(mode="json"), "as_of": as_of.astimezone(UTC).isoformat(), "metrics": [metric.model_dump(mode="json") for metric in metrics], "benchmark_security_id": benchmark_id, "benchmark_observation_hashes": tuple(point.source_observation_hash for point in benchmark) if benchmark is not None else (), "risk_free_rate": str(risk_free_rate) if risk_free_rate is not None else None, "source_observation_hashes": hashes, "methodology_version": "quant-research/v1"}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return QuantResearch(security=security, as_of=as_of.astimezone(UTC), metrics=tuple(metrics), benchmark_security_id=benchmark_id, benchmark_observation_hashes=tuple(point.source_observation_hash for point in benchmark) if benchmark is not None else (), risk_free_rate=str(risk_free_rate) if risk_free_rate is not None else None, source_observation_hashes=hashes, research_hash=digest)
