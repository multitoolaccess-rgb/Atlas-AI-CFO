import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import issue_token
from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.routes.shared import get_or_create_local_user


@pytest.fixture(autouse=True)
def _enable_persistence():
    settings.atlas_investment_persistence_enabled = True


def _client(token: str | None = None) -> TestClient:
    from app.main import app
    settings.atlas_investment_persistence_enabled = True
    client = TestClient(app)
    if token:
        client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_investment_routes_require_authentication(client_no_auth):
    response = client_no_auth.get('/api/v1/investments/recommendations')
    assert response.status_code == 401


def test_investment_routes_are_owner_scoped_and_do_not_enumerate(client, db_session):
    get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    response = client.get('/api/v1/investments/recommendations/investment-recommendation:does-not-exist')
    assert response.status_code == 404
    assert response.headers.get('X-Error-Code') == 'investment_recommendation_not_found'
    assert 'payload_json' not in response.text


def test_investment_decision_requires_both_preconditions(client, db_session):
    get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    response = client.post(
        '/api/v1/investments/recommendations/investment-recommendation:missing/decisions',
        json={'decision_type': 'accept'},
    )
    assert response.status_code == 428
    assert response.headers.get('X-Error-Code') == 'precondition_required'


def test_investment_decision_rejects_malformed_command(client, db_session):
    get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    response = client.post(
        '/api/v1/investments/recommendations/investment-recommendation:missing/decisions',
        json={'decision_type': 'BUY', 'owner_id': 999},
        headers={'If-Match': 'x', 'Idempotency-Key': 'same-key'},
    )
    assert response.status_code == 422


def test_wrong_owner_subject_is_not_resolved_to_another_user(client, db_session):
    owner = get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    assert owner is not None
    other = _client(issue_token(username='not-alex'))
    response = other.get('/api/v1/investments/recommendations')
    assert response.status_code == 401
