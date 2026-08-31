"""INV-04 provider-neutral fundamental research contracts and calculations.

Provider payloads are normalized into immutable, source-cited facts before any
metric is calculated. No model or provider is authoritative for Atlas facts.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable

from pydantic import Field, field_validator, model_validator

from .contracts import DataState, EvidenceReference, InvestmentStrictModel
from .securities import SecurityIdentity


class FactKind(StrEnum):
    REVENUE = "revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_INCOME = "operating_income"
    NET_INCOME = "net_income"
    EPS = "eps"
    CASH = "cash"
    DEBT = "debt"
    ASSETS = "assets"
    LIABILITIES = "liabilities"
    EQUITY = "equity"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPITAL_EXPENDITURES = "capital_expenditures"
    SHARES_OUTSTANDING = "shares_outstanding"


class PeriodBasis(StrEnum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    TTM = "ttm"
    INSTANT = "instant"


class FactStatus(StrEnum):
    REPORTED = "reported"
    ESTIMATED = "estimated"
    RESTATED = "restated"
    DERIVED = "derived"


class FundamentalFailure(ValueError):
    """Sanitized failure raised when untrusted fundamental data is invalid."""


class FundamentalFact(InvestmentStrictModel):
    schema_version: str = "FundamentalFact/v1"
    fact_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    security: SecurityIdentity
    kind: FactKind
    value: str | None = Field(default=None, max_length=64)
    unit: str = Field(min_length=1, max_length=24)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    period_basis: PeriodBasis
    period_start: datetime | None = None
    period_end: datetime
    filing_date: datetime | None = None
    as_known_at: datetime
    retrieved_at: datetime
    status: FactStatus
    source: EvidenceReference
    revision_of: str | None = Field(default=None, max_length=160)

    @field_validator("value")
    @classmethod
    def finite_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("fundamental value must be a decimal") from None
        if not number.is_finite():
            raise ValueError("fundamental value must be finite")
        return format(number.normalize(), "f")

    @field_validator("period_start", "period_end", "filing_date", "as_known_at", "retrieved_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("fundamental timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_fact(self) -> "FundamentalFact":
        if self.period_start and self.period_start > self.period_end:
            raise ValueError("period_start must not follow period_end")
        if self.filing_date and self.filing_date > self.as_known_at:
            raise ValueError("as_known_at cannot precede filing date")
        if self.as_known_at > self.retrieved_at:
            raise ValueError("as_known_at cannot follow retrieval")
        if self.status is not FactStatus.DERIVED and self.value is None:
            raise ValueError("reported or estimated facts require a value")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode()).hexdigest()


class FundamentalMetric(InvestmentStrictModel):
    schema_version: str = "FundamentalMetric/v1"
    metric_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    name: str = Field(min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=64)
    unit: str = Field(min_length=1, max_length=24)
    state: DataState
    formula_version: str = Field(min_length=1, max_length=48)
    period_basis: PeriodBasis
    as_of: datetime
    source_fact_ids: tuple[str, ...] = Field(min_length=1, max_length=12)

    @field_validator("value")
    @classmethod
    def finite_metric(cls, value: str | None) -> str | None:
        if value is None:
            return None
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("metric must be finite")
        return format(number.normalize(), "f")

    @field_validator("as_of")
    @classmethod
    def metric_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("metric as_of must be timezone-aware UTC")
        return value.astimezone(UTC)


class FundamentalResearch(InvestmentStrictModel):
    schema_version: str = "FundamentalResearch/v1"
    security: SecurityIdentity
    facts: tuple[FundamentalFact, ...] = Field(default=(), max_length=100)
    metrics: tuple[FundamentalMetric, ...] = Field(default=(), max_length=100)
    as_of: datetime
    methodology_version: str = "fundamental-research/v1"
    source_fact_ids: tuple[str, ...] = Field(default=(), max_length=100)
    research_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of")
    @classmethod
    def research_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research as_of must be timezone-aware UTC")
        return value.astimezone(UTC)

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"research_hash"}), sort_keys=True, separators=(",", ":"))


def normalize_fundamental_fact(payload: dict, *, security: SecurityIdentity, source: EvidenceReference, normalization_version: str = "fundamental-normalizer/v1") -> FundamentalFact:
    """Normalize one bounded provider payload; raw provider fields do not escape."""
    if not isinstance(payload, dict):
        raise FundamentalFailure("fundamental payload is invalid")
    try:
        fact = FundamentalFact(
            fact_id=f"{security.security_id}:{payload['fact_id']}:{normalization_version.replace('/', '.')}",
            security=security,
            kind=FactKind(payload["kind"]),
            value=str(payload["value"]) if payload.get("value") is not None else None,
            unit=str(payload["unit"]), currency=payload.get("currency"),
            period_basis=PeriodBasis(payload["period_basis"]),
            period_start=payload.get("period_start"), period_end=payload["period_end"],
            filing_date=payload.get("filing_date"), as_known_at=payload["as_known_at"],
            retrieved_at=payload["retrieved_at"], status=FactStatus(payload.get("status", "reported")),
            source=source, revision_of=payload.get("revision_of"),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise FundamentalFailure("fundamental payload failed validation") from exc
    return fact


def _ratio(name: str, numerator: FundamentalFact, denominator: FundamentalFact, *, as_of: datetime, formula_version: str = "fundamental-metrics/v1") -> FundamentalMetric:
    if numerator.currency != denominator.currency or numerator.period_basis != denominator.period_basis or numerator.period_end != denominator.period_end:
        return FundamentalMetric(metric_id=f"{name}:{numerator.fact_id}:{denominator.fact_id}", name=name, value=None, unit="ratio", state=DataState.UNKNOWN, formula_version=formula_version, period_basis=numerator.period_basis, as_of=as_of, source_fact_ids=(numerator.fact_id, denominator.fact_id))
    divisor = Decimal(denominator.value) if denominator.value is not None else Decimal(0)
    value = None if divisor == 0 or numerator.value is None else format((Decimal(numerator.value) / divisor).normalize(), "f")
    return FundamentalMetric(metric_id=f"{name}:{numerator.fact_id}:{denominator.fact_id}", name=name, value=value, unit="ratio", state=DataState.OBSERVED if value is not None else DataState.UNKNOWN, formula_version=formula_version, period_basis=numerator.period_basis, as_of=as_of, source_fact_ids=(numerator.fact_id, denominator.fact_id))


def derive_metrics(facts: Iterable[FundamentalFact], *, as_of: datetime) -> tuple[FundamentalMetric, ...]:
    """Calculate a minimal deterministic margin set from matching facts."""
    facts = tuple(facts)
    by_kind = {fact.kind: fact for fact in facts if fact.status is not FactStatus.ESTIMATED}
    metrics: list[FundamentalMetric] = []
    revenue = by_kind.get(FactKind.REVENUE)
    if revenue:
        for kind, name in ((FactKind.GROSS_PROFIT, "gross_margin"), (FactKind.OPERATING_INCOME, "operating_margin"), (FactKind.NET_INCOME, "net_margin"), (FactKind.OPERATING_CASH_FLOW, "cash_flow_margin")):
            fact = by_kind.get(kind)
            if fact:
                metrics.append(_ratio(name, fact, revenue, as_of=as_of))
    return tuple(metrics)
