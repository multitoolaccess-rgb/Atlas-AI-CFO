"""INV-02 market observation contracts with point-in-time provenance."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .contracts import DataState, InvestmentStrictModel
from .securities import SecurityIdentity


class AdjustmentBasis(StrEnum):
    UNADJUSTED = "unadjusted"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN_ADJUSTED = "total_return_adjusted"
    UNKNOWN = "unknown"


class ObservationQuality(StrEnum):
    VALIDATED = "validated"
    PARTIAL = "partial"
    INVALID = "invalid"


class MarketObservation(InvestmentStrictModel):
    schema_version: Literal["MarketObservation/v1"] = "MarketObservation/v1"
    security: SecurityIdentity
    observed_value: str | None = Field(default=None, max_length=48)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    observation_time: datetime
    as_of: datetime
    retrieved_at: datetime
    source: str = Field(min_length=1, max_length=160)
    source_identifier: str | None = Field(default=None, max_length=160)
    freshness: DataState
    adjustment_basis: AdjustmentBasis = AdjustmentBasis.UNKNOWN
    quality: ObservationQuality
    observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("observation_time", "as_of", "retrieved_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @field_validator("observed_value")
    @classmethod
    def finite_value(cls, value: str | None) -> str | None:
        if value is None:
            return value
        from decimal import Decimal
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("observed_value must be finite")
        return format(number.normalize(), "f")

    @model_validator(mode="after")
    def coherent_state(self) -> "MarketObservation":
        if self.freshness == DataState.OBSERVED and self.observed_value is None:
            raise ValueError("observed data requires a value")
        if self.quality == ObservationQuality.INVALID:
            raise ValueError("invalid observations cannot enter canonical contracts")
        if self.as_of > self.retrieved_at:
            raise ValueError("as_of cannot be later than retrieval")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"observation_hash"}), sort_keys=True, separators=(",", ":"))

    @classmethod
    def with_hash(cls, **values) -> "MarketObservation":
        provisional = cls.model_validate({**values, "observation_hash": "0" * 64})
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return cls.model_validate({**values, "observation_hash": digest})
