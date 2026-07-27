"""Phase 4 route tests \u2014 /api/accounts/ (\u22652 tests per resource per the user's spec)."""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


def test_list_accounts_empty_returns_200_and_empty_list(client):
    """Brand-new DB: GET ``/api/accounts/`` returns ``[]`` with HTTP 200."""
    r = client.get("/api/accounts/")
    assert r.status_code == 200
    assert r.json() == []


def test_create_account_returns_201_then_list_returns_it(client):
    """POST ``/api/accounts/`` then GET ``/api/accounts/`` \u2014 round trips the new row."""
    payload = {
        "account_name": "Phase 4 Checking",
        "account_type": "checking",
        "institution_name": "Phase 4 Bank",
        "current_balance": 1500.50,
    }
    r = client.post("/api/accounts/", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["account_name"] == "Phase 4 Checking"
    assert created["current_balance"] == 1500.50
    assert created["is_active"] is True
    assert "id" in created

    r = client.get("/api/accounts/")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["account_name"] == "Phase 4 Checking"


def test_get_account_by_id_returns_row(client):
    """GET ``/api/accounts/{id}`` after a POST \u2014 returns the same row."""
    create = client.post(
        "/api/accounts/",
        json={
            "account_name": "Specific Test",
            "account_type": "savings",
            "institution_name": "Specific Bank",
            "current_balance": 42.0,
        },
    )
    new_id = create.json()["id"]

    r = client.get(f"/api/accounts/{new_id}")
    assert r.status_code == 200
    assert r.json()["account_name"] == "Specific Test"
    assert r.json()["id"] == new_id


def test_get_account_missing_returns_404(client):
    """GET ``/api/accounts/{nonexistent}`` returns 404."""
    r = client.get("/api/accounts/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Account not found"


# ---------------------------------------------------------------------
# Phase 7: PUT (partial update) + DELETE (soft-delete)
# ---------------------------------------------------------------------


def _create_basic_account(client, **overrides):
    """Helper to POST a baseline account; returns the parsed response JSON."""
    payload = {
        "account_name": "Edit Target",
        "account_type": "checking",
        "institution_name": "Edit Bank",
        "current_balance": 100.0,
    }
    payload.update(overrides)
    r = client.post("/api/accounts/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_update_account_partial_renames_and_rebalances(client):
    """PUT ``/api/accounts/{id}`` mutates ONLY the declared fields."""
    acc = _create_basic_account(client, account_name="Original Name", current_balance=100.0)
    r = client.put(
        f"/api/accounts/{acc['id']}",
        json={"account_name": "Renamed", "current_balance": 250.5},
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["id"] == acc["id"]
    assert updated["account_name"] == "Renamed"
    assert updated["current_balance"] == 250.5
    # Untouched fields are preserved (partial semantics; null fields skipped).
    assert updated["account_type"] == "checking"
    assert updated["is_active"] is True

    # GET-by-id confirms the persisted state.
    r = client.get(f"/api/accounts/{acc['id']}")
    assert r.status_code == 200
    assert r.json()["account_name"] == "Renamed"


def test_update_account_reactivates_via_is_active(client):
    """PUT with ``is_active=true`` after soft-delete re-includes the row in list."""
    acc = _create_basic_account(client)

    # Deactivate first.
    r = client.delete(f"/api/accounts/{acc['id']}")
    assert r.status_code == 204
    assert client.get("/api/accounts/").json() == []

    # Reactivate.
    r = client.put(f"/api/accounts/{acc['id']}", json={"is_active": True})
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    # Back in the listing.
    listed = client.get("/api/accounts/").json()
    assert len(listed) == 1
    assert listed[0]["id"] == acc["id"]


def test_update_account_missing_returns_404(client):
    """PUT on a non-existent account id returns 404 (no row shadowing)."""
    r = client.put("/api/accounts/99999", json={"account_name": "X"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Account not found"


def test_delete_account_soft_deactivates_and_hides_from_list(client):
    """DELETE flips ``is_active=False``; a subsequent GET-by-id still returns the row, but
    list_accounts filters it out."""
    acc = _create_basic_account(client)
    assert client.get("/api/accounts/").json() == [acc]

    r = client.delete(f"/api/accounts/{acc['id']}")
    assert r.status_code == 204
    # 204 No Content => empty body.
    assert r.content == b""

    # Listing hides the inactive row.
    assert client.get("/api/accounts/").json() == []
    # But GET-by-id still returns it (FK preservation guarantee).
    r = client.get(f"/api/accounts/{acc['id']}")
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_delete_account_is_idempotent(client):
    """A second DELETE on an already-inactive row still returns 204."""
    acc = _create_basic_account(client)
    assert client.delete(f"/api/accounts/{acc['id']}").status_code == 204
    # Idempotent path: no DB write, no error.
    assert client.delete(f"/api/accounts/{acc['id']}").status_code == 204


def test_delete_account_missing_returns_404(client):
    """DELETE on a non-existent account id returns 404."""
    r = client.delete("/api/accounts/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Account not found"
