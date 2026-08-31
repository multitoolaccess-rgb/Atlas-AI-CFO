from datetime import UTC, datetime
from types import SimpleNamespace

from app.investments.contracts import DataState
from app.investments.portfolio_intelligence import Completeness, CostBasisState, build_portfolio_snapshot


AS_OF = datetime(2026, 8, 30, 12, tzinfo=UTC)


def account(id, user_id=1):
    return SimpleNamespace(id=id, user_id=user_id)


def holding(id, account_id, symbol="AAPL", value=100.0, quantity=1.0, cost=80.0, type="Stock", price=100.0):
    return SimpleNamespace(id=id, account_id=account_id, symbol=symbol, current_value=value, last_price=price, quantity=quantity, cost_basis_total=cost, type=type)


def test_snapshot_is_owner_scoped_and_reproducible():
    accounts = [account(2), account(1), account(3, user_id=9)]
    holdings = [holding(10, 2, "VTI", 200), holding(11, 1, "AAPL", 100), holding(99, 3, "SECRET", 9999)]
    first = build_portfolio_snapshot(owner_id=1, accounts=accounts, holdings=holdings, as_of=AS_OF)
    second = build_portfolio_snapshot(owner_id=1, accounts=accounts, holdings=holdings, as_of=AS_OF)
    assert first.account_ids == (1, 2)
    assert {p.security.symbol for p in first.positions} == {"AAPL", "VTI"}
    assert first.total_market_value == "300"
    assert first.snapshot_hash == second.snapshot_hash


def test_snapshot_preserves_unknown_cost_basis_and_missing_value():
    result = build_portfolio_snapshot(
        owner_id=1,
        accounts=[account(1)],
        holdings=[holding(1, 1, "AAPL", value=None, quantity=None, cost=None)],
        as_of=AS_OF,
    )
    assert result.completeness is Completeness.PARTIAL
    assert result.positions[0].cost_basis_state is CostBasisState.UNKNOWN
    assert result.positions[0].market_value is None
    assert result.positions[0].market_value_state.value == "unknown"
    assert result.total_market_value is None
    assert result.exposures[0].percentage is None


def test_unresolved_symbol_is_not_silently_zero_or_valid_security():
    result = build_portfolio_snapshot(owner_id=1, accounts=[account(1)], holdings=[holding(1, 1, symbol=None, value=50)], as_of=AS_OF)
    assert result.positions[0].security.state.value == "unresolved"
    assert result.positions[0].market_value == "50"
    assert result.positions[0].security.symbol is None


def test_unknown_instrument_is_not_promoted_to_equity():
    result = build_portfolio_snapshot(owner_id=1, accounts=[account(1)], holdings=[holding(1, 1, "XYZ", 50, type="Warrant")], as_of=AS_OF)
    assert result.positions[0].security.state.value == "unsupported"
    assert result.positions[0].security.instrument_type.value == "unknown"


def test_currency_is_not_assumed_by_portfolio_projection():
    result = build_portfolio_snapshot(owner_id=1, accounts=[account(1)], holdings=[holding(1, 1, "AAPL", 50)], as_of=AS_OF)
    assert result.positions[0].currency is None


def test_missing_price_does_not_produce_observed_market_value():
    result = build_portfolio_snapshot(owner_id=1, accounts=[account(1)], holdings=[holding(1, 1, "AAPL", 50, price=None)], as_of=AS_OF)
    assert result.positions[0].market_value_state is not DataState.OBSERVED
    assert result.completeness is Completeness.PARTIAL


def test_as_of_requires_timezone():
    try:
        build_portfolio_snapshot(owner_id=1, accounts=[account(1)], holdings=[], as_of=datetime(2026, 8, 30))
    except ValueError as exc:
        assert "timezone" in str(exc)
    else:
        raise AssertionError("naive as_of must be rejected")
