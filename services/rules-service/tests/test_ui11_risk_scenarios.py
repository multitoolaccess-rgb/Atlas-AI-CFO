from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.investments.risk_scenarios import (
    BaselineCapability,
    BaselineCompleteness,
    InvestmentRiskService,
    RiskDataState,
    RiskScenarioRequest,
)
from app.models import Account, Holding
from app.investments.securities import SecurityIdentity, SecurityState, InstrumentType


class _Session:
    """Small query double for service-level deterministic fixture tests."""

    def __init__(self, accounts, holdings):
        self.accounts = accounts
        self.holdings = holdings

    def scalars(self, statement):
        class Result:
            def __init__(self, values):
                self.values = values

            def all(self):
                return list(self.values)

            def __iter__(self):
                return iter(self.values)

        text = str(statement)
        if "FROM accounts" in text:
            owner_id = statement.compile().params.get("user_id")
            accounts = self.accounts if owner_id is None else [account for account in self.accounts if account.user_id == owner_id]
            return Result(accounts)
        return Result([h for h in self.holdings if h.account_id in {a.id for a in self.accounts}])


def _account(account_id=1, owner_id=7, currency="USD"):
    return SimpleNamespace(
        id=account_id,
        user_id=owner_id,
        is_active=True,
        currency_code=currency,
        last_sync=datetime(2026, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def _holding(holding_id=11, account_id=1, symbol="AAPL", value=100, quantity=1, price=100, kind="Stock"):
    return SimpleNamespace(
        id=holding_id,
        account_id=account_id,
        symbol=symbol,
        description="Test position",
        current_value=value,
        quantity=quantity,
        last_price=price,
        cost_basis_total=80,
        type=kind,
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_baseline_is_owner_scoped_current_only_and_hash_bound():
    service = InvestmentRiskService(_Session([_account()], [_holding(), _holding(12, 99, "SECRET", 9999)]))
    baseline = service.get_portfolio_baseline(owner_id=7)

    assert baseline.capability is BaselineCapability.CURRENT_ONLY
    assert baseline.completeness is BaselineCompleteness.COMPLETE
    assert baseline.total_value == "100"
    assert [position.security.symbol for position in baseline.positions] == ["AAPL"]
    assert baseline.positions[0].security.state is SecurityState.UNRESOLVED
    assert baseline.baseline_id.startswith("portfolio-baseline:")
    assert len(baseline.baseline_hash) == 64
    assert baseline.baseline_hash == service.get_portfolio_baseline(owner_id=7).baseline_hash
    assert all(position.as_of <= baseline.as_of for position in baseline.positions)


def test_unknown_currency_and_identity_remain_explicit_not_zero():
    service = InvestmentRiskService(
        _Session([_account(currency=None)], [_holding(symbol=None, value=50, price=None)])
    )
    baseline = service.get_portfolio_baseline(owner_id=7)

    assert baseline.total_value is None
    assert baseline.completeness is BaselineCompleteness.PARTIAL
    assert baseline.positions[0].market_value_state is RiskDataState.UNKNOWN
    assert baseline.positions[0].security.state is SecurityState.UNRESOLVED
    assert "currency_unavailable" in " ".join(baseline.omissions)
    assert any(metric.name == "portfolio_volatility" and metric.state is RiskDataState.UNAVAILABLE for metric in baseline.metrics)


def test_unsupported_instrument_is_preserved():
    service = InvestmentRiskService(_Session([_account()], [_holding(kind="Warrant")]))
    baseline = service.get_portfolio_baseline(owner_id=7)
    assert baseline.positions[0].security.state is SecurityState.UNSUPPORTED
    assert baseline.positions[0].security.instrument_type is InstrumentType.UNKNOWN


def test_mixed_currency_is_not_aggregated():
    service = InvestmentRiskService(_Session([_account(1, 7, "USD"), _account(2, 7, "EUR")], [_holding(), _holding(12, 2, "SAP", 100, 1, 100)]))
    baseline = service.get_portfolio_baseline(owner_id=7)
    assert baseline.total_value is None
    assert baseline.currency is None
    assert "mixed_currency_portfolio_is_not_comparable" in baseline.omissions


def test_preview_is_deterministic_hypothetical_and_non_mutating():
    accounts = [_account()]
    holdings = [_holding()]
    service = InvestmentRiskService(_Session(accounts, holdings))
    request = RiskScenarioRequest(position_id=11, market_value_delta="25")
    first = service.preview_investment_risk_scenario(owner_id=7, request=request)
    second = service.preview_investment_risk_scenario(owner_id=7, request=request)

    assert first.hypothetical is True
    assert first.predictive is False
    assert first.result_hash == second.result_hash
    assert first.scenario_id == second.scenario_id
    assert any(metric.name == "hypothetical_total_value" and metric.value == "125" for metric in first.metrics)
    assert holdings[0].current_value == 100
    assert accounts[0].currency_code == "USD"


def test_future_portfolio_source_timestamp_fails_closed():
    future = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    account = _account()
    account.updated_at = future
    with pytest.raises(ValueError, match="future portfolio source timestamp"):
        InvestmentRiskService(_Session([account], [_holding()])).get_portfolio_baseline(owner_id=7)


def test_preview_rejects_stale_baseline_and_negative_result():
    service = InvestmentRiskService(_Session([_account()], [_holding()]))
    baseline = service.get_portfolio_baseline(owner_id=7)
    with pytest.raises(ValueError, match="baseline is stale"):
        service.preview_investment_risk_scenario(
            owner_id=7,
            request=RiskScenarioRequest(baseline_id="portfolio-baseline:" + "a" * 32, position_id=11, market_value_delta="1"),
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        service.preview_investment_risk_scenario(
            owner_id=7,
            request=RiskScenarioRequest(baseline_id=baseline.baseline_id, position_id=11, market_value_delta="-101"),
        )


def test_request_is_strict_and_bounded():
    with pytest.raises(ValidationError):
        RiskScenarioRequest(position_id=1, market_value_delta="1", owner_id=7)
    with pytest.raises(ValidationError):
        RiskScenarioRequest(position_id=1, market_value_delta="1e999999")


def test_security_contract_is_not_replaced_by_risk_contract():
    identity = SecurityIdentity(
        security_id="sec:test", state=SecurityState.RESOLVED,
        instrument_type=InstrumentType.EQUITY, symbol="AAPL",
        as_of=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert identity.security_id == "sec:test"
    assert "recommendation" not in InvestmentRiskService.__module__
