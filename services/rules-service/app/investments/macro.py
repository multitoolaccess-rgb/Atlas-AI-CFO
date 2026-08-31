"""INV-06 deterministic macro observations and derived context."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable

from pydantic import Field, field_validator, model_validator

from .contracts import DataState, EvidenceReference, InvestmentStrictModel


class MacroFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    EVENT = "event"


class MacroStatus(StrEnum):
    INITIAL = "initial"
    REVISED = "revised"
    ESTIMATED = "estimated"
    DERIVED = "derived"


class MacroKind(StrEnum):
    POLICY_RATE = "policy_rate"
    TREASURY_YIELD = "treasury_yield"
    INFLATION = "inflation"
    UNEMPLOYMENT = "unemployment"
    GDP_GROWTH = "gdp_growth"


class MacroFailure(ValueError):
    """Sanitized failure for invalid external macro data."""


class MacroObservation(InvestmentStrictModel):
    schema_version: str = "MacroObservation/v1"
    observation_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    indicator_id: MacroKind
    geography: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")
    value: str | None = Field(default=None, max_length=64)
    unit: str = Field(min_length=1, max_length=24, pattern=r"^(percent|basis_points|USD|index|count|rate|ratio)$")
    frequency: MacroFrequency
    observation_period: datetime
    release_date: datetime | None = None
    effective_date: datetime | None = None
    as_known_at: datetime
    retrieved_at: datetime
    status: MacroStatus
    state: DataState
    source: EvidenceReference
    revision_of: str | None = Field(default=None, max_length=160)

    @field_validator("value")
    @classmethod
    def finite_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("macro value must be decimal") from None
        if not number.is_finite():
            raise ValueError("macro value must be finite")
        return format(number.normalize(), "f")

    @field_validator("observation_period", "release_date", "effective_date", "as_known_at", "retrieved_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("macro timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def coherent_temporal_state(self) -> "MacroObservation":
        if self.release_date and self.release_date > self.as_known_at:
            raise ValueError("as_known_at cannot precede release date")
        if self.as_known_at > self.retrieved_at:
            raise ValueError("as_known_at cannot follow retrieval")
        if self.state is DataState.OBSERVED and self.value is None:
            raise ValueError("observed macro data requires a value")
        return self

    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


class MacroDerivedMetric(InvestmentStrictModel):
    schema_version: str = "MacroDerivedMetric/v1"
    name: str = Field(min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=64)
    unit: str = Field(min_length=1, max_length=24)
    state: DataState
    as_of: datetime
    methodology_version: str = "macro-calculations/v1"
    source_observation_ids: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: str | None) -> str | None:
        if value is None:
            return value
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("derived macro value must be finite")
        return format(number.normalize(), "f")

    @field_validator("as_of")
    @classmethod
    def utc_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("macro metric as_of must be timezone-aware UTC")
        return value.astimezone(UTC)


class MacroRegime(StrEnum):
    TIGHTENING = "tightening"
    EASING = "easing"
    INFLATIONARY = "inflationary"
    DISINFLATIONARY = "disinflationary"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class MacroContext(InvestmentStrictModel):
    schema_version: str = "MacroContext/v1"
    as_of: datetime
    metrics: tuple[MacroDerivedMetric, ...] = Field(default=(), max_length=50)
    regime: MacroRegime
    source_observation_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def normalize_macro_observation(payload: dict, *, source: EvidenceReference, normalization_version: str = "macro-normalizer/v1") -> MacroObservation:
    if not isinstance(payload, dict):
        raise MacroFailure("macro payload is invalid")
    try:
        observation = MacroObservation(
            observation_id=f"{payload['indicator_id']}:{payload['observation_id']}:{normalization_version.replace('/', '.')}",
            indicator_id=MacroKind(payload["indicator_id"]), geography=str(payload["geography"]), value=str(payload["value"]) if payload.get("value") is not None else None,
            unit=str(payload["unit"]), frequency=MacroFrequency(payload["frequency"]), observation_period=payload["observation_period"], release_date=payload.get("release_date"), effective_date=payload.get("effective_date"), as_known_at=payload["as_known_at"], retrieved_at=payload["retrieved_at"], status=MacroStatus(payload.get("status", "initial")), state=DataState(payload.get("state", "observed")), source=source, revision_of=payload.get("revision_of"),
        )
        return observation
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise MacroFailure("macro payload failed validation") from exc


def derive_macro_metrics(observations: Iterable[MacroObservation], *, as_of: datetime) -> tuple[MacroDerivedMetric, ...]:
    """Derive a minimal policy-rate and yield-spread context without actions."""
    known = [item for item in observations if item.as_known_at <= as_of and item.value is not None and item.state is DataState.OBSERVED]
    metrics: list[MacroDerivedMetric] = []
    rates = sorted((item for item in known if item.indicator_id is MacroKind.TREASURY_YIELD), key=lambda item: item.observation_period)
    two_year = next((item for item in reversed(rates) if item.unit == "percent" and item.geography == "US-2Y"), None)
    ten_year = next((item for item in reversed(rates) if item.unit == "percent" and item.geography == "US-10Y"), None)
    if two_year and ten_year:
        spread = Decimal(ten_year.value) - Decimal(two_year.value)
        metrics.append(MacroDerivedMetric(name="yield_spread_10y_2y", value=format(spread.normalize(), "f"), unit="percent", state=DataState.OBSERVED, as_of=as_of.astimezone(UTC), source_observation_ids=(two_year.observation_id, ten_year.observation_id)))
    return tuple(metrics)
