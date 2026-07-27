"""Phase 4 route tests \u2014 /api/plaid/.

PLAID_CLIENT_ID / PLAID_SECRET are unset for tests (see conftest.py), so the
endpoints MUST surface a 501 (NotImplemented) with our chosen `use the
statement-upload ingest` message rather than 500-ing silently. Phase 7 will
flip this once a real Plaid sandbox is wired.
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


def test_create_link_token_without_plaid_env_returns_501(client):
    """Without PLAID_CLIENT_ID \u2014 501 with a redirect message to /api/imports."""
    r = client.post("/api/plaid/create_link_token")
    assert r.status_code == 501
    detail = r.json()["detail"]
    assert "Plaid not configured" in detail
    assert "/api/imports" in detail  # pointer to the alternative ingest path


def test_exchange_public_token_without_plaid_env_returns_501(client):
    """Same 501 contract for the exchange endpoint."""
    r = client.post(
        "/api/plaid/exchange_public_token",
        json={"public_token": "public-sandbox-XXXX"},
    )
    assert r.status_code == 501
    assert "Plaid not configured" in r.json()["detail"]
