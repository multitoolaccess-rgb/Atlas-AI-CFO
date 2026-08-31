"""Offline fundamental provider adapter for INV-04.

This proves the provider -> DTO -> validation -> canonical fact boundary without
activating a live provider or coupling Atlas models to provider payloads.
"""
from __future__ import annotations

from typing import Any, Protocol

from .contracts import EvidenceReference
from .fundamentals import FundamentalFact, FundamentalFailure, normalize_fundamental_fact
from .securities import SecurityIdentity


class FundamentalDataProvider(Protocol):
    def facts(self, provider_security_id: str) -> list[dict[str, Any]]: ...


class FixtureFundamentalProvider:
    def __init__(self, records: dict[str, list[dict[str, Any]]]) -> None:
        self._records = records

    def facts(self, provider_security_id: str) -> list[dict[str, Any]]:
        return [dict(record) for record in self._records.get(provider_security_id, [])]


def normalize_provider_facts(
    provider: FundamentalDataProvider,
    *,
    provider_security_id: str,
    security: SecurityIdentity,
    source: EvidenceReference,
) -> tuple[FundamentalFact, ...]:
    """Normalize all fixture/provider records; invalid records fail closed."""
    try:
        payloads = provider.facts(provider_security_id)
        return tuple(normalize_fundamental_fact(payload, security=security, source=source) for payload in payloads)
    except FundamentalFailure:
        raise
    except (TypeError, ValueError) as exc:
        raise FundamentalFailure("fundamental provider response was invalid") from exc
