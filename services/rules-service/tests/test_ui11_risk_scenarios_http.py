from __future__ import annotations

from datetime import UTC, datetime

from app.models import Account, Holding, User
from app.routes.shared import get_or_create_family_member_self, get_or_create_institution


def _seed_position(db_session, *, symbol="AAPL", value=100.0, price=100.0, currency="USD"):
    user = db_session.query(User).filter(User.local_user_sub == "alex").first()
    if user is None:
        from app.routes.shared import get_or_create_local_user
        user = get_or_create_local_user(db_session, "alex")
    institution = get_or_create_institution(db_session, "UI11 Test Bank")
    member = get_or_create_family_member_self(db_session, user)
    account = Account(
        user_id=user.id,
        institution_id=institution.id,
        family_member_id=member.id,
        account_name="UI11 Brokerage",
        account_type="investment",
        currency_code=currency,
        is_active=True,
        current_balance=value,
        last_sync=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.add(account)
    db_session.flush()
    holding = Holding(
        account_id=account.id,
        symbol=symbol,
        description="UI11 position",
        quantity=1.0,
        last_price=price,
        current_value=value,
        cost_basis_total=80.0,
        type="Stock",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.add(holding)
    db_session.commit()
    return account.id, holding.id


def test_baseline_requires_authentication(client_no_auth):
    response = client_no_auth.get("/api/v1/investments/portfolio-risk/baseline")
    assert response.status_code == 401


def test_baseline_is_typed_current_only_and_does_not_leak_account_details(client, db_session):
    from app.config import settings
    settings.atlas_investment_read_enabled = True
    _account_id, holding_id = _seed_position(db_session)

    response = client.get("/api/v1/investments/portfolio-risk/baseline")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "InvestmentPortfolioBaseline/v1"
    assert body["capability"] == "current_only"
    assert body["total_value"] == "100"
    assert body["currency"] == "USD"
    assert body["positions"][0]["position_id"] == holding_id
    assert body["positions"][0]["exposure_percentage"] == "100"
    assert body["positions"][0]["exposure_state"] == "available"
    assert "owner_id" not in body
    assert "account_id" not in body["positions"][0]
    assert "account_name" not in body["positions"][0]


def test_baseline_excludes_another_owners_positions(client, db_session):
    from app.config import settings
    settings.atlas_investment_read_enabled = True
    _account_id, own_holding_id = _seed_position(db_session)
    other = User(
        local_user_sub="other-ui11-owner",
        email="other-ui11-owner@example.com",
        hashed_password="synthetic",
    )
    db_session.add(other)
    db_session.flush()
    institution = get_or_create_institution(db_session, "Other UI11 Bank")
    member = get_or_create_family_member_self(db_session, other)
    account = Account(
        user_id=other.id,
        institution_id=institution.id,
        family_member_id=member.id,
        account_name="Other Owner Brokerage",
        account_type="investment",
        currency_code="USD",
        is_active=True,
        current_balance=999.0,
    )
    db_session.add(account)
    db_session.flush()
    private_holding = Holding(
        account_id=account.id,
        symbol="PRIVATE",
        description="Other owner private position",
        quantity=1.0,
        last_price=999.0,
        current_value=999.0,
        cost_basis_total=900.0,
        type="Stock",
    )
    db_session.add(private_holding)
    db_session.commit()

    response = client.get("/api/v1/investments/portfolio-risk/baseline")
    assert response.status_code == 200
    body = response.json()
    assert [position["position_id"] for position in body["positions"]] == [own_holding_id]
    assert "PRIVATE" not in response.text
    assert "Other Owner Brokerage" not in response.text


def test_preview_accepts_only_bounded_intent_and_is_deterministic(client, db_session):
    from app.config import settings
    settings.atlas_investment_read_enabled = True
    _account_id, holding_id = _seed_position(db_session)
    baseline = client.get("/api/v1/investments/portfolio-risk/baseline").json()

    payload = {
        "baseline_id": baseline["baseline_id"],
        "position_id": holding_id,
        "market_value_delta": "25",
    }
    first = client.post("/api/v1/investments/portfolio-risk/scenarios/preview", json=payload)
    second = client.post("/api/v1/investments/portfolio-risk/scenarios/preview", json=payload)
    assert first.status_code == second.status_code == 200
    first_body, second_body = first.json(), second.json()
    assert first_body["scenario_id"] == second_body["scenario_id"]
    assert first_body["result_hash"] == second_body["result_hash"]
    assert first_body["metrics"] == second_body["metrics"]
    assert first_body["evaluated_at"] != second_body["evaluated_at"]
    assert first_body["hypothetical"] is True
    assert first.json()["predictive"] is False
    assert any(item["name"] == "hypothetical_total_value" and item["value"] == "125" for item in first.json()["metrics"])


def test_preview_rejects_client_financial_authority_and_malformed_commands(client, db_session):
    from app.config import settings
    settings.atlas_investment_read_enabled = True
    _account_id, holding_id = _seed_position(db_session)
    baseline = client.get("/api/v1/investments/portfolio-risk/baseline").json()
    base = {"baseline_id": baseline["baseline_id"], "position_id": holding_id, "market_value_delta": "1"}

    injected = client.post(
        "/api/v1/investments/portfolio-risk/scenarios/preview",
        json={**base, "owner_id": 999, "market_value": "100000", "result_hash": "a" * 64},
    )
    assert injected.status_code == 422
    malformed = client.post(
        "/api/v1/investments/portfolio-risk/scenarios/preview",
        json={**base, "market_value_delta": "-101"},
    )
    assert malformed.status_code == 422


def test_stale_baseline_and_missing_position_are_non_enumerating_conflicts(client, db_session):
    from app.config import settings
    settings.atlas_investment_read_enabled = True
    _account_id, holding_id = _seed_position(db_session)
    stale = client.post(
        "/api/v1/investments/portfolio-risk/scenarios/preview",
        json={"baseline_id": "portfolio-baseline:" + "a" * 32, "position_id": holding_id, "market_value_delta": "1"},
    )
    assert stale.status_code == 409
    missing = client.post(
        "/api/v1/investments/portfolio-risk/scenarios/preview",
        json={"position_id": 999999, "market_value_delta": "1"},
    )
    assert missing.status_code == 404
    assert "not found" in missing.json()["detail"].lower()


def test_future_portfolio_source_timestamp_fails_closed(client, db_session):
    from app.config import settings
    settings.atlas_investment_read_enabled = True
    account_id, _holding_id = _seed_position(db_session)
    account = db_session.get(Account, account_id)
    account.updated_at = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    db_session.commit()

    response = client.get("/api/v1/investments/portfolio-risk/baseline")
    assert response.status_code == 404
    assert "future portfolio source timestamp" not in response.text


def test_preview_does_not_mutate_holding_or_account(client, db_session):
    from app.config import settings
    settings.atlas_investment_read_enabled = True
    account_id, holding_id = _seed_position(db_session)
    baseline = client.get("/api/v1/investments/portfolio-risk/baseline").json()
    response = client.post(
        "/api/v1/investments/portfolio-risk/scenarios/preview",
        json={"baseline_id": baseline["baseline_id"], "position_id": holding_id, "market_value_delta": "25"},
    )
    assert response.status_code == 200
    db_session.expire_all()
    account = db_session.get(Account, account_id)
    holding = db_session.get(Holding, holding_id)
    assert account.current_balance == 100.0
    assert holding.current_value == 100.0
