"""INV-02 provider boundary.

Provider payloads terminate here. Only validated canonical SecurityIdentity and
MarketObservation values leave this module.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol

from .errors import InvestmentFailure
from .contracts import DataState
from .market_observations import AdjustmentBasis, MarketObservation, ObservationQuality
from .securities import InstrumentType, SecurityIdentifier, SecurityIdentity, SecurityState, security_id_for


class ObservationFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class ProviderPayloadError(ValueError):
    """Sanitized provider payload failure."""


class SecurityDataProvider(Protocol):
    """Minimal provider-neutral capability surface required by INV-02."""

    def resolve_security(self, symbol: str, exchange: str | None = None) -> dict[str, Any] | None: ...

    def get_observation(self, provider_security_id: str) -> dict[str, Any] | None: ...

    def get_historical_observations(self, provider_security_id: str) -> list[dict[str, Any]]: ...


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ProviderPayloadError(f"{field} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderPayloadError(f"{field} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProviderPayloadError(f"{field} timestamp must include timezone")
    return parsed.astimezone(UTC)


def _decimal(value: Any, field: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ProviderPayloadError(f"{field} numeric value is invalid") from exc
    if not number.is_finite():
        raise ProviderPayloadError(f"{field} numeric value is invalid")
    return format(number.normalize(), "f")


def _currency(value: Any) -> str:
    if not isinstance(value, str) or len(value.strip()) != 3 or not value.strip().isalpha():
        raise ProviderPayloadError("currency is invalid")
    return value.strip().upper()


def _instrument(value: Any) -> InstrumentType:
    if not isinstance(value, str):
        raise ProviderPayloadError("instrument type is unknown")
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "equity": InstrumentType.EQUITY,
        "stock": InstrumentType.EQUITY,
        "etf": InstrumentType.ETF,
        "mutual_fund": InstrumentType.MUTUAL_FUND,
        "fund": InstrumentType.MUTUAL_FUND,
        "index": InstrumentType.INDEX,
        "adr": InstrumentType.ADR,
        "cash": InstrumentType.CASH,
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise ProviderPayloadError("instrument type is unknown") from exc


def _freshness(observed_at: datetime, retrieved_at: datetime, max_age: timedelta) -> ObservationFreshness:
    age = retrieved_at - observed_at
    if age < timedelta(0):
        raise ProviderPayloadError("observation timestamp is in the future")
    return ObservationFreshness.FRESH if age <= max_age else ObservationFreshness.STALE


def normalize_security(payload: dict[str, Any], *, normalization_version: str = "security-normalizer/v1") -> SecurityIdentity:
    """Convert an untrusted provider security record to canonical identity."""
    if not isinstance(payload, dict):
        raise ProviderPayloadError("security payload is invalid")
    provider = str(payload.get("provider", "")).strip().lower()
    provider_id = str(payload.get("provider_id", "")).strip()
    symbol = payload.get("symbol")
    exchange = payload.get("exchange")
    if not provider or not provider_id or not isinstance(symbol, str) or not symbol.strip():
        raise ProviderPayloadError("security identity is incomplete")
    if not isinstance(exchange, str) or not exchange.strip():
        raise ProviderPayloadError("exchange is required")
    state_raw = str(payload.get("state", "resolved")).strip().lower()
    try:
        state = SecurityState(state_raw)
    except ValueError as exc:
        raise ProviderPayloadError("security state is invalid") from exc
    instrument = _instrument(payload.get("instrument_type"))
    currency = _currency(payload["currency"]) if payload.get("currency") is not None else None
    sid = security_id_for(namespace=f"{provider}:{exchange}", value=provider_id)
    identifiers = (SecurityIdentifier(namespace=f"provider.{provider}", value=provider_id),)
    return SecurityIdentity(
        security_id=sid,
        state=state,
        instrument_type=instrument,
        symbol=symbol,
        exchange=exchange,
        currency=currency,
        issuer_id=str(payload["issuer_id"]) if payload.get("issuer_id") else None,
        identifiers=identifiers,
        as_of=_utc(payload["as_of"], "as_of"),
    )


def normalize_observation(
    payload: dict[str, Any],
    *,
    security: SecurityIdentity,
    retrieved_at: datetime,
    normalization_version: str = "observation-normalizer/v1",
    max_age: timedelta = timedelta(days=1),
) -> MarketObservation:
    """Convert one provider observation into a validated canonical observation."""
    if not isinstance(payload, dict):
        raise ProviderPayloadError("observation payload is invalid")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ProviderPayloadError("retrieved_at must be timezone-aware UTC")
    retrieved_at = retrieved_at.astimezone(UTC)
    observed_at = _utc(payload.get("observed_at"), "observed_at")
    as_of = _utc(payload.get("as_of"), "as_of")
    if as_of > retrieved_at:
        raise ProviderPayloadError("as_of cannot be later than retrieval")
    currency = _currency(payload.get("currency"))
    state = _freshness(observed_at, retrieved_at, max_age)
    raw_state = str(payload.get("data_state", "observed")).strip().lower()
    if raw_state in {"estimated", "missing", "unknown"}:
        state = ObservationFreshness.UNKNOWN if raw_state == "unknown" else ObservationFreshness(raw_state)
    source = str(payload.get("source", "")).strip()
    source_identifier = str(payload.get("provider_id", "")).strip()
    if not source or not source_identifier:
        raise ProviderPayloadError("observation provenance is incomplete")
    return MarketObservation.with_hash(
        security=security,
        observed_value=_decimal(payload.get("value"), "value"),
        currency=currency,
        observation_time=observed_at,
        as_of=as_of,
        retrieved_at=retrieved_at,
        source=source,
        source_identifier=f"{normalization_version}:{source_identifier}",
        freshness=DataState.OBSERVED if state is ObservationFreshness.FRESH else DataState.STALE,
        adjustment_basis=AdjustmentBasis(str(payload.get("adjustment_basis", "unknown"))),
        quality=ObservationQuality.VALIDATED,
        observation_hash="0" * 64,
    )


class FixtureSecurityDataProvider:
    """Deterministic offline provider used to prove the adapter boundary."""

    def __init__(self, security: dict[str, Any], observations: dict[str, dict[str, Any]], history: dict[str, list[dict[str, Any]]]):
        self._security = security
        self._observations = observations
        self._history = history

    def resolve_security(self, symbol: str, exchange: str | None = None) -> dict[str, Any] | None:
        if self._security.get("symbol", "").upper() != symbol.strip().upper():
            return None
        if exchange and self._security.get("exchange", "").upper() != exchange.strip().upper():
            return None
        return dict(self._security)

    def get_observation(self, provider_security_id: str) -> dict[str, Any] | None:
        payload = self._observations.get(provider_security_id)
        return dict(payload) if payload else None

    def get_historical_observations(self, provider_security_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self._history.get(provider_security_id, [])]
