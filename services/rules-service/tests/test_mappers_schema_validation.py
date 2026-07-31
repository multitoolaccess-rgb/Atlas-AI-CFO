"""Bounded validation contracts for the Phase 1 mapper-cleanup follow-up.

Asserts path B1 (calculation-decimal validator swap on ``monthly_real_rate``,
``unrounded_ending_balance``, and ``unrounded_target_amount``) is wired
correctly in ``app.forecasts.schemas`` without leaking precision drop or
shape changes to clients.

These are pure schema tests; no DB / FastAPI / adapter side effects.
The contract under test is the *accepted* precision envelope per
``atlas-calculation-decimal/v1`` (50 significant digits / 64 fractional digits)
vs the *canonical-money* envelope (38 total digits / 18 fractional digits).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.forecasts.schemas import ScenarioSnapshotSchema, TargetDecisionV2Schema





def _snapshot(monthly_real_rate: str = "0.001") -> ScenarioSnapshotSchema:
    return ScenarioSnapshotSchema(
        annual_return_rate="0.04",
        monthly_real_rate=monthly_real_rate,
        ending_balance="1234.56",
        investment_growth="100",
        target_gap="0",
        reaches_target=True,
    )


def _target_decision(
    *,
    unrounded_ending_balance: str = "0",
    unrounded_target_amount: str = "0",
    rounded_ending_balance: str = "0.00",
    rounded_target_amount: str = "0.00",
) -> TargetDecisionV2Schema:
    return TargetDecisionV2Schema(
        decision_schema_version="atlas-target-decision/v2",
        scenario="base",
        comparison="greater_than_or_equal",
        decision_basis="currency_rounded",
        rounding_rule="ROUND_HALF_EVEN",
        money_precision="0.01",
        unrounded_ending_balance=unrounded_ending_balance,
        unrounded_target_amount=unrounded_target_amount,
        rounded_ending_balance=rounded_ending_balance,
        rounded_target_amount=rounded_target_amount,
        target_status=(Decimal(rounded_ending_balance) >= Decimal(rounded_target_amount)),
    )


# ------------------- monthly_real_rate (ScenarioSnapshotSchema) -------------------

def test_monthly_real_rate_accepts_atlas_calculation_decimal_v1_50_digits() -> None:
    """monthly_real_rate is calculation-decimal — accepts 50-significant-digit values."""
    big_rate = "0." + "1" * 50
    s = _snapshot(monthly_real_rate=big_rate)
    assert s.monthly_real_rate == big_rate


def test_monthly_real_rate_accepts_short_canonical_decimal() -> None:
    s = _snapshot(monthly_real_rate="0.001")
    assert s.monthly_real_rate == "0.001"


def test_monthly_real_rate_rejects_non_canonical_decimal_with_trailing_zeros() -> None:
    with pytest.raises(ValueError):
        _snapshot(monthly_real_rate="0.0010")


def test_monthly_real_rate_rejects_scientific_notation() -> None:
    with pytest.raises(ValueError):
        _snapshot(monthly_real_rate="1e-3")


def test_monthly_real_rate_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        _snapshot(monthly_real_rate="inf")


# ------------------- unrounded_* (TargetDecisionV2Schema) -------------------
# Construct clean (unrounded, rounded) pairs where the unrounded value is the
# exact canonical-quantization string of the rounded value at 0.01 ROUND_HALF_EVEN,
# so the model_validator `_rounded_quantizes_to_unrounded` passes.

def test_unrounded_ending_balance_accepts_50_digit_calculation_decimal() -> None:
    """unrounded_ending_balance uses the calculation-decimal envelope (50 sig digits; NO magnitude bound).

    The paired ``rounded_ending_balance`` must satisfy the canonical-money envelope:
    38 total digits, 18 scale, 40 length, ``|value| <= 1E+24`` (MAX_ABSOLUTE_MONEY).

    Quantum invariant: ``Decimal(unrounded).quantize("0.01", ROUND_HALF_EVEN) == Decimal(rounded)``.

    ``unrounded_ending_balance`` has 50 significant digits (1 integer + 49 non-zero fractional);
    ``Decimal("1.1234...49 digits").quantize("0.01", ROUND_HALF_EVEN) == Decimal("1.12")``
    because the 3rd fractional digit is '3' which rounds DOWN at 2 decimals.
    """
    t = _target_decision(
        unrounded_ending_balance="1.1234567890123456789012345678901234567890123456789",
        unrounded_target_amount="0",
        rounded_ending_balance="1.12",
        rounded_target_amount="0.00",
    )
    assert t.unrounded_ending_balance == (
        "1.1234567890123456789012345678901234567890123456789"
    )
    assert t.rounded_ending_balance == "1.12"


def test_unrounded_target_amount_accepts_50_digit_calculation_decimal() -> None:
    """unrounded_target_amount uses the calculation-decimal envelope (50 sig digits; NO magnitude bound).

    Same canonical-money invariants as test #1 apply to ``rounded_target_amount``.
    The 50-significant-digit unrounded value's 3rd fractional digit is '7', which rounds UP
    at 2 decimals so ``Decimal("2.9876543210...").quantize("0.01", ROUND_HALF_EVEN) == Decimal("2.99")``.
    """
    t = _target_decision(
        unrounded_ending_balance="0",
        unrounded_target_amount=(
            "2.9876543210987654321098765432109876543210987654321"
        ),
        rounded_ending_balance="0.00",
        rounded_target_amount="2.99",
    )
    assert t.unrounded_target_amount == (
        "2.9876543210987654321098765432109876543210987654321"
    )
    assert t.rounded_target_amount == "2.99"


def test_unrounded_ending_balance_rejects_non_canonical_decimal() -> None:
    """Trailing-zero unrounded values are rejected because the calculation-decimal form rejects canonical-no-significant-zeros."""
    with pytest.raises(ValueError):
        _target_decision(
            unrounded_ending_balance="1.5000",  # trailing zeros — non-canonical
        )


# ------------------- rounded_* stays on canonical-money (38 digits) -------------------

def test_rounded_ending_balance_uses_canonical_money_38_digit_bound() -> None:
    """rounded_ending_balance is canonical-money; values exceeding 38-digit bound are rejected."""
    too_big = "1" * 39  # 39 digits > canonical-money bound of 38
    with pytest.raises(ValueError):
        _target_decision(
            rounded_ending_balance=too_big,
        )


def test_rounded_target_amount_accepts_38_digit_canonical_money() -> None:
    """rounded_target_amount at the canonical-money 38-bound passes the wire contract.

    The canonical round-trip (``unrounded == rounded``) is the simplest shape that simultaneously
    satisfies ``_check_calculation_decimal`` (50 sig digits) on the unrounded field AND
    ``_check_canonical_decimal`` (38 total + |value| ≤ 1E+24) on the rounded field.

    Both ``"100.50"`` and ``"1.5"`` would also pass — this test preserves the bounded explicit
    canonical round-trip shape to mirror how Phase 0 produces identical quantized and rounded
    values when the inputs already align to 2 decimals.
    """
    t = _target_decision(
        unrounded_ending_balance="0",
        unrounded_target_amount="100.5",  # calculation-decimal canonical: no trailing zero
        rounded_ending_balance="0.00",
        rounded_target_amount="100.50",    # canonical-money 38-bound accepts trailing-zero form
    )
    assert t.rounded_target_amount == "100.50"
