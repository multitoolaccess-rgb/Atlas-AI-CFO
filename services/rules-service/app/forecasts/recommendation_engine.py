"""Pure-function deterministic recommendation derivation engine.

Phase 2 Slice 1 commit-3 server-owned derivation rules.  No LLM, no
external market data, no raw transactions or statements, no clock
access, no database I/O.  Every rule consumes ONLY the certified,
persisted ``forecast_version`` signals plus the bounded rule literal
plus the canonical schema version.

Same canonical inputs always produce the same Recommendation PK
(see :func:`app.models.decision_journal_identities.recommendation_id_for`)
AND the same content.  The engine has no state of its own beyond the
function arguments, which makes the test suite a pure unit test (no
SQLAlchemy, no clock, no network).

Fail-closed on:

* non-USD currency evidence (caller cannot bypass ``InvalidCurrencyEvidence``)
* unknown ``recommendation_kind`` (rejects ``UnknownRecommendationKind``)
* unsupported ``derivation_schema_version`` or ``rule_version``
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Mapping


ALLOWED_OUTPUT_SCHEMA_VERSION: Final[str] = "atlas-recommendation/v1"
ALLOWED_RULE_VERSION: Final[str] = "v1.0"
ALLOWED_KINDS: Final[frozenset[str]] = frozenset({
    "increase_contribution",
    "hold",
    "extend_horizon",
    "rebalance_allocation",
})


class DerivationError(Exception):
    """Base class for derivation-rule errors. Sanitized exception types only."""


class UnknownRecommendationKind(DerivationError):
    """Raised when ``recommendation_kind`` is not in :data:`ALLOWED_KINDS`."""


class InvalidCurrencyEvidence(DerivationError):
    """Raised when the forecast_version currency is not ``"USD"``."""


class InvalidSchemaVersion(DerivationError):
    """Raised when the rule_version or schema_version is not the canonical literal."""


class InvalidForecastSignals(DerivationError):
    """Raised when the bounded forecast signals are missing a required Decimal etc."""


@dataclass(frozen=True)
class ForecastSignals:
    """Canonical projection face of a persisted ``ForecastVersion``.

    The engine consumes ONLY these bounded signals; no other source
    can leak.  ``currency`` must be ``"USD"``; any other value
    triggers fail-closed behaviour so a cross-currency forecast cannot
    silently produce a recommendation.
    """

    forecast_version_id: str
    forecast_input_state_hash: str
    ending_balance: Decimal
    target_gap: Decimal
    data_as_of: str  # RFC 3339 UTC ``Z`` form already validated by Phase 1
    currency: str
    model_version: str
    calculation_version: str

    @classmethod
    def from_forecast_version(cls, fv: Any) -> "ForecastSignals":
        # ``Any`` so the engine stays decoupled from the SQLAlchemy model;
        # the repository does the import and resolves the attribute names.
        ending_balance_raw = getattr(fv, "ending_balance", None)
        target_gap_raw = getattr(fv, "target_gap", None)
        data_as_of_raw = getattr(fv, "data_as_of", None)
        if any(value is None for value in (ending_balance_raw, target_gap_raw, data_as_of_raw)):
            raise InvalidForecastSignals(
                "forecast_version is missing ending_balance / target_gap / data_as_of"
            )
        try:
            ending_balance = Decimal(str(ending_balance_raw))
            target_gap = Decimal(str(target_gap_raw))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidForecastSignals("forecast money fields must be finite Decimal") from exc
        if not ending_balance.is_finite() or not target_gap.is_finite():
            raise InvalidForecastSignals("forecast money fields must be finite Decimal")
        if isinstance(data_as_of_raw, str):
            data_as_of = data_as_of_raw
        else:
            data_as_of = data_as_of_raw.isoformat().replace("+00:00", "Z")
        return cls(
            forecast_version_id=str(fv.id),
            forecast_input_state_hash=str(fv.input_state_hash),
            ending_balance=ending_balance,
            target_gap=target_gap,
            data_as_of=data_as_of,
            currency=str(fv.currency),
            model_version=str(fv.model_version),
            calculation_version=str(fv.calculation_version),
        )


# ----------------------------------------------------------------------
# Rule implementations (pure bounded deterministic functions).
# Each rule is committed to a fixed impact band so the audit trail
# records the exact rule the recommendation was derived from.  No
# rule consults an LLM, a clock, or anything outside its inputs.
# ----------------------------------------------------------------------


def _floor_cents(value: Decimal) -> Decimal:
    """Round a Decimal down to two-decimal USD cents without raising on NaN/Inf."""
    if not value.is_finite():
        raise InvalidForecastSignals("decimal impact must be finite")
    # Quantize without banker-rounding bias: phase 1 forecasts are
    # already USD-rounded; recommendation impact inherits the same.
    return value.quantize(Decimal("0.01"))


def _bounded_impact(
    target_gap: Decimal,
    *,
    band_low: Decimal,
    band_high: Decimal,
) -> tuple[Decimal, Decimal]:
    """Bound the impact range to a fixed percentage of the target gap."""
    if band_low <= Decimal("0") or band_high <= Decimal("0"):
        raise InvalidForecastSignals("impact band percentages must be positive")
    if band_low >= band_high:
        raise InvalidForecastSignals("impact band must be ordered low < high")
    positive_gap = max(target_gap, Decimal("0"))
    return (
        _floor_cents(positive_gap * band_low),
        _floor_cents(positive_gap * band_high),
    )


def _shared_assumptions(rule_version: str) -> dict[str, Any]:
    return {
        "horizon_months": 360,
        "rule_id": rule_version,
        "model_version": "atlas-projection/v1",
    }


def _shared_freshness(signals: ForecastSignals) -> dict[str, Any]:
    return {
        "observed_at": signals.data_as_of,
        "max_data_age_days": 30,
        "data_age_days": 0,
    }


def _shared_provenance(signals: ForecastSignals, rule_version: str) -> dict[str, Any]:
    return {
        "forecast_version_id": signals.forecast_version_id,
        "input_state_hash": signals.forecast_input_state_hash,
        "rule_id": rule_version,
        "model_version": signals.model_version,
        "calculation_version": signals.calculation_version,
    }


def _shared_metadata() -> str:
    return json.dumps({"engine": "deterministic_v1"}, sort_keys=True, separators=(",", ":"))


def _risks(tokens: tuple[str, ...]) -> str:
    return json.dumps(list(tokens), separators=(",", ":"))


def _hold_payload(signals: ForecastSignals, rule_version: str) -> Mapping[str, Any]:
    """``hold``: projected ending balance already satisfies the goal."""
    zero = Decimal("0")
    return {
        "reason": "Projected ending balance already satisfies the goal target; no action needed.",
        "expected_impact_min_decimal": zero,
        "expected_impact_max_decimal": zero,
        "confidence_score": Decimal("0.95"),
        "assumptions_json": json.dumps(_shared_assumptions(rule_version), sort_keys=True, separators=(",", ":")),
        "risks_json": _risks(()),
        "freshness_json": json.dumps(_shared_freshness(signals), sort_keys=True, separators=(",", ":")),
        "provenance_json": json.dumps(_shared_provenance(signals, rule_version), sort_keys=True, separators=(",", ":")),
        "metadata_json": _shared_metadata(),
    }


def _increase_contribution_payload(signals: ForecastSignals, rule_version: str) -> Mapping[str, Any]:
    """``increase_contribution``: positive target gap; close 30-60% by raising contribution."""
    impact_min, impact_max = _bounded_impact(
        signals.target_gap, band_low=Decimal("0.30"), band_high=Decimal("0.60")
    )
    return {
        "reason": (
            "Projected ending balance is below the goal target; increasing the monthly "
            "contribution within the bounded band closes a portion of the gap."
        ),
        "expected_impact_min_decimal": impact_min,
        "expected_impact_max_decimal": impact_max,
        "confidence_score": Decimal("0.65"),
        "assumptions_json": json.dumps(
            {**_shared_assumptions(rule_version), "increase_band": "0.30-0.60"},
            sort_keys=True, separators=(",", ":"),
        ),
        "risks_json": _risks(("liquidity_reduction", "stale_input")),
        "freshness_json": json.dumps(_shared_freshness(signals), sort_keys=True, separators=(",", ":")),
        "provenance_json": json.dumps(_shared_provenance(signals, rule_version), sort_keys=True, separators=(",", ":")),
        "metadata_json": _shared_metadata(),
    }


def _extend_horizon_payload(signals: ForecastSignals, rule_version: str) -> Mapping[str, Any]:
    """``extend_horizon``: gap is large; extending horizon reduces the per-month burden."""
    impact_min, impact_max = _bounded_impact(
        signals.target_gap, band_low=Decimal("0.10"), band_high=Decimal("0.25")
    )
    return {
        "reason": (
            "The projected horizon is short relative to the gap; extending the horizon "
            "within the bounded band reduces the required monthly contribution."
        ),
        "expected_impact_min_decimal": impact_min,
        "expected_impact_max_decimal": impact_max,
        "confidence_score": Decimal("0.55"),
        "assumptions_json": json.dumps(_shared_assumptions(rule_version), sort_keys=True, separators=(",", ":")),
        "risks_json": _risks(("reversibility_required", "stale_input")),
        "freshness_json": json.dumps(_shared_freshness(signals), sort_keys=True, separators=(",", ":")),
        "provenance_json": json.dumps(_shared_provenance(signals, rule_version), sort_keys=True, separators=(",", ":")),
        "metadata_json": _shared_metadata(),
    }


def _rebalance_allocation_payload(signals: ForecastSignals, rule_version: str) -> Mapping[str, Any]:
    """``rebalance_allocation``: structurally-bound deterministic placeholder.

    The actual rebalance rule will be defined in a future slice;
    commit-3 ships a bounded output so the recommendation_kind enum
    is fully wired through derivation. ``rebalance_band`` is fixed
    in the audit log so a future change lifts the rule_version and
    produces a new PK + new content.
    """
    impact_min, impact_max = _bounded_impact(
        signals.target_gap, band_low=Decimal("0.05"), band_high=Decimal("0.20")
    )
    return {
        "reason": (
            "Deterministic rebalance suggestion; reduce concentration risk within the "
            "bounded band while maintaining the goal target."
        ),
        "expected_impact_min_decimal": impact_min,
        "expected_impact_max_decimal": impact_max,
        "confidence_score": Decimal("0.50"),
        "assumptions_json": json.dumps(
            {**_shared_assumptions(rule_version), "rebalance_band": "0.05-0.20"},
            sort_keys=True, separators=(",", ":"),
        ),
        "risks_json": _risks(("concentration", "reversibility_required")),
        "freshness_json": json.dumps(_shared_freshness(signals), sort_keys=True, separators=(",", ":")),
        "provenance_json": json.dumps(_shared_provenance(signals, rule_version), sort_keys=True, separators=(",", ":")),
        "metadata_json": _shared_metadata(),
    }


def derive_recommendation(
    *,
    signals: ForecastSignals,
    recommendation_kind: str,
    rule_version: str = ALLOWED_RULE_VERSION,
    derivation_schema_version: str = ALLOWED_OUTPUT_SCHEMA_VERSION,
) -> Mapping[str, Any]:
    """Pure deterministic derivation. Returns ORM-ready column values.

    The keys of the returned mapping match the column names on
    :class:`app.models.Recommendation` so the repository can splat
    them directly.
    """
    if not isinstance(signals, ForecastSignals):
        raise InvalidForecastSignals("signals must be a ForecastSignals instance")
    if not isinstance(recommendation_kind, str) or recommendation_kind not in ALLOWED_KINDS:
        raise UnknownRecommendationKind("recommendation_kind is not in ALLOWED_KINDS")
    if rule_version != ALLOWED_RULE_VERSION:
        raise InvalidSchemaVersion("rule_version is not the canonical literal")
    if derivation_schema_version != ALLOWED_OUTPUT_SCHEMA_VERSION:
        raise InvalidSchemaVersion("derivation_schema_version is not the canonical literal")
    if signals.currency != "USD":
        raise InvalidCurrencyEvidence("forecast currency evidence is not USD")

    if recommendation_kind == "increase_contribution":
        return _increase_contribution_payload(signals, rule_version)
    if recommendation_kind == "hold":
        return _hold_payload(signals, rule_version)
    if recommendation_kind == "extend_horizon":
        return _extend_horizon_payload(signals, rule_version)
    if recommendation_kind == "rebalance_allocation":
        return _rebalance_allocation_payload(signals, rule_version)
    # unreachable after the membership check above
    raise UnknownRecommendationKind("recommendation_kind fell through the table")


__all__ = [
    "ALLOWED_OUTPUT_SCHEMA_VERSION",
    "ALLOWED_RULE_VERSION",
    "ALLOWED_KINDS",
    "DerivationError",
    "UnknownRecommendationKind",
    "InvalidCurrencyEvidence",
    "InvalidSchemaVersion",
    "InvalidForecastSignals",
    "ForecastSignals",
    "derive_recommendation",
]
