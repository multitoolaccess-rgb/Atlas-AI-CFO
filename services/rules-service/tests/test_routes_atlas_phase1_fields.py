"""Atlas Phase 1 field tests — Account debt fields + Category budget_group.

Verifies that the new columns added to Account and Category models
are correctly accepted and persisted through the CRUD routes.
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# -------- Account debt fields --------

def test_create_account_with_debt_fields(client):
    """POST ``/api/accounts/`` with debt fields persists them."""
    r = client.post(
        "/api/accounts/",
        json={
            "account_name": "Home Mortgage",
            "account_type": "mortgage",
            "institution_name": "Chase Bank",
            "current_balance": -350000.0,
            "interest_rate": 6.5,
            "credit_limit": None,
            "minimum_payment": 2200.0,
            "term_months": 360,
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["interest_rate"] == 6.5
    assert created["minimum_payment"] == 2200.0
    assert created["term_months"] == 360


def test_create_credit_card_with_credit_limit(client):
    """POST ``/api/accounts/`` credit card with credit_limit."""
    r = client.post(
        "/api/accounts/",
        json={
            "account_name": "Visa Platinum",
            "account_type": "credit_card",
            "institution_name": "Capital One",
            "current_balance": -3500.0,
            "credit_limit": 10000.0,
            "interest_rate": 19.99,
            "minimum_payment": 75.0,
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["credit_limit"] == 10000.0
    assert created["interest_rate"] == 19.99
    assert created["minimum_payment"] == 75.0


def test_update_account_debt_fields(client):
    """PUT ``/api/accounts/{id}`` can update debt fields."""
    r = client.post(
        "/api/accounts/",
        json={
            "account_name": "Auto Loan",
            "account_type": "loan",
            "institution_name": "Wells Fargo",
            "current_balance": -15000.0,
        },
    )
    assert r.status_code == 201
    acc_id = r.json()["id"]

    # Update with debt fields
    r = client.put(
        f"/api/accounts/{acc_id}",
        json={
            "interest_rate": 4.5,
            "minimum_payment": 350.0,
            "term_months": 60,
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["interest_rate"] == 4.5
    assert updated["minimum_payment"] == 350.0
    assert updated["term_months"] == 60


def test_create_account_without_debt_fields_defaults_null(client):
    """POST ``/api/accounts/`` without debt fields leaves them null (backward compat)."""
    r = client.post(
        "/api/accounts/",
        json={
            "account_name": "Checking",
            "account_type": "checking",
            "institution_name": "Bank",
            "current_balance": 1000.0,
        },
    )
    assert r.status_code == 201
    created = r.json()
    # Debt fields should not appear or be null
    assert created.get("interest_rate") is None
    assert created.get("credit_limit") is None
    assert created.get("minimum_payment") is None
    assert created.get("term_months") is None


# -------- Category budget_group --------

def test_create_category_with_budget_group(client):
    """POST ``/api/categories/`` with budget_group persists it."""
    r = client.post(
        "/api/categories/",
        json={"name": "Rent", "budget_group": "fixed"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["budget_group"] == "fixed"


def test_create_category_with_flexible_group(client):
    """POST ``/api/categories/`` with budget_group='flexible'."""
    r = client.post(
        "/api/categories/",
        json={"name": "Entertainment", "budget_group": "flexible"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["budget_group"] == "flexible"


def test_create_category_without_budget_group_defaults_to_flexible(client):
    """POST ``/api/categories/`` without budget_group defaults to 'flexible'."""
    r = client.post(
        "/api/categories/",
        json={"name": "Misc"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["budget_group"] == "flexible"


def test_update_category_budget_group(client):
    """PUT ``/api/categories/{id}`` can update budget_group."""
    r = client.post(
        "/api/categories/",
        json={"name": "Savings", "budget_group": "savings"},
    )
    assert r.status_code == 201
    cat_id = r.json()["id"]

    r = client.put(
        f"/api/categories/{cat_id}",
        json={"budget_group": "fixed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["budget_group"] == "fixed"


def test_create_category_with_all_budget_groups(client):
    """All 5 budget_group values are accepted."""
    groups = ["fixed", "flexible", "debt", "savings", "other"]
    for i, group in enumerate(groups):
        r = client.post(
            "/api/categories/",
            json={"name": f"Cat {group} {i}", "budget_group": group},
        )
        assert r.status_code == 201, f"budget_group={group} failed: {r.text}"
        assert r.json()["budget_group"] == group
