"""UI-09 bounded opportunity discovery read-model.

Discovery is deliberately separate from INV-09 recommendations. This module
only normalizes caller-provided, already-authorized canonical security and
research projections into an explainable, point-in-time queue; it does not
create recommendations or calculate financial intelligence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Iterable, Sequence

from pydantic import Field, model_validator

from .contracts import DataState, InvestmentStrictModel
from .contracts import SecurityIdentity


class DiscoveryStatus(StrEnum):
    CANDIDATE = "candidate"
    WATCH = "watch"
    UNAVAILABLE = "unavailable"


class DiscoveryCandidate(InvestmentStrictModel):
    schema_version: str = "InvestmentDiscoveryCandidate/v1"
    security: SecurityIdentity
    status: DiscoveryStatus
    reason: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=160)
    as_of: datetime
    freshness: DataState
    methodology_version: str = Field(min_length=1, max_length=80)
    metrics: dict[str, str | None] = Field(default_factory=dict)
    metric_states: dict[str, DataState] = Field(default_factory=dict)
    recommendation_id: str | None = None

    @model_validator(mode="after")
    def validate_temporal(self) -> "DiscoveryCandidate":
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("discovery as_of must be timezone-aware")
        if hasattr(self.security, "as_of") and self.security.as_of > self.as_of:
            raise ValueError("security identity cannot be newer than discovery context")
        if set(self.metrics) != set(self.metric_states):
            raise ValueError("every discovery metric requires an explicit data state")
        return self

    def stable_id(self) -> str:
        payload = self.model_dump(mode="json", exclude={"recommendation_id"})
        return "discovery:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]


class DiscoveryUniverse(StrEnum):
    PORTFOLIO = "portfolio"
    SP500 = "sp500"


class DiscoveryQuery(InvestmentStrictModel):
    universe: DiscoveryUniverse = DiscoveryUniverse.PORTFOLIO
    security_ids: tuple[str, ...] = ()
    status: DiscoveryStatus | None = None
    query: str | None = Field(default=None, max_length=80)
    limit: int = Field(default=50, ge=1, le=100)
    as_of: datetime | None = None


class DiscoveryProjection(InvestmentStrictModel):
    schema_version: str = "InvestmentDiscovery/v1"
    as_of: datetime
    methodology_version: str
    candidates: tuple[DiscoveryCandidate, ...]
    omitted_count: int = Field(ge=0)


class ComparisonMetric(InvestmentStrictModel):
    name: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=32)
    values: dict[str, str | None]
    states: dict[str, DataState]
    as_of: datetime
    methodology_version: str


class DiscoveryComparison(InvestmentStrictModel):
    schema_version: str = "InvestmentDiscoveryComparison/v1"
    candidate_ids: tuple[str, ...] = Field(min_length=2, max_length=10)
    metrics: tuple[ComparisonMetric, ...]
    comparable: bool
    limitations: tuple[str, ...] = ()


def build_comparison(candidates: Sequence[DiscoveryCandidate], metric_names: Sequence[str]) -> DiscoveryComparison:
    """Build descriptive comparison rows; incompatible states stay explicit."""
    if len(candidates) < 2 or len(candidates) > 10:
        raise ValueError("comparison requires between 2 and 10 candidates")
    metrics: list[ComparisonMetric] = []
    limitations: list[str] = []
    for name in metric_names:
        values = {candidate.stable_id(): candidate.metrics.get(name) for candidate in candidates}
        states = {candidate.stable_id(): candidate.metric_states.get(name, DataState.MISSING) for candidate in candidates}
        if any(state != DataState.OBSERVED for state in states.values()):
            limitations.append(f"{name} is not fully comparable because one or more values are unavailable")
        as_ofs = {candidate.as_of for candidate in candidates}
        if len(as_ofs) != 1:
            limitations.append(f"{name} uses incompatible as-of timestamps")
        metrics.append(ComparisonMetric(name=name, values=values, states=states, as_of=max(as_ofs), methodology_version="explicit-candidate/v1"))
    return DiscoveryComparison(candidate_ids=tuple(candidate.stable_id() for candidate in candidates), metrics=tuple(metrics), comparable=not limitations, limitations=tuple(dict.fromkeys(limitations)))


def candidate_from_symbol(symbol: str, *, universe: DiscoveryUniverse, as_of: datetime) -> DiscoveryCandidate:
    """Create a descriptive candidate from an approved universe member.

    This is identity/universe projection only: it intentionally carries no
    price, score, recommendation, or financial advice. The symbol remains a
    display/provider alias; the deterministic security ID is namespaced by
    the approved universe and therefore cannot be confused with INV-09 state.
    """
    normalized = symbol.strip().upper()
    security = SecurityIdentity(
        security_id=f"sec:ui09:{universe.value}:{normalized.lower()}",
        state="resolved",
        instrument_type="equity",
        symbol=normalized,
    )
    return DiscoveryCandidate(
        security=security,
        status=DiscoveryStatus.CANDIDATE,
        reason=f"Member of the approved {universe.value} discovery universe",
        source=f"server:ui09:{universe.value}-universe",
        as_of=as_of,
        freshness=DataState.UNKNOWN,
        methodology_version="ui09-universe-membership/v1",
        metrics={},
        metric_states={},
    )


def build_discovery_projection(candidates: Iterable[DiscoveryCandidate], query: DiscoveryQuery, *, now: Callable[[], datetime] | None = None) -> DiscoveryProjection:
    """Filter and order candidates deterministically without scoring them."""
    selected = list(candidates)
    if query.security_ids:
        allowed = set(query.security_ids)
        selected = [item for item in selected if item.security.security_id in allowed]
    if query.status:
        selected = [item for item in selected if item.status == query.status]
    if query.query:
        needle = query.query.casefold()
        selected = [item for item in selected if needle in (item.security.symbol or "").casefold() or needle in item.reason.casefold()]
    if query.as_of:
        if query.as_of.tzinfo is None or query.as_of.utcoffset() is None:
            raise ValueError("query as_of must be timezone-aware")
        selected = [item for item in selected if item.as_of <= query.as_of]
    selected.sort(key=lambda item: (item.security.symbol or "", item.security.security_id, item.stable_id()))
    omitted = max(0, len(selected) - query.limit)
    selected = selected[: query.limit]
    as_of = query.as_of or (max((item.as_of for item in selected), default=(now or (lambda: datetime.now(UTC)))()))
    methods = {item.methodology_version for item in selected}
    methodology = next(iter(methods)) if len(methods) == 1 else "mixed/explicit-per-candidate"
    return DiscoveryProjection(as_of=as_of, methodology_version=methodology, candidates=tuple(selected), omitted_count=omitted)
