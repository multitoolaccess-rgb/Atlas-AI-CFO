from __future__ import annotations

from fastapi.testclient import TestClient
from app.auth import issue_token
from app.config import settings
from app.database import SessionLocal
from app.models import Account, Holding, Institution, User
from app.routes.shared import get_or_create_family_member_self


def _client(username: str = "alex") -> TestClient:
    from app.main import app
    settings.atlas_investment_persistence_enabled = True
    settings.atlas_investment_read_enabled = True
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {issue_token(username=username)}"
    return client


def test_discovery_requires_authentication(client_no_auth):
    response = client_no_auth.get("/api/v1/investments/discovery", params={"universe": "sp500"})
    assert response.status_code == 401


def test_sp500_mode_is_typed_bounded_and_deterministic(client):
    settings.atlas_investment_read_enabled = True
    first = client.get("/api/v1/investments/discovery", params={"universe": "sp500", "limit": 3})
    second = client.get("/api/v1/investments/discovery", params={"universe": "sp500", "limit": 3})
    assert first.status_code == second.status_code == 200
    left, right = first.json(), second.json()
    assert left == right
    assert left["universe"] == "sp500"
    assert len(left["candidates"]) == 3
    assert left["candidates"][0]["security"]["symbol"] == "A"
    assert all("recommendation" not in candidate for candidate in left["candidates"])


def test_portfolio_mode_is_owner_scoped(client, db_session):
    settings.atlas_investment_read_enabled = True
    user = db_session.query(User).filter(User.local_user_sub == "alex").first()
    if user is None:
        from app.routes.shared import get_or_create_local_user
        user = get_or_create_local_user(db_session, "alex")
    institution = db_session.query(Institution).first()
    if institution is None:
        institution = Institution(name="UI09 Test Institution")
        db_session.add(institution)
        db_session.flush()
    member = get_or_create_family_member_self(db_session, user)
    account = Account(user_id=user.id, institution_id=institution.id, family_member_id=member.id, account_name="UI09", account_type="investment", is_active=True)
    db_session.add(account)
    db_session.flush()
    db_session.add(Holding(account_id=account.id, symbol="ZZZ", current_value=1.0))
    db_session.commit()
    response = client.get("/api/v1/investments/discovery", params={"universe": "portfolio"})
    assert response.status_code == 200
    assert [item["security"]["symbol"] for item in response.json()["candidates"]] == ["ZZZ"]


def test_portfolio_mode_handles_provider_annotated_symbols(client, db_session):
    """Provider sweep-fund annotations (e.g. ``CORE**``) must not break the
    canonical discovery security ID pattern; the display alias is preserved."""
    settings.atlas_investment_read_enabled = True
    user = db_session.query(User).filter(User.local_user_sub == "alex").first()
    if user is None:
        from app.routes.shared import get_or_create_local_user
        user = get_or_create_local_user(db_session, "alex")
    institution = db_session.query(Institution).first()
    if institution is None:
        institution = Institution(name="UI09 Annotated Institution")
        db_session.add(institution)
        db_session.flush()
    member = get_or_create_family_member_self(db_session, user)
    account = Account(user_id=user.id, institution_id=institution.id, family_member_id=member.id, account_name="UI09A", account_type="investment", is_active=True)
    db_session.add(account)
    db_session.flush()
    db_session.add(Holding(account_id=account.id, symbol="CORE**", current_value=1.0))
    db_session.commit()
    response = client.get("/api/v1/investments/discovery", params={"universe": "portfolio"})
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    # The provider annotation is a display artifact, not part of the ticker;
    # the canonical discovery identity must carry a clean alias and ID.
    assert [item["security"]["symbol"] for item in candidates] == ["CORE"]
    assert all(item["security"]["security_id"].startswith("sec:ui09:portfolio:") for item in candidates)
    assert all("*" not in item["security"]["security_id"] for item in candidates)


def test_detail_and_invalid_comparison_are_bounded(client):
    settings.atlas_investment_read_enabled = True
    listing = client.get("/api/v1/investments/discovery", params={"universe": "sp500", "limit": 2}).json()
    ids = [item["candidate_id"] for item in listing["candidates"]]
    detail = client.get(f"/api/v1/investments/discovery/{ids[0]}", params={"universe": "sp500"})
    assert detail.status_code == 200
    assert detail.json()["candidate_id"] == ids[0]
    invalid = client.post("/api/v1/investments/discovery/compare", params={"universe": "sp500"}, json={"candidate_ids": [ids[0]], "metric_names": ["price"]})
    assert invalid.status_code == 422


def test_discovery_candidate_is_not_a_recommendation(client):
    settings.atlas_investment_read_enabled = True
    response = client.get("/api/v1/investments/discovery", params={"universe": "sp500", "query": "AAPL", "limit": 5})
    assert response.status_code == 200
    for candidate in response.json()["candidates"]:
        assert candidate["recommendation_id"] is None
        assert candidate["metrics"] == {}
        assert candidate["metric_states"] == {}
