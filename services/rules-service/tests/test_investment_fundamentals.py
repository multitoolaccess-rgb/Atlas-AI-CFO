from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.investments.contracts import DataState, EvidenceKind, EvidenceReference
from app.investments.fundamental_adapters import FixtureFundamentalProvider, normalize_provider_facts
from app.investments.fundamentals import (
    FactKind,
    FactStatus,
    FundamentalFailure,
    FundamentalFact,
    PeriodBasis,
    derive_metrics,
)
from app.investments.securities import InstrumentType, SecurityIdentity, SecurityState


T0 = datetime(2025, 12, 31, tzinfo=UTC)
T1 = datetime(2026, 2, 15, tzinfo=UTC)
SECURITY = SecurityIdentity(
    security_id="sec:abc123", state=SecurityState.RESOLVED,
    instrument_type=InstrumentType.EQUITY, symbol="ABC", currency="USD", as_of=T0,
)
SOURCE = EvidenceReference(
    evidence_id="filing:abc:1", kind=EvidenceKind.SOURCE, source="sec",
    content_hash="a" * 64, as_of=T1, retrieved_at=T1,
)


def payload(fact_id, kind, value, *, currency="USD", period_end=T0, as_known_at=T1, status="reported"):
    return {
        "fact_id": fact_id, "kind": kind, "value": value, "unit": "USD",
        "currency": currency, "period_basis": "annual", "period_end": period_end,
        "as_known_at": as_known_at, "retrieved_at": T1, "status": status,
    }


def test_fact_preserves_reporting_and_knowledge_times_and_hashes():
    fact = FundamentalFact(
        fact_id="fact:revenue:1", security=SECURITY, kind=FactKind.REVENUE,
        value="100.00", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL,
        period_end=T0, filing_date=T1, as_known_at=T1, retrieved_at=T1,
        status=FactStatus.REPORTED, source=SOURCE,
    )
    assert fact.value == "100"
    assert fact.period_end == T0
    assert fact.as_known_at == T1
    assert len(fact.content_hash()) == 64


def test_future_filing_cannot_be_known_before_filing_date():
    with pytest.raises(ValueError):
        FundamentalFact(
            fact_id="fact:revenue:1", security=SECURITY, kind=FactKind.REVENUE,
            value="100", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL,
            period_end=T0, filing_date=T1, as_known_at=T0, retrieved_at=T1,
            status=FactStatus.REPORTED, source=SOURCE,
        )


def test_restatement_is_a_new_version_not_an_overwrite():
    original = FundamentalFact(
        fact_id="fact:revenue:1", security=SECURITY, kind=FactKind.REVENUE,
        value="100", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL,
        period_end=T0, as_known_at=T1, retrieved_at=T1, status=FactStatus.REPORTED, source=SOURCE,
    )
    revised = original.model_copy(update={"fact_id": "fact:revenue:2", "value": "101", "status": FactStatus.RESTATED, "revision_of": original.fact_id})
    assert revised.fact_id != original.fact_id
    assert revised.revision_of == original.fact_id
    assert original.value == "100"


def test_provider_normalization_is_bounded_and_provenance_preserved():
    provider = FixtureFundamentalProvider({"provider:abc": [payload("revenue", "revenue", "100.0")]})
    facts = normalize_provider_facts(provider, provider_security_id="provider:abc", security=SECURITY, source=SOURCE)
    assert len(facts) == 1
    assert facts[0].source.evidence_id == SOURCE.evidence_id
    assert facts[0].value == "100"


def test_invalid_numeric_payload_fails_closed():
    provider = FixtureFundamentalProvider({"provider:abc": [payload("revenue", "revenue", "NaN")]})
    with pytest.raises(FundamentalFailure):
        normalize_provider_facts(provider, provider_security_id="provider:abc", security=SECURITY, source=SOURCE)


def test_metrics_are_decimal_safe_and_source_bound():
    facts = [
        FundamentalFact(fact_id="revenue", security=SECURITY, kind=FactKind.REVENUE, value="100", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL, period_end=T0, as_known_at=T1, retrieved_at=T1, status=FactStatus.REPORTED, source=SOURCE),
        FundamentalFact(fact_id="gross", security=SECURITY, kind=FactKind.GROSS_PROFIT, value="37.5", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL, period_end=T0, as_known_at=T1, retrieved_at=T1, status=FactStatus.REPORTED, source=SOURCE),
    ]
    metrics = derive_metrics(facts, as_of=T1)
    assert metrics[0].name == "gross_margin"
    assert metrics[0].value == "0.375"
    assert metrics[0].state is DataState.OBSERVED
    assert metrics[0].source_fact_ids == ("gross", "revenue")


def test_ratio_with_zero_denominator_is_unknown_not_zero():
    facts = [
        FundamentalFact(fact_id="revenue", security=SECURITY, kind=FactKind.REVENUE, value="0", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL, period_end=T0, as_known_at=T1, retrieved_at=T1, status=FactStatus.REPORTED, source=SOURCE),
        FundamentalFact(fact_id="income", security=SECURITY, kind=FactKind.NET_INCOME, value="10", unit="USD", currency="USD", period_basis=PeriodBasis.ANNUAL, period_end=T0, as_known_at=T1, retrieved_at=T1, status=FactStatus.REPORTED, source=SOURCE),
    ]
    assert derive_metrics(facts, as_of=T1)[0].value is None
    assert derive_metrics(facts, as_of=T1)[0].state is DataState.UNKNOWN
