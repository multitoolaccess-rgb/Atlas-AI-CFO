"""GAP-09 — single shared holding→security-identity resolver.

Before this module, two independent modules derived a ``SecurityIdentity``
from the same ``Account``/``Holding`` row with contradictory semantics:

- ``portfolio_intelligence._identity`` promoted symbol + known instrument
  type to a **resolved** canonical key (``atlas-security`` namespace).
- ``risk_scenarios._identity`` refused to promote ticker/type inference
  because holdings carry no verified security-master reference, producing
  an ``atlas-unresolved`` key with ``SecurityState.UNRESOLVED``.

Both behaviors were deliberate for their surfaces (INV-03 portfolio
projection and the ADR-UI-11 risk boundary respectively), but duplicating
the derivation in two places allowed drift: the same holding could receive
two different ``security_id`` strings depending on which module ran.

This module provides **one** implementation. Callers declare which
resolution policy applies to their surface:

- ``HoldingIdentityPolicy.CANONICAL`` — the frozen INV-12 D-2 rule used by
  INV-03 portfolio projections and the INV-12 durable observation/snapshot
  stores: a holding with a symbol and a known instrument type resolves to
  the ``atlas-security`` namespace with ``SecurityState.RESOLVED``;
  everything else stays ``atlas-unresolved``/``UNSUPPORTED`` and is
  ineligible for INV-12 storage and evaluation. Equality is exact
  ``security_id`` string equality; alias/name matching is never applied.
- ``HoldingIdentityPolicy.MASTER_VERIFIED_ONLY`` — the certified UI-11 risk
  boundary (ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY): no holding is ever
  promoted to ``RESOLVED`` because the holdings source path carries no
  verified security master. Symbol + known type → ``UNRESOLVED`` under
  ``atlas-unresolved``; symbol with an unsupported type → ``UNSUPPORTED``
  under ``atlas-unsupported``; no symbol → ``UNRESOLVED`` keyed on the
  holding id.

The per-policy mapping tables are declared inline below so every surface's
output stays byte-identical to its certified behavior while the derivation
logic lives in exactly one place.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .securities import InstrumentType, SecurityIdentity, SecurityState, security_id_for


class HoldingIdentityPolicy(StrEnum):
    CANONICAL = "canonical"
    MASTER_VERIFIED_ONLY = "master_verified_only"


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def identity_for_holding(holding: Any, *, policy: HoldingIdentityPolicy, as_of: datetime | None = None) -> SecurityIdentity:
    """Resolve one holding row to a canonical ``SecurityIdentity``.

    ``holding`` only needs ``symbol``, ``type``, and ``id`` attributes so
    tests may pass lightweight doubles. The ``as_of`` is the identity
    reference instant; when omitted the UNIX epoch is used so the identity
    is stable regardless of when it is derived.
    """
    resolved_at = as_of.astimezone(UTC) if (as_of is not None and as_of.tzinfo is not None) else as_of
    if resolved_at is None or resolved_at.tzinfo is None:
        resolved_at = _EPOCH
    symbol = (getattr(holding, "symbol", None) or "").strip().upper() or None
    raw_type = (getattr(holding, "type", None) or "").strip().lower()
    holding_id = getattr(holding, "id", None)

    if policy is HoldingIdentityPolicy.CANONICAL:
        return _canonical(symbol=symbol, raw_type=raw_type, as_of=resolved_at)
    return _master_verified_only(symbol=symbol, raw_type=raw_type, holding_id=holding_id, as_of=resolved_at)


def _canonical(*, symbol: str | None, raw_type: str, as_of: datetime) -> SecurityIdentity:
    """INV-03 / INV-12 D-2 frozen rule (identical to the former portfolio_intelligence behavior)."""
    mapping = {
        "stock": InstrumentType.EQUITY,
        "equity": InstrumentType.EQUITY,
        "etf": InstrumentType.ETF,
        "mutual fund": InstrumentType.MUTUAL_FUND,
        "crypto": InstrumentType.UNKNOWN,
    }
    instrument = mapping.get(raw_type, InstrumentType.UNKNOWN)
    state = (
        SecurityState.RESOLVED
        if symbol and instrument is not InstrumentType.UNKNOWN
        else SecurityState.UNSUPPORTED
        if symbol
        else SecurityState.UNRESOLVED
    )
    if symbol and instrument is not InstrumentType.UNKNOWN:
        security_id = security_id_for(namespace="atlas-security", value=f"{instrument.value}:{symbol}")
    else:
        security_id = security_id_for(namespace="atlas-unresolved", value=f"{instrument.value}:{symbol or 'unknown'}")
    return SecurityIdentity(
        security_id=security_id,
        state=state,
        instrument_type=instrument,
        symbol=symbol,
        exchange=None,
        currency=None,
        as_of=as_of,
    )


def _master_verified_only(*, symbol: str | None, raw_type: str, holding_id: Any, as_of: datetime) -> SecurityIdentity:
    """ADR-UI-11 certified risk rule (identical to the former risk_scenarios behavior)."""
    mapping = {
        "stock": InstrumentType.EQUITY,
        "equity": InstrumentType.EQUITY,
        "etf": InstrumentType.ETF,
        "mutual fund": InstrumentType.MUTUAL_FUND,
        "fund": InstrumentType.MUTUAL_FUND,
        "index": InstrumentType.INDEX,
    }
    instrument = mapping.get(raw_type, InstrumentType.UNKNOWN)
    if symbol and instrument is not InstrumentType.UNKNOWN:
        security_id = security_id_for(namespace="atlas-unresolved", value=f"{instrument.value}:{symbol}")
        state = SecurityState.UNRESOLVED
    elif symbol:
        security_id = security_id_for(namespace="atlas-unsupported", value=f"{raw_type}:{symbol}")
        instrument = InstrumentType.UNKNOWN
        state = SecurityState.UNSUPPORTED
    else:
        security_id = security_id_for(namespace="atlas-unresolved", value=f"holding:{holding_id}")
        instrument = InstrumentType.UNKNOWN
        state = SecurityState.UNRESOLVED
    return SecurityIdentity(
        security_id=security_id,
        state=state,
        instrument_type=instrument,
        symbol=symbol,
        exchange=None,
        currency=None,
        as_of=as_of,
    )


__all__ = ["HoldingIdentityPolicy", "identity_for_holding"]
