# services/rules-service/tests/test_categories_hierarchy.py
#
# Phase 30h — sub-category hierarchy (categories.parent_id).
#
# Boundary tests:
#   1. Creating a category with ``parent_id`` nests it under the parent
#      and INHERITS the parent's ``group`` (the hierarchy is the source
#      of truth, not a redundant group field).
#   2. A missing parent → 404.
#   3. Updating ``parent_id`` validates the parent + inherits its group
#      when ``group`` is not explicitly patched.
#   4. A category can never be its own parent (400).
#   5. A category can never be linked under one of its own descendants
#      (cycle guard → 400).
#   6. The list endpoint serializes ``parent_id`` + ``parent_name``.
import pytest


def _create(client, name, **extra):
    payload = {"name": name, **extra}
    r = client.post("/api/categories/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_child_inherits_parent_group(client):
    parent = _create(client, "Food & Dining", group="Expenses")
    child = _create(client, "Coffee Shops", parent_id=parent["id"], group="Income")

    # The hierarchy wins: a child always lives in its parent's group.
    assert child["parent_id"] == parent["id"]
    assert child["parent_name"] == "Food & Dining"
    assert child["group"] == "Expenses"


def test_create_child_missing_parent_404(client):
    r = client.post("/api/categories/", json={"name": "Orphan", "parent_id": 9999})
    assert r.status_code == 404
    assert "Parent category" in r.json()["detail"]


def test_list_serializes_parent_name(client):
    parent = _create(client, "Transportation", group="Expenses")
    _create(client, "Rideshare", parent_id=parent["id"])

    r = client.get("/api/categories/")
    assert r.status_code == 200
    by_name = {c["name"]: c for c in r.json()}
    assert by_name["Rideshare"]["parent_id"] == parent["id"]
    assert by_name["Rideshare"]["parent_name"] == "Transportation"
    assert by_name["Transportation"]["parent_id"] is None
    assert by_name["Transportation"]["parent_name"] is None


def test_update_moves_category_under_parent_and_inherits_group(client):
    parent = _create(client, "Shopping", group="Expenses")
    child = _create(client, "Online Retail", group="Expenses")
    assert child["parent_id"] is None

    r = client.put(f"/api/categories/{child['id']}", json={"parent_id": parent["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_id"] == parent["id"]
    assert body["parent_name"] == "Shopping"
    assert body["group"] == "Expenses"


def test_update_cannot_make_category_its_own_parent(client):
    cat = _create(client, "Self Parent", group="Expenses")
    r = client.put(f"/api/categories/{cat['id']}", json={"parent_id": cat["id"]})
    assert r.status_code == 400
    assert "own parent" in r.json()["detail"]


def test_update_rejects_cycle_via_descendant(client):
    """A → B → C. Linking A under C would create A→C→B→A — rejected."""
    a = _create(client, "Cycle A", group="Expenses")
    b = _create(client, "Cycle B", group="Expenses", parent_id=a["id"])
    c = _create(client, "Cycle C", group="Expenses", parent_id=b["id"])

    r = client.put(f"/api/categories/{a['id']}", json={"parent_id": c["id"]})
    assert r.status_code == 400
    assert "cycle" in r.json()["detail"].lower()


def test_update_parent_missing_404(client):
    cat = _create(client, "No Parent", group="Expenses")
    r = client.put(f"/api/categories/{cat['id']}", json={"parent_id": 5555})
    assert r.status_code == 404


def test_update_can_clear_parent(client):
    parent = _create(client, "Parent X", group="Expenses")
    child = _create(client, "Child Y", group="Expenses", parent_id=parent["id"])
    r = client.put(f"/api/categories/{child['id']}", json={"parent_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["parent_id"] is None
