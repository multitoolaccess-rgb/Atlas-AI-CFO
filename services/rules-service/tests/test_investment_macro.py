from datetime import UTC, datetime

import pytest

from app.investments.contracts import DataState, EvidenceKind, EvidenceReference
from app.investments.macro import MacroFailure, MacroKind, MacroStatus, MacroRegime, derive_macro_metrics, normalize_macro_observation
from app.investments.macro_adapters import FixtureMacroProvider, normalize_provider_observations

T0 = datetime(2026, 1, 31, tzinfo=UTC)
RELEASED = datetime(2026, 2, 12, tzinfo=UTC)
RETRIEVED = datetime(2026, 2, 13, tzinfo=UTC)
SOURCE = EvidenceReference(evidence_id="fred:CPI:1", kind=EvidenceKind.SOURCE, source="fred", content_hash="b" * 64, as_of=RELEASED, retrieved_at=RETRIEVED)


def payload(indicator_id="inflation", value="3.1", *, geography="US", unit="percent", observation_id="cpi-2026-01", as_known_at=RELEASED, status="initial"):
    return {"indicator_id": indicator_id, "observation_id": observation_id, "geography": geography, "value": value, "unit": unit, "frequency": "monthly", "observation_period": T0, "release_date": RELEASED, "effective_date": T0, "as_known_at": as_known_at, "retrieved_at": RETRIEVED, "status": status, "state": "observed"}


def test_macro_observation_preserves_units_geography_release_and_vintage():
    observation = normalize_macro_observation(payload(), source=SOURCE)
    assert observation.value == "3.1"
    assert observation.unit == "percent"
    assert observation.geography == "US"
    assert observation.release_date == RELEASED
    assert observation.as_known_at == RELEASED
    assert len(observation.content_hash()) == 64


def test_future_release_cannot_be_used_in_earlier_knowledge_context():
    with pytest.raises(MacroFailure):
        normalize_macro_observation(payload(as_known_at=datetime(2026, 2, 1, tzinfo=UTC)), source=SOURCE)


def test_revision_is_a_new_observation_with_original_linkage():
    original = normalize_macro_observation(payload(), source=SOURCE)
    revised = normalize_macro_observation(payload(value="3.2", observation_id="cpi-2026-01-r1", as_known_at=RETRIEVED, status="revised"), source=SOURCE)
    revised = revised.model_copy(update={"revision_of": original.observation_id})
    assert revised.status is MacroStatus.REVISED
    assert revised.revision_of == original.observation_id
    assert original.value == "3.1"


def test_macro_provider_normalization_is_bounded():
    provider = FixtureMacroProvider({"CPI": [payload()]})
    values = normalize_provider_observations(provider, series_id="CPI", source=SOURCE)
    assert len(values) == 1
    assert values[0].indicator_id is MacroKind.INFLATION


def test_invalid_macro_numeric_or_unit_fails_closed():
    with pytest.raises(MacroFailure):
        normalize_macro_observation(payload(value="NaN"), source=SOURCE)
    with pytest.raises(MacroFailure):
        normalize_macro_observation(payload(unit="5"), source=SOURCE)


def test_yield_curve_spread_is_deterministic_and_source_bound():
    two = normalize_macro_observation(payload(indicator_id="treasury_yield", geography="US-2Y", value="4.5", unit="percent", observation_id="2y"), source=SOURCE)
    ten = normalize_macro_observation(payload(indicator_id="treasury_yield", geography="US-10Y", value="4.0", unit="percent", observation_id="10y"), source=SOURCE)
    metrics = derive_macro_metrics([ten, two], as_of=RETRIEVED)
    assert metrics[0].name == "yield_spread_10y_2y"
    assert metrics[0].value == "-0.5"
    assert metrics[0].source_observation_ids == (two.observation_id, ten.observation_id)


def test_later_observation_is_excluded_from_historical_context():
    later = normalize_macro_observation(payload(value="9", observation_id="later", as_known_at=datetime(2026, 2, 13, tzinfo=UTC),), source=SOURCE)
    assert derive_macro_metrics([later], as_of=datetime(2026, 2, 1, tzinfo=UTC)) == ()
