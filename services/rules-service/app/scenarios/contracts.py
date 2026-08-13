"""Strict, server-safe Scenario Lab contracts.

The request contract contains only explicit scenario controls. Ownership,
canonical state, provenance, baseline snapshots, hashes, model versions, and
results are server-derived and therefore cannot be supplied by a client.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.forecasts.canonical_state import validate_canonical_decimal

SCENARIO_SCHEMA_VERSION = "atlas-scenario-lab/v1"
SCENARIO_MODEL_VERSION = "atlas-scenario-lab/v1"
MAX_SCENARIO_STRING_LENGTH = 128
MAX_SCENARIO_HORIZON_MONTHS = 2_400
MAX_SCENARIO_COLLECTION_SIZE = 3
MAX_SCENARIO_AMOUNT_ABS = Decimal("1E+24")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class ScenarioInputError(ValueError):
    """Sanitized deterministic scenario-input failure."""


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class OneTimeOutflow(_StrictRequest):
    """One positive outflow applied once at a mapped month-end boundary."""

    date: date
    amount: str = Field(min_length=1, max_length=40)

    @field_validator("amount")
    @classmethod
    def amount_is_positive_canonical_decimal(cls, value: str) -> str:
        try:
            validate_canonical_decimal(value)
            parsed = Decimal(value)
        except Exception as exc:
            raise ValueError("outflow amount must be a canonical decimal") from exc
        if parsed <= 0 or abs(parsed) > MAX_SCENARIO_AMOUNT_ABS:
            raise ValueError("outflow amount is outside the supported positive bound")
        return value


class ScenarioInput(_StrictRequest):
    """Explicit bounded changes accepted by the Scenario Lab MVP."""

    scenario_id: str | None = Field(default=None, min_length=36, max_length=36)
    monthly_contribution_delta: str | None = Field(default=None, min_length=1, max_length=40)
    contribution_start_date: date | None = None
    contribution_stop_date: date | None = None
    one_time_outflow: OneTimeOutflow | None = None

    @field_validator("scenario_id")
    @classmethod
    def scenario_id_is_lower_uuid(cls, value: str | None) -> str | None:
        if value is not None and not _UUID_RE.fullmatch(value):
            raise ValueError("scenario_id must be a lowercase canonical UUID")
        return value

    @field_validator("monthly_contribution_delta")
    @classmethod
    def contribution_delta_is_canonical_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            validate_canonical_decimal(value)
            if abs(Decimal(value)) > MAX_SCENARIO_AMOUNT_ABS:
                raise ValueError
        except Exception as exc:
            raise ValueError("monthly contribution delta must be a canonical decimal") from exc
        return value

    @field_validator("contribution_start_date", "contribution_stop_date", mode="before")
    @classmethod
    def date_is_iso_date(cls, value: Any) -> Any:
        if value is None or isinstance(value, date):
            return value
        if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
            raise ValueError("scenario dates must be ISO date-only values")
        return value

    @model_validator(mode="after")
    def has_at_least_one_change(self) -> "ScenarioInput":
        if all(
            value is None
            for value in (
                self.monthly_contribution_delta,
                self.contribution_start_date,
                self.contribution_stop_date,
                self.one_time_outflow,
            )
        ):
            raise ValueError("at least one supported scenario change is required")
        if (
            self.contribution_start_date is not None
            and self.contribution_stop_date is not None
            and self.contribution_start_date > self.contribution_stop_date
        ):
            raise ValueError("contribution start date cannot be after stop date")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        """Return sorted, hash-ready values without server-owned fields."""

        return {
            "contribution_start_date": self.contribution_start_date.isoformat()
            if self.contribution_start_date
            else None,
            "contribution_stop_date": self.contribution_stop_date.isoformat()
            if self.contribution_stop_date
            else None,
            "monthly_contribution_delta": self.monthly_contribution_delta,
            "one_time_outflow": (
                {
                    "amount": self.one_time_outflow.amount,
                    "date": self.one_time_outflow.date.isoformat(),
                }
                if self.one_time_outflow
                else None
            ),
        }


class ScenarioCompareRequest(_StrictRequest):
    """Strict body for comparing at most three saved scenarios."""

    scenario_ids: tuple[str, ...] = Field(min_length=1, max_length=3)

    @field_validator("scenario_ids", mode="before")
    @classmethod
    def coerce_ids(cls, value: Any) -> Any:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("scenario_ids")
    @classmethod
    def ids_are_lower_uuids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not _UUID_RE.fullmatch(item) for item in value):
            raise ValueError("scenario_ids must be unique lowercase UUIDs")
        return value
