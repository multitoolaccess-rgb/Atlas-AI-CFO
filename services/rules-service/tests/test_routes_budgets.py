"""Atlas Phase 1 route tests — ``/api/budgets/`` CRUD + status endpoint.

Mirrors ``tests/test_routes_goals.py`` and ``tests/test_routes_accounts.py``
structure so the test suite feels uniform across resources:

- list-empty / create-then-list / get-by-id / get-missing-404,
- update partial / update missing-404,
- delete / delete is idempotent / delete missing-404.
- status endpoint: budget vs actual comparison, empty state, overspend.
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# -------- helpers --------

def _create_basic_budget(client, **overrides):
    """POST a baseline budget; returns the parsed response JSON."""
    payload = {"amount": 500.0, "period": "2026-07"}
    payload.update(overrides)
    r = client.post("/api/budgets/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_category(client, name="Groceries", budget_group="flexible"):
    """POST a category and return the response JSON."""
    r = client.post(
        "/api/categories/",
        json={"name": name, "budget_group": budget_group},
    )
    assert r.status_code == 201, r.text
    return r.json()


# -------- list --------

def test_list_budgets_empty_returns_200_and_empty_list(client):
    """Brand-new DB: GET ``/api/budgets/`` returns ``[]`` with HTTP 200."""
    r = client.get("/api/budgets/")
    assert r.status_code == 200
    assert r.json() == []


def test_list_budgets_filters_by_period(client):
    """GET ``/api/budgets/?period=2026-07`` only returns budgets for that period."""
    _create_basic_budget(client, period="2026-07")
    _create_basic_budget(client, period="2026-08")

    r = client.get("/api/budgets/", params={"period": "2026-07"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["period"] == "2026-07"


# -------- create --------

def test_create_budget_returns_201_then_list_returns_it(client):
    """POST ``/api/budgets/`` then GET ``/api/budgets/`` round-trips the new row."""
    r = client.post(
        "/api/budgets/",
        json={"amount": 1000.0, "period": "2026-07"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["amount"] == 1000.0
    assert created["period"] == "2026-07"
    assert created["category_id"] is None
    assert created["category_name"] is None
    assert "id" in created

    r = client.get("/api/budgets/")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["amount"] == 1000.0


def test_create_budget_with_category_returns_category_name(client):
    """POST ``/api/budgets/`` with a category_id resolves category_name in the response."""
    cat = _create_category(client, "Rent", "fixed")
    r = client.post(
        "/api/budgets/",
        json={"amount": 2000.0, "period": "2026-07", "category_id": cat["id"]},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["category_id"] == cat["id"]
    assert created["category_name"] == "Rent"


def test_create_budget_validates_required_fields(client):
    """POST ``/api/budgets/`` without amount or period returns 422."""
    r = client.post("/api/budgets/", json={})
    assert r.status_code == 422


def test_create_global_budget_succeeds_once_per_period(client):
    """A Global budget (category_id=None) can be created once per period."""
    r = client.post("/api/budgets/", json={"amount": 1000.0, "period": "2026-07"})
    assert r.status_code == 201
    assert r.json()["category_id"] is None


def test_create_second_global_budget_same_period_conflicts(client):
    """A second Global budget for the same period returns 409 with a clear message."""
    _create_basic_budget(client, amount=1000.0, period="2026-07")
    r = client.post("/api/budgets/", json={"amount": 500.0, "period": "2026-07"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Global budget already exists" in detail
    assert "2026-07" in detail


def test_global_budget_allowed_in_different_period(client):
    """A Global budget for a different period is allowed."""
    _create_basic_budget(client, amount=1000.0, period="2026-07")
    r = client.post("/api/budgets/", json={"amount": 500.0, "period": "2026-08"})
    assert r.status_code == 201
    assert r.json()["category_id"] is None


def test_multiple_category_budgets_same_period_allowed(client):
    """Multiple category budgets for the same period are still allowed."""
    cat1 = _create_category(client, "Rent", "fixed")
    cat2 = _create_category(client, "Groceries", "flexible")
    r1 = client.post(
        "/api/budgets/",
        json={"amount": 1000.0, "period": "2026-07", "category_id": cat1["id"]},
    )
    r2 = client.post(
        "/api/budgets/",
        json={"amount": 500.0, "period": "2026-07", "category_id": cat2["id"]},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201


# -------- update --------

def test_update_budget_changes_amount(client):
    """PUT ``/api/budgets/{id}`` mutates ONLY the declared fields."""
    budget = _create_basic_budget(client, amount=500.0)
    r = client.put(
        f"/api/budgets/{budget['id']}",
        json={"amount": 750.0},
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["id"] == budget["id"]
    assert updated["amount"] == 750.0
    assert updated["period"] == "2026-07"  # Untouched


def test_update_budget_missing_returns_404(client):
    """PUT on a non-existent budget id returns 404."""
    r = client.put("/api/budgets/99999", json={"amount": 100.0})
    assert r.status_code == 404
    assert r.json()["detail"] == "Budget not found"


# -------- delete --------

def test_delete_budget_removes_row(client):
    """DELETE ``/api/budgets/{id}`` removes the budget; subsequent GET returns empty."""
    budget = _create_basic_budget(client)
    assert len(client.get("/api/budgets/").json()) == 1

    r = client.delete(f"/api/budgets/{budget['id']}")
    assert r.status_code == 204
    assert r.content == b""

    assert client.get("/api/budgets/").json() == []


def test_delete_budget_second_delete_returns_404(client):
    """A second DELETE on a hard-deleted budget returns 404 (budgets use hard delete, not soft-archive)."""
    budget = _create_basic_budget(client)
    assert client.delete(f"/api/budgets/{budget['id']}").status_code == 204
    # Second delete: row is gone, returns 404.
    assert client.delete(f"/api/budgets/{budget['id']}").status_code == 404


def test_delete_budget_missing_returns_404(client):
    """DELETE on a non-existent budget id returns 404."""
    r = client.delete("/api/budgets/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Budget not found"


# -------- auth --------

def test_budgets_require_auth(client_no_auth):
    """All budget endpoints reject unauthenticated requests."""
    assert client_no_auth.get("/api/budgets/").status_code == 401
    assert client_no_auth.post("/api/budgets/", json={"amount": 1, "period": "2026-07"}).status_code == 401
    assert client_no_auth.put("/api/budgets/1", json={"amount": 1}).status_code == 401
    assert client_no_auth.delete("/api/budgets/1").status_code == 401


# -------- status endpoint --------

def test_budget_status_empty_returns_zero_totals(client):
    """GET ``/api/budgets/status?period=2026-07`` with no budgets returns zero totals."""
    r = client.get("/api/budgets/status", params={"period": "2026-07"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == "2026-07"
    assert body["categories"] == []
    assert body["totals"]["planned"] == 0
    assert body["totals"]["actual"] == 0
    assert body["totals"]["remaining"] == 0
    assert body["totals"]["percent_used"] == 0


def test_budget_status_returns_budget_vs_actual(client, db_session, make_account, make_transaction, make_category):
    """Status endpoint compares planned budgets against actual spending."""
    from app.models import Budget

    # Create a category + budget
    cat = _create_category(client, "Dining", "flexible")
    _create_basic_budget(client, amount=300.0, period="2026-07", category_id=cat["id"])

    # Create an account + transaction that falls within the period
    acc = make_account(account_type="checking")
    db_session.add(acc)
    db_session.commit()

    from datetime import datetime

    txn = make_transaction(
        account_id=acc.id,
        description="Restaurant dinner",
        amount=-75.0,
        transaction_date=datetime(2026, 7, 15),
        category_id=cat["id"],
    )
    db_session.add(txn)
    db_session.commit()

    r = client.get("/api/budgets/status", params={"period": "2026-07"})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["period"] == "2026-07"
    assert len(body["categories"]) == 1
    cat_status = body["categories"][0]
    assert cat_status["category_name"] == "Dining"
    assert cat_status["budget_group"] == "flexible"
    assert cat_status["planned"] == 300.0
    assert cat_status["actual"] == 75.0
    assert cat_status["remaining"] == 225.0
    assert cat_status["percent_used"] == 25.0

    assert body["totals"]["planned"] == 300.0
    assert body["totals"]["actual"] == 75.0


def test_budget_status_overspend_shows_negative_remaining(client, db_session, make_account, make_transaction):
    """When actual > planned, remaining is negative and percent_used > 100."""
    from datetime import datetime

    cat = _create_category(client, "Entertainment", "flexible")
    _create_basic_budget(client, amount=100.0, period="2026-07", category_id=cat["id"])

    acc = make_account(account_type="checking")
    db_session.add(acc)
    db_session.commit()

    txn = make_transaction(
        account_id=acc.id,
        description="Concert tickets",
        amount=-150.0,
        transaction_date=datetime(2026, 7, 20),
        category_id=cat["id"],
    )
    db_session.add(txn)
    db_session.commit()

    r = client.get("/api/budgets/status", params={"period": "2026-07"})
    assert r.status_code == 200
    cat_status = r.json()["categories"][0]
    assert cat_status["actual"] == 150.0
    assert cat_status["remaining"] == -50.0
    assert cat_status["percent_used"] == 150.0


def test_budget_status_excludes_other_periods(client, db_session, make_account, make_transaction):
    """Transactions outside the queried period don't affect the status."""
    from datetime import datetime

    cat = _create_category(client, "Shopping", "flexible")
    _create_basic_budget(client, amount=500.0, period="2026-07", category_id=cat["id"])

    acc = make_account(account_type="checking")
    db_session.add(acc)
    db_session.commit()

    # Transaction in August — shouldn't count for July
    txn = make_transaction(
        account_id=acc.id,
        description="August purchase",
        amount=-200.0,
        transaction_date=datetime(2026, 8, 5),
        category_id=cat["id"],
    )
    db_session.add(txn)
    db_session.commit()

    r = client.get("/api/budgets/status", params={"period": "2026-07"})
    assert r.status_code == 200
    cat_status = r.json()["categories"][0]
    assert cat_status["actual"] == 0.0
    assert cat_status["percent_used"] == 0.0


def test_budget_status_requires_period_param(client):
    """GET ``/api/budgets/status`` without period returns 422."""
    r = client.get("/api/budgets/status")
    assert r.status_code == 422


def test_budget_status_multiple_categories(client, db_session, make_account, make_transaction):
    """Status endpoint aggregates across multiple budgeted categories."""
    from datetime import datetime

    cat1 = _create_category(client, "Food", "fixed")
    cat2 = _create_category(client, "Transport", "flexible")
    _create_basic_budget(client, amount=400.0, period="2026-07", category_id=cat1["id"])
    _create_basic_budget(client, amount=200.0, period="2026-07", category_id=cat2["id"])

    acc = make_account(account_type="checking")
    db_session.add(acc)
    db_session.commit()

    for desc, amt, cid, day in [
        ("Grocery store", -120.0, cat1["id"], 10),
        ("Gas station", -45.0, cat2["id"], 12),
        ("Restaurant", -60.0, cat1["id"], 18),
    ]:
        txn = make_transaction(
            account_id=acc.id,
            description=desc,
            amount=amt,
            transaction_date=datetime(2026, 7, day),
            category_id=cid,
        )
        db_session.add(txn)
    db_session.commit()

    r = client.get("/api/budgets/status", params={"period": "2026-07"})
    assert r.status_code == 200
    body = r.json()

    assert len(body["categories"]) == 2
    assert body["totals"]["planned"] == 600.0
    assert body["totals"]["actual"] == 225.0  # 120 + 60 + 45
    assert body["totals"]["remaining"] == 375.0
