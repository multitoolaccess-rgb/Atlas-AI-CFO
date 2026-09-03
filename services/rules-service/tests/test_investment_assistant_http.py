def test_investment_context_requires_auth(client_no_auth):
    response = client_no_auth.post(
        "/api/v1/investments/assistant/context",
        json={"selector": {"security_id": "sec:test"}},
    )
    assert response.status_code == 401


def test_investment_tool_requires_auth(client_no_auth):
    response = client_no_auth.post(
        "/api/v1/investments/assistant/tool",
        json={"tool": "get_investment_context", "selector": {"security_id": "sec:test"}},
    )
    assert response.status_code == 401


def test_investment_tool_returns_bounded_unavailable_context(client):
    response = client.post(
        "/api/v1/investments/assistant/tool",
        json={"tool": "get_investment_context", "selector": {"security_id": "sec:unknown"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tool"] == "get_investment_context"
    assert body["context"]["state"] == "unavailable"


def test_investment_context_rejects_empty_selector(client):
    response = client.post(
        "/api/v1/investments/assistant/context",
        json={"selector": {}},
    )
    assert response.status_code == 422


def test_investment_context_rejects_client_authoritative_payload(client):
    response = client.post(
        "/api/v1/investments/assistant/context",
        json={
            "selector": {"security_id": "sec:test"},
            "recommendation": {"action": "BUY", "recommendation_hash": "fake"},
        },
    )
    assert response.status_code == 422


def test_investment_context_does_not_leak_unknown_security(client):
    response = client.post(
        "/api/v1/investments/assistant/context",
        json={"selector": {"security_id": "sec:unknown"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "unavailable"
    assert body["recommendation"] is None
    assert body["committee"] is None
