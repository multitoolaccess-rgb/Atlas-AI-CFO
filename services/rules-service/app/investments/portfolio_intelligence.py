"""INV-03 deterministic portfolio intelligence projection.

This module consumes the existing Account/Holding models. It does not create a
second ledger, mutate financial state, or expose execution capabilities.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable

from .contracts import DataState, InvestmentStrictModel
from .securities import InstrumentType, SecurityIdentity, SecurityState, security_id_for


class Completeness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CostBasisState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    ESTIMATED = "estimated"
    PARTIAL = "partial"


def _money(value: object | None) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return format(number.normalize(), "f")


class PortfolioPosition(InvestmentStrictModel):
    security: SecurityIdentity
    account_id: int
    quantity: str | None
    market_value: str | None
    currency: str | None
    cost_basis: str | None
    cost_basis_state: CostBasisState
    market_value_state: DataState
    source_holding_id: int
    as_of: datetime


class ExposureBucket(InvestmentStrictModel):
    key: str
    value: str
    percentage: str | None
    state: DataState
    source_position_ids: tuple[int, ...]


class PortfolioSnapshot(InvestmentStrictModel):
    schema_version: str = "PortfolioSnapshot/v1"
    owner_id: int
    account_ids: tuple[int, ...]
    as_of: datetime
    positions: tuple[PortfolioPosition, ...]
    exposures: tuple[ExposureBucket, ...]
    total_market_value: str | None
    available_cash: str | None
    completeness: Completeness
    source_ids: tuple[int, ...]
    calculation_version: str = "portfolio-intelligence/v1"
    snapshot_hash: str

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude={"snapshot_hash"}), sort_keys=True, separators=(",", ":"))


def _identity(holding) -> SecurityIdentity:
    symbol = (holding.symbol or "").strip().upper() or None
    raw_type = (holding.type or "").strip().lower()
    mapping = {"stock": InstrumentType.EQUITY, "equity": InstrumentType.EQUITY, "etf": InstrumentType.ETF, "mutual fund": InstrumentType.MUTUAL_FUND, "crypto": InstrumentType.UNKNOWN}
    instrument = mapping.get(raw_type, InstrumentType.UNKNOWN)
    state = SecurityState.RESOLVED if symbol and instrument is not InstrumentType.UNKNOWN else SecurityState.UNSUPPORTED if symbol else SecurityState.UNRESOLVED
    return SecurityIdentity(
        security_id=security_id_for(namespace="atlas-holding", value=f"{holding.id}:{symbol or 'unknown'}"),
        state=state,
        instrument_type=instrument,
        symbol=symbol,
        exchange=None,
        currency="USD" if symbol else None,
        as_of=datetime(1970, 1, 1, tzinfo=UTC),
    )


def build_portfolio_snapshot(*, owner_id: int, accounts: Iterable, holdings: Iterable, as_of: datetime) -> PortfolioSnapshot:
    """Build a reproducible owner-scoped projection from canonical holdings."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware UTC")
    account_map = {account.id: account for account in accounts if account.user_id == owner_id}
    allowed = [holding for holding in holdings if holding.account_id in account_map]
    positions: list[PortfolioPosition] = []
    values: list[Decimal] = []
    source_ids: list[int] = []
    incomplete = False
    for holding in sorted(allowed, key=lambda row: (row.account_id, row.id)):
        value = _money(holding.current_value)
        cost = _money(holding.cost_basis_total)
        quantity = _money(holding.quantity)
        value_state = DataState.OBSERVED if value is not None else DataState.UNKNOWN
        cost_state = CostBasisState.KNOWN if cost is not None else CostBasisState.UNKNOWN
        if value is None or not holding.symbol or quantity is None:
            incomplete = True
        else:
            values.append(Decimal(value))
        source_ids.append(holding.id)
        positions.append(PortfolioPosition(
            security=_identity(holding), account_id=holding.account_id,
            quantity=quantity, market_value=value, currency=None,
            cost_basis=cost, cost_basis_state=cost_state, market_value_state=value_state,
            source_holding_id=holding.id, as_of=as_of.astimezone(UTC),
        ))
    total = format(sum(values, Decimal(0)).normalize(), "f") if not incomplete else None
    buckets: list[ExposureBucket] = []
    for position in positions:
        if position.market_value is None or total is None or Decimal(total) == 0:
            percentage = None
            state = DataState.UNKNOWN
        else:
            percentage = format((Decimal(position.market_value) / Decimal(total) * 100).normalize(), "f")
            state = DataState.OBSERVED
        buckets.append(ExposureBucket(key=position.security.symbol or "unknown", value=position.market_value or "0", percentage=percentage, state=state, source_position_ids=(position.source_holding_id,)))
    snapshot = PortfolioSnapshot(
        owner_id=owner_id, account_ids=tuple(sorted(account_map)), as_of=as_of.astimezone(UTC),
        positions=tuple(positions), exposures=tuple(buckets), total_market_value=total,
        available_cash=None, completeness=Completeness.PARTIAL if incomplete else Completeness.COMPLETE,
        source_ids=tuple(source_ids), snapshot_hash="0" * 64,
    )
    digest = hashlib.sha256(snapshot.canonical_payload().encode()).hexdigest()
    return snapshot.model_copy(update={"snapshot_hash": digest})
