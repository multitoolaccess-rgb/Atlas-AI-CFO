"""UI-11 server-owned current-only portfolio risk/scenario boundary.

This module deliberately supports descriptive exposure and data-quality
metrics only. It does not calculate a risk score, probability, optimizer,
portfolio return, or execution instruction. Holdings are current source rows,
so every baseline is explicitly current-only and never historical.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Holding
from .contracts import InvestmentStrictModel
from .holding_identity import HoldingIdentityPolicy, identity_for_holding
from .securities import SecurityIdentity, SecurityState

_MAX_DELTA = Decimal("1000000000000")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class RiskBoundaryError(ValueError):
    """Sanitized UI-11 domain failure."""


class RiskNotFound(RiskBoundaryError):
    """A requested owner-scoped risk resource is unavailable."""


class RiskConflict(RiskBoundaryError):
    """The requested baseline no longer matches the server projection."""


class BaselineCapability(StrEnum):
    CURRENT_ONLY = "current_only"
    HISTORICAL_CAPABLE = "historical_capable"
    UNAVAILABLE = "unavailable"


class BaselineCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class RiskDataState(StrEnum):
    AVAILABLE = "available"
    UNKNOWN = "unknown"
    MISSING = "missing"
    STALE = "stale"
    UNSUPPORTED = "unsupported"
    INCOMPATIBLE = "incompatible"
    UNAVAILABLE = "unavailable"


class RiskPosition(InvestmentStrictModel):
    """Server-derived position data; account identity is intentionally omitted."""

    position_id: int = Field(gt=0)
    security: SecurityIdentity
    quantity: str | None = Field(default=None, max_length=48)
    market_value: str | None = Field(default=None, max_length=48)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    market_value_state: RiskDataState
    exposure_percentage: str | None = Field(default=None, max_length=48)
    exposure_state: RiskDataState = RiskDataState.UNAVAILABLE
    cost_basis: str | None = Field(default=None, max_length=48)
    cost_basis_state: RiskDataState
    as_of: datetime
    source_id: str = Field(min_length=1, max_length=80)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of")
    @classmethod
    def utc_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("position as_of must be timezone-aware UTC")
        return value.astimezone(UTC)


class RiskMetric(InvestmentStrictModel):
    """One descriptive metric with an explicit semantic state."""

    name: str = Field(min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=48)
    unit: str = Field(min_length=1, max_length=24)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    state: RiskDataState
    limitation: str | None = Field(default=None, max_length=240)


class InvestmentPortfolioBaseline(InvestmentStrictModel):
    """Immutable-in-memory, owner-scoped current portfolio projection."""

    schema_version: Literal["InvestmentPortfolioBaseline/v1"] = "InvestmentPortfolioBaseline/v1"
    baseline_id: str = Field(pattern=r"^portfolio-baseline:[a-f0-9]{32}$")
    owner_id: int = Field(gt=0)
    as_of: datetime
    as_known_at: datetime | None = None
    capability: BaselineCapability
    positions: tuple[RiskPosition, ...] = Field(default=(), max_length=500)
    total_value: str | None = Field(default=None, max_length=48)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    metrics: tuple[RiskMetric, ...] = Field(default=(), max_length=50)
    completeness: BaselineCompleteness
    omissions: tuple[str, ...] = Field(default=(), max_length=50)
    freshness: RiskDataState
    methodology_version: str = "ui11-current-portfolio/v1"
    calculation_version: str = "ui11-baseline/v1"
    source_ids: tuple[str, ...] = Field(default=(), max_length=1000)
    source_hashes: tuple[str, ...] = Field(default=(), max_length=1000)
    baseline_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of", "as_known_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("baseline timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def coherent_timestamps(self) -> "InvestmentPortfolioBaseline":
        if self.as_known_at is not None and self.as_known_at > self.as_of:
            raise ValueError("as_known_at cannot be later than as_of")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude={"owner_id", "baseline_id", "baseline_hash"}),
            sort_keys=True,
            separators=(",", ":"),
        )


class PortfolioBaselineResponse(InvestmentStrictModel):
    """Public typed baseline response without the internal owner identifier."""

    schema_version: Literal["InvestmentPortfolioBaseline/v1"] = "InvestmentPortfolioBaseline/v1"
    baseline_id: str
    as_of: datetime
    as_known_at: datetime | None
    capability: BaselineCapability
    positions: tuple[RiskPosition, ...]
    total_value: str | None
    currency: str | None
    metrics: tuple[RiskMetric, ...]
    completeness: BaselineCompleteness
    omissions: tuple[str, ...]
    freshness: RiskDataState
    methodology_version: str
    calculation_version: str
    source_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    baseline_hash: str


class RiskScenarioRequest(InvestmentStrictModel):
    """Bounded hypothetical intent; all financial authority is server-derived."""

    schema_version: Literal["InvestmentRiskScenarioRequest/v1"] = "InvestmentRiskScenarioRequest/v1"
    baseline_id: str | None = Field(default=None, pattern=r"^portfolio-baseline:[a-f0-9]{32}$")
    position_id: int = Field(gt=0)
    market_value_delta: str = Field(min_length=1, max_length=48)

    @field_validator("market_value_delta")
    @classmethod
    def canonical_delta(cls, value: str) -> str:
        try:
            decimal = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("market_value_delta must be a decimal") from None
        if not decimal.is_finite() or abs(decimal) > _MAX_DELTA:
            raise ValueError("market_value_delta is outside the supported bound")
        return format(decimal.normalize(), "f")


class InvestmentRiskScenario(InvestmentStrictModel):
    """Non-persistent, deterministic, explicitly hypothetical preview."""

    schema_version: Literal["InvestmentRiskScenario/v1"] = "InvestmentRiskScenario/v1"
    scenario_id: str = Field(pattern=r"^investment-risk-scenario:[a-f0-9]{32}$")
    owner_id: int = Field(gt=0)
    baseline_id: str
    baseline_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    inputs: RiskScenarioRequest
    metrics: tuple[RiskMetric, ...]
    source_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    as_of: datetime
    as_known_at: datetime | None
    evaluated_at: datetime
    methodology_version: str = "ui11-exposure-preview/v1"
    calculation_version: str = "ui11-scenario/v1"
    hypothetical: bool = True
    predictive: bool = False
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    limitations: tuple[str, ...] = Field(default=(), max_length=50)
    warnings: tuple[str, ...] = Field(default=(), max_length=50)

    @field_validator("as_of", "as_known_at", "evaluated_at")
    @classmethod
    def utc_scenario_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scenario timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def non_predictive_preview(self) -> "InvestmentRiskScenario":
        if not self.hypothetical or self.predictive:
            raise ValueError("UI-11 scenarios must be hypothetical and non-predictive")
        if self.as_known_at is not None and self.as_known_at > self.as_of:
            raise ValueError("scenario known-at time cannot be later than as_of")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware UTC")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude={"owner_id", "scenario_id", "result_hash", "evaluated_at"}),
            sort_keys=True,
            separators=(",", ":"),
        )


class RiskScenarioResponse(InvestmentStrictModel):
    """Public typed scenario response without the internal owner identifier."""

    schema_version: Literal["InvestmentRiskScenario/v1"] = "InvestmentRiskScenario/v1"
    scenario_id: str
    baseline_id: str
    baseline_hash: str
    inputs: RiskScenarioRequest
    metrics: tuple[RiskMetric, ...]
    source_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    as_of: datetime
    as_known_at: datetime | None
    evaluated_at: datetime
    methodology_version: str
    calculation_version: str
    hypothetical: bool
    predictive: bool
    result_hash: str
    limitations: tuple[str, ...]
    warnings: tuple[str, ...]


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    # SQLite returns legacy UTC columns without tzinfo even when the
    # application wrote timezone-aware values. Treat those persisted
    # values as UTC at this boundary; never silently discard them,
    # otherwise future-source validation can be bypassed on SQLite.
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decimal(value: Any) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return format(number.normalize(), "f")


def _identity(holding: Holding, as_of: datetime) -> SecurityIdentity:
    # GAP-09: shared resolver under the ADR-UI-11 MASTER_VERIFIED_ONLY policy.
    # Outputs are identical to the former local derivation: holdings never
    # promote ticker/type inference to canonical identity because the
    # holdings source path carries no verified security master.
    return identity_for_holding(
        holding,
        policy=HoldingIdentityPolicy.MASTER_VERIFIED_ONLY,
        as_of=as_of,
    )


def _source_hash(holding: Holding, account: Account) -> str:
    payload = {
        "holding_id": holding.id,
        "account_id": holding.account_id,
        "symbol": holding.symbol,
        "description": holding.description,
        "quantity": _decimal(holding.quantity),
        "last_price": _decimal(holding.last_price),
        "current_value": _decimal(holding.current_value),
        "cost_basis_total": _decimal(holding.cost_basis_total),
        "type": holding.type,
        "currency": account.currency_code,
        "observed_at": (_utc(holding.updated_at) or _utc(holding.created_at)).isoformat() if (_utc(holding.updated_at) or _utc(holding.created_at)) else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _metric(name: str, value: str | None, unit: str, currency: str | None, state: RiskDataState, limitation: str | None = None) -> RiskMetric:
    return RiskMetric(name=name, value=value, unit=unit, currency=currency, state=state, limitation=limitation)


def _public_baseline(baseline: InvestmentPortfolioBaseline) -> PortfolioBaselineResponse:
    return PortfolioBaselineResponse(**baseline.model_dump(exclude={"owner_id"}))


def _public_scenario(scenario: InvestmentRiskScenario) -> RiskScenarioResponse:
    return RiskScenarioResponse(**scenario.model_dump(exclude={"owner_id"}))


class InvestmentRiskService:
    """Build and validate owner-scoped baseline and non-mutating previews."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_portfolio_baseline(self, *, owner_id: int) -> InvestmentPortfolioBaseline:
        accounts = list(self._session.scalars(select(Account).where(Account.user_id == owner_id, Account.is_active.is_(True))))
        account_map = {int(account.id): account for account in accounts}
        holdings = list(self._session.scalars(select(Holding).where(Holding.account_id.in_(tuple(account_map))))) if account_map else []
        holdings.sort(key=lambda item: (int(item.account_id), int(item.id)))
        positions: list[RiskPosition] = []
        source_ids: list[str] = []
        source_hashes: list[str] = []
        omissions: list[str] = []
        timestamps: list[datetime] = []
        currencies = {account.currency_code for account in accounts if account.currency_code}
        now = datetime.now(UTC)
        for account in accounts:
            for timestamp in (
                _utc(getattr(account, "last_sync", None)),
                _utc(getattr(account, "updated_at", None)),
                _utc(getattr(account, "created_at", None)),
                _utc(getattr(account, "currency_observed_at", None)),
            ):
                if timestamp is not None:
                    if timestamp > now:
                        raise RiskBoundaryError("future portfolio source timestamp is unavailable")
                    timestamps.append(timestamp)
        for holding in holdings:
            account = account_map.get(int(holding.account_id))
            if account is None:
                continue
            observed_at = _utc(holding.updated_at) or _utc(holding.created_at)
            if observed_at is not None:
                if observed_at > now:
                    raise RiskBoundaryError("future portfolio source timestamp is unavailable")
                timestamps.append(observed_at)
            currency = account.currency_code if account.currency_code in {"USD"} else None
            value = _decimal(holding.current_value)
            quantity = _decimal(holding.quantity)
            cost = _decimal(holding.cost_basis_total)
            source_id = f"holding:{holding.id}"
            source_hash = _source_hash(holding, account)
            source_ids.append(source_id)
            source_hashes.append(source_hash)
            identity = _identity(holding, observed_at or _EPOCH)
            price = _decimal(holding.last_price)
            valid_price = price is not None and Decimal(price) > 0
            value_state = RiskDataState.AVAILABLE if value is not None and valid_price and currency else RiskDataState.UNKNOWN
            if not currency:
                omissions.append(f"holding:{holding.id}:currency_unavailable")
            if value is None or not valid_price:
                omissions.append(f"holding:{holding.id}:market_value_unavailable")
            if identity.state is not SecurityState.RESOLVED:
                omissions.append(f"holding:{holding.id}:security_identity_{identity.state.value}")
            positions.append(RiskPosition(
                position_id=int(holding.id), security=identity, quantity=quantity, market_value=value,
                currency=currency, market_value_state=value_state, cost_basis=cost,
                cost_basis_state=RiskDataState.AVAILABLE if cost is not None and currency else RiskDataState.UNKNOWN,
                as_of=observed_at or _EPOCH, source_id=source_id, source_hash=source_hash,
            ))
        as_of = max(timestamps, default=_EPOCH)
        as_known_at = as_of if as_of != _EPOCH else None
        compatible_currency = next(iter(currencies)) if len(currencies) == 1 and currencies <= {"USD"} else None
        complete_values = bool(positions) and all(item.market_value_state is RiskDataState.AVAILABLE for item in positions)
        total: str | None = None
        if complete_values and compatible_currency:
            total = format(sum((Decimal(item.market_value or "0") for item in positions), Decimal(0)).normalize(), "f")
        elif positions:
            omissions.append("portfolio_total_unavailable_until_currency_and_values_are_complete")
        if len(currencies) > 1:
            omissions.append("mixed_currency_portfolio_is_not_comparable")
        if not positions:
            completeness = BaselineCompleteness.UNKNOWN
            freshness = RiskDataState.UNAVAILABLE
            omissions.append("no_active_holdings")
        elif complete_values and compatible_currency:
            # Identity omissions do not invalidate value aggregation;
            # identity-dependent grouping remains explicitly unavailable.
            completeness = BaselineCompleteness.COMPLETE
            freshness = RiskDataState.AVAILABLE
        else:
            completeness = BaselineCompleteness.PARTIAL
            freshness = RiskDataState.UNKNOWN
        if total is not None and Decimal(total) != 0 and compatible_currency:
            positions = [
                position.model_copy(update={
                    "exposure_percentage": format((Decimal(position.market_value or "0") / Decimal(total) * 100).normalize(), "f"),
                    "exposure_state": RiskDataState.AVAILABLE,
                }) if position.market_value_state is RiskDataState.AVAILABLE and position.currency == compatible_currency else position
                for position in positions
            ]
        else:
            positions = [
                position.model_copy(update={
                    "exposure_state": RiskDataState.UNAVAILABLE,
                }) for position in positions
            ]
            if positions:
                omissions.append("position_exposure_unavailable_without_nonzero_compatible_total")
        valid_values = [item for item in positions if item.market_value_state is RiskDataState.AVAILABLE]
        metrics: list[RiskMetric] = [
            _metric("position_count", str(len(positions)), "count", None, RiskDataState.AVAILABLE),
            _metric("observed_position_count", str(len(valid_values)), "count", compatible_currency, RiskDataState.AVAILABLE if valid_values else RiskDataState.UNKNOWN),
            _metric("total_value", total, "currency", compatible_currency, RiskDataState.AVAILABLE if total is not None else RiskDataState.UNAVAILABLE, None if total is not None else "currency and complete observed values are required"),
            _metric("unresolved_or_unsupported_identity_count", str(sum(item.security.state is not SecurityState.RESOLVED for item in positions)), "count", None, RiskDataState.AVAILABLE),
            _metric("portfolio_volatility", None, "ratio", None, RiskDataState.UNAVAILABLE, "portfolio volatility methodology is not approved for UI-11"),
            _metric("portfolio_drawdown", None, "ratio", None, RiskDataState.UNAVAILABLE, "historical portfolio valuation is unavailable"),
        ]
        provisional = InvestmentPortfolioBaseline(
            baseline_id="portfolio-baseline:" + "0" * 32, owner_id=owner_id, as_of=as_of,
            as_known_at=as_known_at, capability=BaselineCapability.CURRENT_ONLY,
            positions=tuple(positions), total_value=total, currency=compatible_currency,
            metrics=tuple(metrics), completeness=completeness, omissions=tuple(dict.fromkeys(omissions)),
            freshness=freshness, source_ids=tuple(source_ids), source_hashes=tuple(source_hashes),
            baseline_hash="0" * 64,
        )
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return provisional.model_copy(update={"baseline_id": "portfolio-baseline:" + digest[:32], "baseline_hash": digest})

    def preview_investment_risk_scenario(self, *, owner_id: int, request: RiskScenarioRequest) -> InvestmentRiskScenario:
        baseline = self.get_portfolio_baseline(owner_id=owner_id)
        if request.baseline_id is not None and request.baseline_id != baseline.baseline_id:
            raise RiskConflict("baseline is stale")
        target = next((position for position in baseline.positions if position.position_id == request.position_id), None)
        if target is None:
            raise RiskNotFound("position not found")
        if baseline.currency is None or baseline.total_value is None or baseline.completeness is not BaselineCompleteness.COMPLETE:
            raise RiskConflict("baseline is incomplete for hypothetical comparison")
        if target.market_value is None or target.currency != baseline.currency:
            raise RiskConflict("position value is unavailable for hypothetical comparison")
        delta = Decimal(request.market_value_delta)
        resulting_value = Decimal(target.market_value) + delta
        if resulting_value < 0:
            raise RiskBoundaryError("hypothetical value cannot be negative")
        resulting_total = Decimal(baseline.total_value) + delta
        if resulting_total <= 0:
            raise RiskBoundaryError("hypothetical total must remain positive")
        metrics = (
            _metric("baseline_total_value", baseline.total_value, "currency", baseline.currency, RiskDataState.AVAILABLE),
            _metric("hypothetical_total_value", format(resulting_total.normalize(), "f"), "currency", baseline.currency, RiskDataState.AVAILABLE),
            _metric("total_value_delta", format(delta.normalize(), "f"), "currency", baseline.currency, RiskDataState.AVAILABLE),
            _metric("baseline_position_exposure", format((Decimal(target.market_value) / Decimal(baseline.total_value) * 100).normalize(), "f"), "percent", baseline.currency, RiskDataState.AVAILABLE),
            _metric("hypothetical_position_exposure", format((resulting_value / resulting_total * 100).normalize(), "f"), "percent", baseline.currency, RiskDataState.AVAILABLE),
            _metric("portfolio_volatility", None, "ratio", None, RiskDataState.UNAVAILABLE, "portfolio volatility methodology is not approved for UI-11"),
        )
        provisional = InvestmentRiskScenario(
            scenario_id="investment-risk-scenario:" + "0" * 32, owner_id=owner_id,
            baseline_id=baseline.baseline_id, baseline_hash=baseline.baseline_hash, inputs=request,
            metrics=metrics, source_ids=baseline.source_ids, source_hashes=baseline.source_hashes,
            as_of=baseline.as_of, as_known_at=baseline.as_known_at, evaluated_at=datetime.now(UTC),
            hypothetical=True, predictive=False,
            result_hash="0" * 64,
            limitations=("Current-only baseline; historical portfolio reconstruction is unavailable.", "Descriptive exposure preview only; no return or risk prediction is calculated."),
            warnings=("Hypothetical analysis only. This is not a prediction, recommendation, allocation instruction, or execution.",),
        )
        digest = hashlib.sha256(provisional.canonical_payload().encode()).hexdigest()
        return provisional.model_copy(update={"scenario_id": "investment-risk-scenario:" + digest[:32], "result_hash": digest})


__all__ = [
    "BaselineCapability", "BaselineCompleteness", "InvestmentPortfolioBaseline",
    "InvestmentRiskScenario", "InvestmentRiskService", "PortfolioBaselineResponse",
    "RiskBoundaryError", "RiskConflict", "RiskDataState", "RiskNotFound",
    "RiskMetric", "RiskPosition", "RiskScenarioRequest", "RiskScenarioResponse",
]
