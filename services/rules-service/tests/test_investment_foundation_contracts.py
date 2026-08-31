from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.investments.contracts import (
    DataState,
    EvidenceKind,
    EvidenceReference,
    InvestmentContext,
    InvestmentPosition,
    InvestmentValue,
    SecurityIdentity,
)


def _evidence() -> EvidenceReference:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    return EvidenceReference(
        evidence_id="calc:portfolio:1",
        kind=EvidenceKind.CALCULATION,
        source="portfolio_snapshot_v1",
        content_hash="a" * 64,
        as_of=now,
        retrieved_at=now,
    )


def _context(owner_id: int = 1) -> InvestmentContext:
    security = SecurityIdentity(
        security_id="security:abc",
        instrument_type="equity",
        symbol="ABC",
        currency="USD",
    )
    position = InvestmentPosition(
        security=security,
        market_value=InvestmentValue(amount="10.00", currency="USD", state=DataState.OBSERVED),
        evidence=(_evidence(),),
    )
    return InvestmentContext(
        owner_id=owner_id,
        account_ids=(2, 1),
        as_of=datetime(2026, 8, 30, 12, tzinfo=UTC),
        positions=(position,),
        evidence=(_evidence(),),
    )


def test_context_is_versioned_and_hash_is_deterministic():
    first = _context()
    second = _context()
    assert first.schema_version == "InvestmentContext/v1"
    assert first.account_ids == (1, 2)
    assert first.context_hash() == second.context_hash()


def test_owner_is_not_part_of_shared_hash_payload():
    assert _context(1).context_hash() == _context(2).context_hash()


def test_decimal_values_are_finite_and_canonical():
    value = InvestmentValue(amount="0010.00", currency="USD", state=DataState.OBSERVED)
    assert value.amount == "10"
    with pytest.raises(ValidationError):
        InvestmentValue(amount="NaN", currency="USD", state=DataState.UNKNOWN)
    with pytest.raises(ValidationError):
        InvestmentValue(amount="Infinity", currency="USD", state=DataState.UNKNOWN)


def test_data_states_remain_distinct():
    assert {state.value for state in DataState} == {
        "unknown", "missing", "stale", "estimated", "observed"
    }


def test_unresolved_security_cannot_claim_resolved_identity():
    with pytest.raises(ValidationError):
        SecurityIdentity(
            security_id="security:unknown",
            instrument_type="equity",
            state="resolved",
        )


def test_settings_keep_investment_features_off_by_default():
    settings = Settings(_env_file=None)
    assert settings.atlas_investment_read_enabled is False
    assert settings.atlas_investment_analysis_enabled is False
    assert settings.atlas_investment_external_provider_enabled is False
    assert settings.atlas_investment_scheduler_enabled is False


def test_evidence_rejects_non_utc_or_bad_hash():
    now = datetime(2026, 8, 30, 12)
    with pytest.raises(ValidationError):
        EvidenceReference(
            evidence_id="source:x",
            kind=EvidenceKind.SOURCE,
            source="sec",
            content_hash="bad",
            as_of=now,
            retrieved_at=now,
        )
