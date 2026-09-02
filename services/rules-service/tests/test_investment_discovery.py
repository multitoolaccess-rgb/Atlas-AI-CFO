from datetime import UTC, datetime, timedelta
import pytest
from app.investments.discovery import DiscoveryCandidate, DiscoveryQuery, DiscoveryStatus, DiscoveryUniverse, build_comparison, build_discovery_projection, candidate_from_symbol
from app.investments.contracts import DataState
from app.investments.contracts import SecurityIdentity

NOW = datetime(2026, 8, 31, tzinfo=UTC)

def candidate(symbol, *, as_of=NOW, state=DataState.OBSERVED, status=DiscoveryStatus.CANDIDATE):
    security = SecurityIdentity(security_id=f"sec:ui09:{symbol.lower()}", state="resolved", instrument_type="equity", symbol=symbol)
    return DiscoveryCandidate(security=security, status=status, reason="Matches the configured research universe", source="server:ui09-fixture", as_of=as_of, freshness=state, methodology_version="discovery/v1", metrics={"price": "100" if state == DataState.OBSERVED else None}, metric_states={"price": state})

def test_discovery_is_deterministic_and_stably_ordered():
    items = [candidate("ZZZ"), candidate("AAA")]
    one = build_discovery_projection(items, DiscoveryQuery(limit=10))
    two = build_discovery_projection(list(reversed(items)), DiscoveryQuery(limit=10))
    assert [item.security.symbol for item in one.candidates] == ["AAA", "ZZZ"]
    assert one.model_dump() == two.model_dump()
    assert one.candidates[0].stable_id().startswith("discovery:")

def test_discovery_pagination_and_filters_are_bounded():
    result = build_discovery_projection([candidate("AAA"), candidate("BBB"), candidate("CCC")], DiscoveryQuery(query="bb", limit=1))
    assert [item.security.symbol for item in result.candidates] == ["BBB"]
    assert result.omitted_count == 0
    with pytest.raises(Exception):
        DiscoveryQuery(limit=101)

def test_temporal_identity_and_metric_state_fail_closed():
    with pytest.raises(ValueError):
        DiscoveryCandidate(security=candidate("FUT").security, status=DiscoveryStatus.CANDIDATE, reason="x", source="x", as_of=datetime(2026, 8, 31), freshness=DataState.OBSERVED, methodology_version="v1", metrics={}, metric_states={})
    unavailable = candidate("MISS", state=DataState.MISSING)
    assert unavailable.metrics["price"] is None
    assert unavailable.metric_states["price"] == DataState.MISSING

def test_comparison_marks_incompatible_time_and_data_states_without_fabrication():
    result = build_comparison([candidate("AAA"), candidate("BBB", state=DataState.MISSING)], ["price"])
    assert result.comparable is False
    assert result.metrics[0].values[result.candidate_ids[1]] is None
    assert result.metrics[0].states[result.candidate_ids[1]] == DataState.MISSING
    assert result.limitations

def test_approved_universe_projection_is_separate_and_score_free():
    portfolio = candidate_from_symbol("AAPL", universe=DiscoveryUniverse.PORTFOLIO, as_of=NOW)
    sp500 = candidate_from_symbol("AAPL", universe=DiscoveryUniverse.SP500, as_of=NOW)
    assert portfolio.source != sp500.source
    assert portfolio.recommendation_id is None
    assert portfolio.metrics == {}
    assert portfolio.stable_id() != sp500.stable_id()


def test_comparison_requires_bounded_candidate_count():
    with pytest.raises(ValueError):
        build_comparison([candidate("AAA")], ["price"])
