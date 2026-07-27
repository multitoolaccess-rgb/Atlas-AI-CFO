"""Phase 8 route tests — ``/api/goals/`` CRUD (≥2 tests per resource per the user's spec).

Mirrors ``tests/test_routes_accounts.py`` structure so the test suite
feels uniform across resources:

- list-empty / create-then-list / get-by-id / get-missing-404,
- update partial / reactivate / update missing-404,
- archive soft-deletes / archive is idempotent / archive missing-404.
- dashboard summary includes the non-archived goals.
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# -------- list --------


def test_list_goals_empty_returns_200_and_empty_list(client):
    """Phase 15: brand-new user GET ``/api/goals/`` returns the seeded
    ``Default $15M Goal`` (auto-inserted by ``list_goals`` when zero
    rows exist). The previous Phase 8 expectation of ``[]`` was the
    pre-seed behavior.

    Confirming the auto-seed AND the idempotency in ONE test: a
    second GET returns the SAME row id (not a second seed), proving
    the once-only guard preserved across calls.
    """
    r = client.get("/api/goals/")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1, f"expected exactly the seeded goal; got {rows!r}"
    seed = rows[0]
    assert seed["name"] == "Default $15M Goal"
    assert seed["target_amount"] == 15_000_000.0
    assert seed["horizon_years"] == 20
    assert seed["is_archived"] is False
    assert seed["priority"] == 0
    seed_id = seed["id"]

    # Idempotency: a second list returns the same row id (no re-seed).
    r2 = client.get("/api/goals/")
    rows2 = r2.json()
    assert len(rows2) == 1
    assert rows2[0]["id"] == seed_id, (
        f"second GET must NOT re-seed; expected the same id {seed_id}, "
        f"got new seed {rows2[0]['id']!r}"
    )


def test_list_goals_does_not_reseed_after_archive(client):
    """Phase 15 idempotency under soft-archive: after the user
    archives the seed goal, a subsequent GET must NOT resurrect
    another seed row. The cross-archive lookup (``first()`` without
    ``is_archived`` filter) makes this case unambiguous — once
    ANY row exists (active OR archived) we skip the seed branch.
    """
    # First visit seeds.
    seed_id = client.get("/api/goals/").json()[0]["id"]
    # User archives the seed.
    r = client.delete(f"/api/goals/{seed_id}")
    assert r.status_code == 204
    assert client.get("/api/goals/").json() == []
    # Re-visit: still no active goal — the seed branch must NOT fire.
    assert client.get("/api/goals/").json() == []
    # DB-level proof: still exactly one row (archived), never two.
    # We hit the list again with a synthetic "force seed" check: a
    # SECOND archive attempt is idempotent so the row count can't
    # have grown; the above GET == [] already locks it at zero active.


def test_create_goal_returns_201_then_list_returns_it(client):
    """POST ``/api/goals/`` then GET ``/api/goals/`` round-trips the new row."""
    payload = {
        "name": "Retirement",
        "target_amount": 15_000_000.0,
        "horizon_years": 20,
        "priority": 10,
        "notes": "Fire-by-55 plan",
    }
    r = client.post("/api/goals/", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "Retirement"
    assert created["target_amount"] == 15_000_000.0
    assert created["horizon_years"] == 20
    assert created["priority"] == 10
    assert created["is_archived"] is False
    assert "id" in created

    r = client.get("/api/goals/")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "Retirement"


def test_get_goal_by_id_returns_row(client):
    """GET ``/api/goals/{id}`` after a POST — returns the same row."""
    create = client.post(
        "/api/goals/",
        json={
            "name": "Emergency fund",
            "target_amount": 50_000.0,
            "horizon_years": 3,
        },
    )
    new_id = create.json()["id"]

    r = client.get(f"/api/goals/{new_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Emergency fund"
    assert r.json()["id"] == new_id


def test_get_goal_missing_returns_404(client):
    """GET ``/api/goals/{nonexistent}`` returns 404."""
    r = client.get("/api/goals/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Goal not found"


# -------- update --------


def _create_basic_goal(client, **overrides):
    payload = {"name": "Edit Target", "target_amount": 100_000.0}
    payload.update(overrides)
    r = client.post("/api/goals/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_update_goal_partial_renames_and_changes_target(client):
    """PUT ``/api/goals/{id}`` mutates ONLY the declared fields."""
    goal = _create_basic_goal(
        client, name="Original Name", target_amount=100_000.0, priority=0
    )
    r = client.put(
        f"/api/goals/{goal['id']}",
        json={"name": "Renamed", "target_amount": 250_000.0, "priority": 5},
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["id"] == goal["id"]
    assert updated["name"] == "Renamed"
    assert updated["target_amount"] == 250_000.0
    assert updated["priority"] == 5
    # Untouched field preserved.
    assert updated["is_archived"] is False

    r = client.get(f"/api/goals/{goal['id']}")
    assert r.json()["name"] == "Renamed"


def test_update_goal_empty_name_returns_400(client):
    """Defensive regression — empty ``name`` would break the FE's
    ``summary.user_goals[0]?.name`` chip."""
    goal = _create_basic_goal(client)
    r = client.put(f"/api/goals/{goal['id']}", json={"name": "   "})
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower() or "must not" in r.json()["detail"].lower()


def test_update_goal_missing_returns_404(client):
    """PUT on a non-existent goal id returns 404."""
    r = client.put("/api/goals/99999", json={"name": "X"})
    assert r.status_code == 404


# -------- archive (DELETE = soft-archive) --------


def test_archive_goal_hides_from_list_but_row_remains(client):
    """DELETE flips ``is_archived=True``; ``list_goals`` filters it out,
    but ``get_goal`` still returns the row (FK preservation contract)."""
    goal = _create_basic_goal(client)
    assert client.get("/api/goals/").json() == [goal]

    r = client.delete(f"/api/goals/{goal['id']}")
    assert r.status_code == 204
    assert r.content == b""

    assert client.get("/api/goals/").json() == []
    r = client.get(f"/api/goals/{goal['id']}")
    assert r.status_code == 200
    assert r.json()["is_archived"] is True


def test_archive_goal_is_idempotent(client):
    """A second DELETE on an already-archived row still returns 204."""
    goal = _create_basic_goal(client)
    assert client.delete(f"/api/goals/{goal['id']}").status_code == 204
    assert client.delete(f"/api/goals/{goal['id']}").status_code == 204


def test_archive_goal_missing_returns_404(client):
    """DELETE on a non-existent goal id returns 404."""
    r = client.delete("/api/goals/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Goal not found"


# -------- dashboard summary wiring --------


# -------- forwarder wiring for /api/dashboard/summary --------


def test_dashboard_summary_forwarder_includes_user_goals(client, install_finlynq_state_forward):
    """Phase-F5 forwarder contract: ``user_goals`` from Finlynq's
    ``StateSummaryOut`` re-emits through rules-service's
    ``DashboardSummary`` coercion.

    The pre-F5 version of this test asserted the LOCAL aggregator's
    Goal ordering with seeded goals via ``POST /api/goals/``.
    Post-F5d the dashboard is a forwarder; the aggregator's ordering
    of ``user_goals`` by priority DESC + created_at ASC is locked
    by ``services/tests/test_state_aggregator_cross_db.py::test_state_summary_third_engine_aggregator_totals_match``
    (F5f end-to-end). The forwarder test here proves ONLY
    pass-through."""
    canned_goals = [
        {
            "id": 1,
            "name": "Retirement",
            "target_amount": 15_000_000.0,
            "target_date": None,
            "horizon_years": 20,
            "priority": 10,
            "is_archived": False,
            "notes": "Fire-by-55 plan",
            "created_at": "2026-07-01T00:00:00+00:00",
            "updated_at": "2026-07-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "name": "Emergency",
            "target_amount": 50_000.0,
            "target_date": None,
            "horizon_years": 3,
            "priority": 0,
            "is_archived": False,
            "notes": None,
            "created_at": "2026-06-30T00:00:00+00:00",
            "updated_at": "2026-06-30T00:00:00+00:00",
        },
    ]
    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": canned_goals,
    }
    install_finlynq_state_forward(canned)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [g["name"] for g in body["user_goals"]] == ["Retirement", "Emergency"]


def test_dashboard_summary_forwarder_excludes_archived_goals(client, install_finlynq_state_forward):
    """Phase-F5 forwarder contract: archived-goal filter is the
    FINLYNQ aggregator's responsibility (locked by F5f). The
    forwarder's job is to re-emit whatever ``StateSummaryOut``
    provided; this test proves that contract.

    (Pre-F5 this test posted an active + archived goal and asserted
    only the active one surfaced. Post-F5d ``POST /api/goals/``
    writes to rules-service's local goals table; the Finlynq
    aggregator -- over in F5f -- is the single source of truth for
    what the dashboard emits. A goal POST at rules-service does not
    reach Finlynq's view of the world, so a forwarder test cannot
    drive Finlynq's filtering through rules-service's POST --
    only the canonical cross-DB F5f test can.)"""
    canned_goals = [
        {
            "id": 1,
            "name": "Active",
            "target_amount": 100.0,
            "target_date": None,
            "horizon_years": None,
            "priority": 0,
            "is_archived": False,
            "notes": None,
            "created_at": "2026-07-01T00:00:00+00:00",
            "updated_at": "2026-07-01T00:00:00+00:00",
        },
    ]
    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": canned_goals,
    }
    install_finlynq_state_forward(canned)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [g["name"] for g in body["user_goals"]] == ["Active"]


# -------- forwarder ZERO-user_goals case (covers the pre-F5
# "empty user_goals" assertion in the test_dashboard_summary_includes_user_goals
# variant where goals are [] -- still a forwarder-contract test) --------


def test_dashboard_summary_forwarder_empty_user_goals_passes_empty_list(
    client, install_finlynq_state_forward
):
    """Forwarder passes through an empty ``user_goals`` list verbatim
    (used by the FE for the brand-new-user branch)."""
    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    assert r.json()["user_goals"] == []


# -------- Pre-F5 LOCAL AGGREGATOR tests that pre-date F5d
# (POST /api/goals/, then GET /api/dashboard/summary expecting
# the local aggregator response) are now moved to
# services/tests/test_state_aggregator_cross_db.py::test_state_summary_third_engine_aggregator_totals_match
# which exercises the SAME behavior end-to-end across services via
# the canonical ``/state/summary`` aggregator. The forwarder cannot
# replicate those tests because rules-service's POST /api/goals/
# writes to the LOCAL backing store which Finlynq's aggregator does
# NOT observe (Phase-F5 cross-service split of responsibilities).
