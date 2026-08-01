"""Pure-function tests for the deterministic recommendation derivation engine.

These tests do NOT touch the database.  They exercise the engine as
a pure functional unit so the contract (identity, content,
fail-closed invariants) is provable without SQLAlchemy.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.forecasts.recommendation_engine import (
    ALLOWED_KINDS,
    ALLOWED_OUTPUT_SCHEMA_VERSION,
    ALLOWED_RULE_VERSION,
    DerivationError,
    ForecastSignals,
    InvalidCurrencyEvidence,
    InvalidForecastSignals,
    InvalidSchemaVersion,
    UnknownRecommendationKind,
    derive_recommendation,
)


def _signals(**overrides) -> ForecastSignals:
    base = dict(
        forecast_version_id="00000000-0000-4000-8000-000000000001",
        forecast_input_state_hash="a" * 64,
        ending_balance=Decimal("8500.00"),
        target_gap=Decimal("1500.00"),
        data_as_of="2026-07-01T12:00:00Z",
        currency="USD",
        model_version="forecast-model/v1",
        calculation_version="forecast-calc/v1",
    )
    base.update(overrides)
    return ForecastSignals(**base)


# ---------------------------------------------------------------------------
# Determinism: same canonical inputs ⇒ identical content
# ---------------------------------------------------------------------------


def test_derive_recommendation_is_pure_and_deterministic():
    a = derive_recommendation(signals=_signals(), recommendation_kind="hold")
    b = derive_recommendation(signals=_signals(), recommendation_kind="hold")
    assert a == b


def test_derive_recommendation_is_byte_stable_json():
    a = derive_recommendation(signals=_signals(), recommendation_kind="increase_contribution")
    sorted_keys = sorted(a.keys())
    assert sorted_keys == sorted([
        "reason", "expected_impact_min_decimal", "expected_impact_max_decimal",
        "confidence_score", "assumptions_json", "risks_json", "freshness_json",
        "provenance_json", "metadata_json",
    ])
    # JSON blobs are canonical: parseable, sorted keys, ASCII-only decimals.
    assumptions = json.loads(a["assumptions_json"])
    assert assumptions["rule_id"] == ALLOWED_RULE_VERSION
    assert assumptions["model_version"] == "atlas-projection/v1"


# ---------------------------------------------------------------------------
# Currency fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("non_usd_currency", ["EUR", "eur", "USDX", "", None])
def test_non_usd_currency_is_fail_closed(non_usd_currency):
    if non_usd_currency is None:
        signals = _signals(currency=None)  # type: ignore[arg-type]
    else:
        signals = _signals(currency=non_usd_currency)
    with pytest.raises(InvalidCurrencyEvidence):
        derive_recommendation(signals=signals, recommendation_kind="hold")


# ---------------------------------------------------------------------------
# Schema-version guard
# ---------------------------------------------------------------------------


def test_unsupported_schema_version_rejected():
    with pytest.raises(InvalidSchemaVersion):
        derive_recommendation(
            signals=_signals(),
            recommendation_kind="hold",
            derivation_schema_version="atlas-recommendation/v9",
        )


def test_unsupported_rule_version_rejected():
    with pytest.raises(InvalidSchemaVersion):
        derive_recommendation(
            signals=_signals(),
            recommendation_kind="hold",
            rule_version="v9.9",
        )


# ---------------------------------------------------------------------------
# Bounded kind coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(ALLOWED_KINDS))
def test_supported_kind_produces_bounded_content(kind):
    payload = derive_recommendation(signals=_signals(), recommendation_kind=kind)
    assert isinstance(payload["reason"], str) and 1 <= len(payload["reason"]) <= 1024
    assert isinstance(payload["expected_impact_min_decimal"], Decimal)
    assert isinstance(payload["expected_impact_max_decimal"], Decimal)
    assert payload["expected_impact_min_decimal"] <= payload["expected_impact_max_decimal"]
    assert 0 <= float(payload["confidence_score"]) <= 1
    # JSON blobs are parseable and contain only ASCII decimal strings.
    for blob_key in ("assumptions_json", "risks_json", "freshness_json", "provenance_json", "metadata_json"):
        parsed = json.loads(payload[blob_key])
        assert isinstance(parsed, (dict, list))
    risks = json.loads(payload["risks_json"])
    assert isinstance(risks, list)
    for token in risks:
        assert isinstance(token, str) and token.islower()


@pytest.mark.parametrize("bad_kind", ["monte_carlo", "llm_advice", "", "Increase_Contribution"])
def test_unknown_kind_rejected(bad_kind):
    with pytest.raises(UnknownRecommendationKind):
        derive_recommendation(signals=_signals(), recommendation_kind=bad_kind)


# ---------------------------------------------------------------------------
# Rule-specific content invariants
# ---------------------------------------------------------------------------


def test_hold_rule_zero_impact_high_confidence():
    payload = derive_recommendation(signals=_signals(target_gap=Decimal("0")), recommendation_kind="hold")
    assert payload["expected_impact_min_decimal"] == Decimal("0")
    assert payload["expected_impact_max_decimal"] == Decimal("0")
    assert payload["confidence_score"] >= Decimal("0.90")
    assert json.loads(payload["risks_json"]) == []


def test_increase_contribution_uses_bounded_band():
    payload = derive_recommendation(
        signals=_signals(target_gap=Decimal("1000.00")),
        recommendation_kind="increase_contribution",
    )
    # 30% and 60% of 1000.00 = 300.00 and 600.00
    assert payload["expected_impact_min_decimal"] == Decimal("300.00")
    assert payload["expected_impact_max_decimal"] == Decimal("600.00")


def test_increase_contribution_negative_gap_clamped_to_zero():
    payload = derive_recommendation(
        signals=_signals(target_gap=Decimal("-500.00")),
        recommendation_kind="increase_contribution",
    )
    # Negative gap ⇒ rule keeps the impact range at zero (no action).
    assert payload["expected_impact_min_decimal"] == Decimal("0")
    assert payload["expected_impact_max_decimal"] == Decimal("0")


def test_extend_horizon_uses_bounded_band():
    payload = derive_recommendation(
        signals=_signals(target_gap=Decimal("1000.00")),
        recommendation_kind="extend_horizon",
    )
    # 10% and 25% of 1000.00 = 100.00 and 250.00
    assert payload["expected_impact_min_decimal"] == Decimal("100.00")
    assert payload["expected_impact_max_decimal"] == Decimal("250.00")


def test_rebalance_allocation_uses_bounded_band():
    payload = derive_recommendation(
        signals=_signals(target_gap=Decimal("2000.00")),
        recommendation_kind="rebalance_allocation",
    )
    # 5% and 20% of 2000.00 = 100.00 and 400.00
    assert payload["expected_impact_min_decimal"] == Decimal("100.00")
    assert payload["expected_impact_max_decimal"] == Decimal("400.00")


# ---------------------------------------------------------------------------
# Signal-injection helper
# ---------------------------------------------------------------------------


def test_signal_from_forecast_version_rejects_missing_money():
    class _FakeFV:
        id = "00000000-0000-4000-8000-000000000010"
        input_state_hash = "a" * 64
        ending_balance = None  # missing
        target_gap = Decimal("0")
        data_as_of = "2026-07-01T12:00:00Z"
        currency = "USD"
        model_version = "m"
        calculation_version = "c"

    with pytest.raises(InvalidForecastSignals):
        ForecastSignals.from_forecast_version(_FakeFV())


def test_signal_from_forecast_version_rejects_non_finite_money():
    class _FakeFV:
        id = "00000000-0000-4000-8000-000000000010"
        input_state_hash = "a" * 64
        ending_balance = Decimal("NaN")
        target_gap = Decimal("0")
        data_as_of = "2026-07-01T12:00:00Z"
        currency = "USD"
        model_version = "m"
        calculation_version = "c"

    with pytest.raises(InvalidForecastSignals):
        ForecastSignals.from_forecast_version(_FakeFV())


def test_derivation_does_not_require_clock():
    # The engine must NOT depend on ``datetime.now`` or any clock.
    payload = derive_recommendation(signals=_signals(), recommendation_kind="hold")
    assert "derived_at" not in payload
    assert "created_at" not in payload
    # Only canonical / bounded columns appear in the payload.
    assert set(payload) == {
        "reason", "expected_impact_min_decimal", "expected_impact_max_decimal",
        "confidence_score", "assumptions_json", "risks_json", "freshness_json",
        "provenance_json", "metadata_json",
    }
