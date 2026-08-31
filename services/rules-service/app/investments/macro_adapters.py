"""Offline macro provider boundary for INV-06."""
from __future__ import annotations

from typing import Any, Protocol

from .contracts import EvidenceReference
from .macro import MacroFailure, MacroObservation, normalize_macro_observation


class MacroDataProvider(Protocol):
    def observations(self, series_id: str) -> list[dict[str, Any]]: ...


class FixtureMacroProvider:
    def __init__(self, records: dict[str, list[dict[str, Any]]]) -> None:
        self._records = records

    def observations(self, series_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self._records.get(series_id, [])]


def normalize_provider_observations(provider: MacroDataProvider, *, series_id: str, source: EvidenceReference) -> tuple[MacroObservation, ...]:
    try:
        return tuple(normalize_macro_observation(item, source=source) for item in provider.observations(series_id))
    except MacroFailure:
        raise
    except (TypeError, ValueError) as exc:
        raise MacroFailure("macro provider response was invalid") from exc
