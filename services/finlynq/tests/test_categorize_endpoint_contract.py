"""Phase-F4 contract: POST /categorize + /categories CRUD return
200 today (real implementation; F1 ship target was 501 stubs).

Locked shapes (mirroring rules-service for cross-service wire parity):

- ``POST /categorize`` →
  request:  { transactions: [{merchant_name, description}, ...] }
  response: { categorized: int, skipped: int, total: int }

- ``GET    /categories``   → List[CategoryOut]
- ``POST   /categories``   → CategoryOut (id, name, description, icon, color)
- ``PUT    /categories/{id}`` → CategoryOut (partial update)

Phase-F4 also adds:
- 401 contract — ``Depends(require_user)`` rejects unauthenticated POST /categorize.
- Idempotency contract — re-POSTing the same category name returns 409
  (NOT 201 / NOT 200) so the FE knows it's a duplicate. The cross-service
  forwarder at rules-service's ``POST /api/categories/`` MUST propagate
  this 409 verbatim so the FE surfaces the same error regardless of
  which service handles the request.
"""
import pytest
from fastapi.testclient import TestClient

from app.models import Category
from app.routes.categorize import (
    CategoryCreatePayload,
    CategoryOut,
    CategoryUpdatePayload,
    CategorizeRequest,
    CategorizeResponse,
)


# ---------------------------------------------------------------------
# Wire-shape lock — mirrors test_cross_service_schema.py field set
# ---------------------------------------------------------------------


def test_categorize_request_response_shape_is_locked():
    """Pin the Pydantic shapes — F4 must respect these."""
    categorize_req_fields = set(CategorizeRequest.model_fields.keys())
    assert categorize_req_fields == {"transactions"}, (
        f"CategorizeRequest drifted (got {categorize_req_fields!r}); "
        f"F4 accepts the same wire shape rules-service's "
        f"POST /api/transactions/categorize accepts today."
    )

    categorize_resp_fields = set(CategorizeResponse.model_fields.keys())
    assert categorize_resp_fields == {"categorized", "skipped", "total"}, (
        f"CategorizeResponse drifted (got {categorize_resp_fields!r}); "
        f"F4 returns the same {categorized, skipped, total} tuple so "
        f"the rules-service forwarder is a 5-line proxy."
    )

    category_create_fields = set(CategoryCreatePayload.model_fields.keys())
    assert category_create_fields == {"name", "description", "icon", "color"}, (
        f"CategoryCreatePayload drifted (got {category_create_fields!r})."
    )

    category_update_fields = set(CategoryUpdatePayload.model_fields.keys())
    assert category_update_fields == {"name", "description", "icon", "color"}, (
        f"CategoryUpdatePayload drifted (got {category_update_fields!r})."
    )

    category_out_fields = set(CategoryOut.model_fields.keys())
    assert category_out_fields == {"id", "name", "description", "icon", "color"}, (
        f"CategoryOut drifted (got {category_out_fields!r})."
    )


# ---------------------------------------------------------------------
# POST /categorize — auth-gated, returns 200 with real counts
# ---------------------------------------------------------------------


def test_categorize_returns_401_without_auth(client: TestClient):
    response = client.post(
        "/categorize",
        json={"transactions": [{"id": 1, "merchant_name": "Starbucks", "description": "Coffee"}]},
    )
    assert response.status_code == 401, (
        f"POST /categorize must return 401 without a valid JWT cookie (got {response.status_code})."
    )


def test_categorize_returns_200_and_counts(client_with_auth: TestClient):
    """Heuristic round-trip: a 4-row payload maps to 2 categorized
    (Starbucks → Food & Dining; PAYROLL DEPOSIT → Income) + 1 skipped
    (no match) = 3 total."""
    response = client_with_auth.post(
        "/categorize",
        json={
            "transactions": [
                {"id": 1, "merchant_name": "Starbucks Coffee #99", "description": ""},
                {"id": 2, "merchant_name": "PAYROLL DEPOSIT ABC", "description": ""},
                {"id": 3, "merchant_name": "ZZZBRAND RANDOM", "description": ""},
            ]
        },
    )
    assert response.status_code == 200, (
        f"POST /categorize must return 200 with the real impl (got {response.status_code} {response.text})"
    )
    body = response.json()
    assert body["categorized"] == 2, f"expected 2 categorized, got {body}"
    assert body["skipped"] == 1, f"expected 1 skipped (no-match), got {body}"
    assert body["total"] == 3, f"expected total=3, got {body}"


def test_categorize_with_empty_payload_returns_zero_counts(client_with_auth: TestClient):
    response = client_with_auth.post("/categorize", json={"transactions": []})
    assert response.status_code == 200
    body = response.json()
    assert body == {"categorized": 0, "skipped": 0, "total": 0}


# ---------------------------------------------------------------------
# GET / POST / PUT /categories — auth-gated CRUD
# ---------------------------------------------------------------------


def test_categories_get_is_public_reference_data(client: TestClient):
    """Phase-F4 reference-data decision: GET /categories is PUBLIC
    (no JWT required) because the canonical category list is shared
    taxonomy across all users — the 12 default seeds appear for a
    fresh-DB visitor without a dev-login round-trip.

    POST + PUT remain auth-gated via ``Depends(require_user)`` on the
    route handler because adding / renaming a custom category IS a
    user-edit.
    """
    response = client.get("/categories")
    assert response.status_code == 200, (
        f"GET /categories must be PUBLIC reference data (got {response.status_code})."
    )
    body = response.json()
    assert isinstance(body, list), (
        f"GET /categories must return List[CategoryOut] (got {type(body).__name__})"
    )


def test_categories_list_returns_seeded_categories(client_with_auth: TestClient):
    """Phase-F4 hermetic seed: ``seed_default_categories`` runs during
    session-scope bootstrap, so 12 categories are present."""
    response = client_with_auth.get("/categories")
    assert response.status_code == 200
    body = response.json()
    names = {row["name"] for row in body}
    expected = {
        "Income", "Transfer", "Food & Dining", "Groceries",
        "Transportation", "Shopping", "Entertainment",
        "Bills & Utilities", "Health", "Travel", "Education",
        "Other",
    }
    assert expected.issubset(names), (
        f"Default categories missing from seed: {expected - names}"
    )


def test_categories_post_returns_201_with_id(client_with_auth: TestClient):
    payload = {
        "name": "Pet Care 11" + str(__import__("time").time()),
        "description": "Vet, food, grooming",
        "icon": "⚓",
        "color": "#22c55e",
    }
    response = client_with_auth.post("/categories", json=payload)
    assert response.status_code == 201, (
        f"POST /categories must return 201 (got {response.status_code} {response.text})"
    )
    body = response.json()
    assert body["name"] == payload["name"]
    assert body["id"] > 0


def test_categories_put_returns_200_with_renamed_row(client_with_auth: TestClient, db_session):
    cat = db_session.query(Category).filter(Category.name == "Other").first()
    assert cat is not None
    response = client_with_auth.put(
        f"/categories/{cat.id}",
        json={"name": "Other / Misc 22", "color": "#0ea5e9"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Other / Misc 22"
    assert body["color"] == "#0ea5e9"


def test_categories_put_unknown_id_returns_404(client_with_auth: TestClient):
    response = client_with_auth.put(
        "/categories/999999",
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


def test_categories_post_rejects_empty_name(client_with_auth: TestClient):
    response = client_with_auth.post("/categories", json={"name": "   "})
    assert response.status_code == 400


# ---------------------------------------------------------------------
# Idempotency lock — Phase F4 promotion from F1 contract test to
# enforce the cross-service forwarder round-trip + the wire-shape
# invariant for duplicate names.
# ---------------------------------------------------------------------


def test_idempotent_categorize_for_same_payload(client_with_auth: TestClient):
    """POST /categorize is deterministic: re-POSTing the same payload
    yields the SAME counts. The Phase-F4 forwarder at rules-service
    propagates this verbatim — the FE surfaces "tagged N of M" on
    the second button-press without an extra GET.
    """
    payload = {
        "transactions": [
            {"id": 1, "merchant_name": "WHOLE FOODS MARKET", "description": ""},
        ]
    }
    r1 = client_with_auth.post("/categorize", json=payload)
    r2 = client_with_auth.post("/categorize", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json(), (
        f"POST /categorize must be deterministic — first call {r1.json()}, "
        f"second call {r2.json()}"
    )


def test_categories_post_is_idempotent_409_on_duplicate_name(client_with_auth: TestClient):
    """Phase-F4 idempotency contract: the FIRST POST creates a row
    (201); a SECOND POST with the same name surfaces as HTTP 409
    (NOT 201 — we do NOT silently overwrite; the FE mirrors this
    so the cross-service forwarder at rules-service propagates
    409 verbatim).

    This is the load-bearing contract the user quoted as
    ``test_idempotent_categorize_for_same_description`` (canonical
    name) but with the implementation intent to also test the
    cross-service wire-shape accuracy: the second POST should not
    flip the first row's id; instead it returns 409 with the
    "already exists" detail.
    """
    payload = {
        "name": "Test Idempotency " + str(__import__("time").time()),
        "icon": "🧪",
        "color": "#ffffff",
    }
    r1 = client_with_auth.post("/categories", json=payload)
    assert r1.status_code == 201, f"first POST must 201 (got {r1.status_code}): {r1.text}"
    first_id = r1.json()["id"]

    r2 = client_with_auth.post("/categories", json=payload)
    assert r2.status_code == 409, (
        f"second POST must 409 (the duplicate name surfaces as "
        f"a conflict, not silently overwrite the first row): "
        f"got {r2.status_code} {r2.text}"
    )
    assert "exists" in str(r2.json().get("detail", "")).lower(), (
        f"the 409 detail should carry the 'exists' marker for the FE "
        f"to introspect; got {r2.text}"
    )

    # Idempotency invariant: the FIRST row's id is preserved — no
    # silent overwrite to a NEW id, no caller-visible churn.
    r3 = client_with_auth.get("/categories")
    matching = [row for row in r3.json() if row["name"] == payload["name"]]
    assert len(matching) == 1, (
        f"duplicate POST must NOT create a second row (got {len(matching)} matches)"
    )
    assert matching[0]["id"] == first_id, (
        f"the original row ID must be preserved (expected {first_id}, "
        f"got {matching[0]['id']})"
    )
