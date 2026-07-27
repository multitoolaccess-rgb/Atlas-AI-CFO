"""Family Members route tests — ``/api/family-members/`` CRUD (auth-enforced).

Mirrors the Goal/Account test shape so the suite reads uniformly across
resources:

- list-auto-seeds-self / create / create-invalid-color-422 / create-empty-name-400
- get-by-id / get-missing-404
- update-partial / update-missing-404
- archive soft-deletes / archive is idempotent / archive missing-404
- archive-self-400 / archive-with-active-accounts-409
- account-create-defaults-to-self / account-update-changes-family-member
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# -------- list --------


def test_list_family_members_auto_seeds_self(client, db_session):
    """Brand-new DB: GET /api/family-members/ returns the bootstrapped
    Self row (idempotent across calls).

    The auto-seed fence uses ``is_self`` (fast column-level check)
    rather than a name-string lookup. The Self row's color is the
    canonical emerald #10b981 chip on the FE.
    """
    r = client.get("/api/family-members/")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1, f"expected exactly Self row; got {rows!r}"
    self_row = rows[0]
    assert self_row["is_self"] is True
    assert self_row["is_archived"] is False
    assert self_row["color"] == "#10b981"
    seed_id = self_row["id"]

    # Idempotent: a second GET returns the same id (no second seed).
    rows2 = client.get("/api/family-members/").json()
    assert len(rows2) == 1
    assert rows2[0]["id"] == seed_id


def test_list_family_members_excludes_archived(client):
    """After a manual member is archived, list_family_members stops
    returning it (Self is always preserved)."""
    created = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    assert created["is_archived"] is False

    before = client.get("/api/family-members/").json()
    before_ids = {r["id"] for r in before}
    assert created["id"] in before_ids

    # Archive via DELETE
    assert client.delete(f"/api/family-members/{created['id']}").status_code == 204

    after = client.get("/api/family-members/").json()
    after_ids = {r["id"] for r in after}
    assert created["id"] not in after_ids
    # Self remains
    assert any(r["is_self"] for r in after)


# -------- create --------


def test_create_family_member_returns_201_with_self_lock(client):
    """POST /api/family-members/ creates a row. name + color required."""
    r = client.post(
        "/api/family-members/",
        json={"name": "Kid", "color": "#f59e0b"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "Kid"
    assert created["color"] == "#f59e0b"
    assert created["is_self"] is False  # Self is bootstrapped, not POSTable
    assert created["is_archived"] is False


def test_create_family_member_invalid_hex_color_returns_422(client):
    """Pydantic ``Field(pattern=...)`` rejects non-hex colors with 422.

    Two failures exercise the regex: a value without ``#``, and a value
    that begins with ``#`` but has the wrong length.
    """
    for bad in ["10b981", "#FFGGGG", "#1a2", "rgb(0,0,0)", "#10b981cc"]:
        r = client.post(
            "/api/family-members/",
            json={"name": "Bad Color", "color": bad},
        )
        assert r.status_code == 422, (
            f"color={bad!r} should be 422; got {r.status_code} {r.text}"
        )


def test_create_family_member_empty_name_returns_400(client):
    """Defensive regression — empty/blank name would break the FE chip."""
    for bad in ["", "   "]:
        r = client.post(
            "/api/family-members/",
            json={"name": bad, "color": "#10b981"},
        )
        assert r.status_code == 400, (
            f"name={bad!r} should be 400; got {r.status_code} {r.text}"
        )


def test_create_family_member_duplicate_name_returns_409(client):
    """UNIQUE (user_id, name) — a second POST with same name 409s
    via the global IntegrityError handler in app.main."""
    client.post(
        "/api/family-members/",
        json={"name": "Duplicate", "color": "#3b82f6"},
    )
    r = client.post(
        "/api/family-members/",
        json={"name": "Duplicate", "color": "#f59e0b"},
    )
    assert r.status_code == 409, r.text
    assert "already exists" in r.json()["detail"].lower()


# -------- get-by-id --------


def test_get_family_member_by_id_returns_row(client):
    """POST then GET /api/family-members/{id} returns the row."""
    created = client.post(
        "/api/family-members/",
        json={"name": "Grandparent", "color": "#10b981"},
    ).json()
    r = client.get(f"/api/family-members/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Grandparent"


def test_get_family_member_missing_returns_404(client):
    """GET on a non-existent member id returns 404."""
    r = client.get("/api/family-members/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Family member not found"


# -------- update --------


def test_update_family_member_partial_renames_and_recolors(client):
    """PUT mutates only declared fields (color + name + is_archived)."""
    created = client.post(
        "/api/family-members/",
        json={"name": "Original", "color": "#3b82f6"},
    ).json()
    r = client.put(
        f"/api/family-members/{created['id']}",
        json={"name": "Renamed", "color": "#f59e0b"},
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["name"] == "Renamed"
    assert updated["color"] == "#f59e0b"
    assert updated["is_self"] is False


def test_update_family_member_cannot_become_self(client):
    """The PUT whitelist does NOT include ``is_self`` — clients cannot
    promote an arbitrary member to Self. Even if the wire payload
    includes it, Pydantic silently drops unknown keys via ``model_dump()``.
    """
    created = client.post(
        "/api/family-members/",
        json={"name": "Kid", "color": "#3b82f6"},
    ).json()
    assert created["is_self"] is False
    r = client.put(
        f"/api/family-members/{created['id']}",
        json={"name": "Kid", "color": "#f59e0b", "is_self": True},
    )
    assert r.status_code == 200, r.text
    # The bogus `is_self=True` was dropped by Pydantic — still False.
    assert r.json()["is_self"] is False


def test_update_family_member_missing_returns_404(client):
    """PUT on a non-existent member id returns 404."""
    r = client.put("/api/family-members/99999", json={"name": "X"})
    assert r.status_code == 404


# -------- archive --------


def test_archive_family_member_soft_deletes_via_is_archived(client):
    """DELETE flips ``is_archived=True``; list filters it but row stays
    in DB so a future FK-bearing reference (e.g. transaction snapshot)
    resolves.

    Phase 16: the list endpoint ALWAYS includes the per-user Self row
    (the lazy-seed branch in ``list_family_members`` guarantees it),
    so after archiving a non-Self member the list returns ``[Self]``
    — NOT ``[]``. Sibling test
    ``test_list_family_members_excludes_archived`` covers the
    \"archived member absent\" branch; this test covers the
    \"archive action writes is_archived=True\".
    """
    created = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    assert client.delete(f"/api/family-members/{created['id']}").status_code == 204
    # Spouse is archived (not in list); Self is still listed.
    after = client.get("/api/family-members/").json()
    assert all(r["is_self"] for r in after) and created["id"] not in {r["id"] for r in after}, (
        f"After archive: list should contain only Self. got {after!r}"
    )
    r = client.get(f"/api/family-members/{created['id']}")
    assert r.status_code == 200
    assert r.json()["is_archived"] is True


def test_archive_family_member_is_idempotent(client):
    """A second DELETE on an already-archived row still returns 204."""
    created = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    assert client.delete(f"/api/family-members/{created['id']}").status_code == 204
    assert client.delete(f"/api/family-members/{created['id']}").status_code == 204


def test_archive_family_member_missing_returns_404(client):
    r = client.delete("/api/family-members/99999")
    assert r.status_code == 404


def test_archive_self_returns_400(client, db_session):
    """The Self row CANNOT be archived — every user has exactly one
    Self row, and accounts default to it. Hard 400, NOT 409.
    """
    self_id = client.get("/api/family-members/").json()[0]["id"]
    r = client.delete(f"/api/family-members/{self_id}")
    assert r.status_code == 400, r.text
    assert "self" in r.json()["detail"].lower()
    # Row is still active.
    r = client.get(f"/api/family-members/{self_id}")
    assert r.json()["is_archived"] is False


def test_archive_family_member_with_active_accounts_returns_409(
    client, make_account, db_session
):
    """Archiving a member with >=1 active account 409s with a detail
    message. Same semantics as Goal's archive (preserves FK integrity).

    SETUP: create one active account assigned to a non-Self member.
    EXPECT: DELETE on that member returns 409.
    """
    spouse = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    # Pre-create an active account on the spouse member (via the BE route)
    r = client.post(
        "/api/accounts/",
        json={
            "account_name": "Joint Checking",
            "account_type": "checking",
            "institution_name": "Joint Bank",
            "current_balance": 100.0,
            "family_member_id": spouse["id"],
        },
    )
    assert r.status_code == 201, r.text
    # Archive attempt — spouse has 1 active account.
    r = client.delete(f"/api/family-members/{spouse['id']}")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"].lower()
    assert "active" in detail
    assert "1" in detail or "joint" in detail


def test_archive_family_member_with_only_inactive_accounts_succeeds(
    client, make_account
):
    """If every account on a member is already soft-deleted
    (``is_active=False``), the archive succeeds because no active FK
    would be orphaned."""
    spouse = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    created = client.post(
        "/api/accounts/",
        json={
            "account_name": "Old Joint",
            "account_type": "checking",
            "institution_name": "Old Bank",
            "current_balance": 0.0,
            "family_member_id": spouse["id"],
        },
    ).json()
    # Soft-delete the account first.
    assert client.delete(f"/api/accounts/{created['id']}").status_code == 204
    # Now archive the member — no active FK references.
    assert client.delete(f"/api/family-members/{spouse['id']}").status_code == 204


# -------- account ↔ family member wiring --------


def test_create_account_defaults_to_self_when_family_member_id_omitted(
    client, db_session
):
    """POST /api/accounts/ with no ``family_member_id`` should auto-default
    to the local user's Self row. The Self row is bootstrapped by
    list_family_members' first call (or by get_or_create_local_user)."""
    self_id = client.get("/api/family-members/").json()[0]["id"]
    created = client.post(
        "/api/accounts/",
        json={
            "account_name": "No-Member",
            "account_type": "checking",
            "institution_name": "Auto Bank",
            "current_balance": 0.0,
        },
    ).json()
    # Family member id is on the response — confirm Self fell through.
    r = client.get(f"/api/accounts/{created['id']}")
    assert r.json()["family_member_id"] == self_id


def test_create_account_with_explicit_family_member_id(client):
    """POST /api/accounts/ with ``family_member_id`` honors it
    (the FE accounts page dropdown uses this path)."""
    spouse = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    created = client.post(
        "/api/accounts/",
        json={
            "account_name": "Spouse Checking",
            "account_type": "checking",
            "institution_name": "Spouse Bank",
            "current_balance": 100.0,
            "family_member_id": spouse["id"],
        },
    ).json()
    r = client.get(f"/api/accounts/{created['id']}")
    assert r.json()["family_member_id"] == spouse["id"]


def test_update_account_reassigns_family_member(client):
    """PUT /api/accounts/{id} with a new ``family_member_id`` flips
    the membership."""
    spouse = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    self_id = client.get("/api/family-members/").json()[0]["id"]
    created = client.post(
        "/api/accounts/",
        json={
            "account_name": "Transferred",
            "account_type": "checking",
            "institution_name": "Transfer Bank",
            "current_balance": 200.0,
        },
    ).json()
    assert created["family_member_id"] == self_id
    r = client.put(
        f"/api/accounts/{created['id']}",
        json={"family_member_id": spouse["id"]},
    )
    assert r.status_code == 200
    # GET-by-id confirms the membership flipped.
    r = client.get(f"/api/accounts/{created['id']}")
    assert r.json()["family_member_id"] == spouse["id"]


# -------- Phase 16+ household profile (relationship / working_status / age) --------


def test_self_row_relationship_backfilled_to_self_on_bootstrap(client):
    """The Self row is bootstrapped on first GET and its ``relationship``
    column is hard-coded to ``'Self'`` at insertion time. A user who
    deletes their profile fields on the FE and re-fetches sees the
    locked value, never ``null``. Defence-in-depth for the
    Self-row relationship invariant.
    """
    self_row = client.get("/api/family-members/").json()[0]
    assert self_row["is_self"] is True
    assert self_row["relationship"] == "Self"


def test_create_family_member_with_relationship_status_and_age(client):
    """POST /api/family-members/ accepts all three household-profile
    fields. The schema is permissive: any subset of
    ``[relationship, working_status, age]`` is OK. This is the
    Phase-16+ "two-click create, fill later via PUT" path.
    """
    r = client.post(
        "/api/family-members/",
        json={
            "name": "Spouse",
            "color": "#3b82f6",
            "relationship": "Spouse",
            "working_status": "Employed",
            "age": 35,
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["relationship"] == "Spouse"
    assert created["working_status"] == "Employed"
    assert created["age"] == 35
    # Self-only fields are still hardcoded.
    assert created["is_self"] is False
    assert created["is_archived"] is False


def test_create_family_member_optional_profile_fields_default_to_none(client):
    """All three household-profile fields are OPTIONAL on POST -- a
    client submitting just ``name`` + ``color`` gets back a row with
    ``relationship`` / ``working_status`` / ``age`` set to ``None``.
    This is the documented 'two-click create' pattern.
    """
    r = client.post(
        "/api/family-members/",
        json={"name": "Unfilled Spouse", "color": "#3b82f6"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["relationship"] is None
    assert created["working_status"] is None
    assert created["age"] is None


def test_create_family_member_invalid_relationship_returns_422(client):
    """A value not in the Pydantic ``Literal['Self'|'Spouse'|...]``
    enum 422s before reaching the route layer. The OpenAPI schema
    serialises the enum so the FE's <select> matches it verbatim.
    """
    r = client.post(
        "/api/family-members/",
        json={"name": "Bad", "color": "#3b82f6", "relationship": "Acquaintance"},
    )
    assert r.status_code == 422, r.text


def test_create_family_member_invalid_working_status_returns_422(client):
    """Same Literal contract for ``working_status``."""
    r = client.post(
        "/api/family-members/",
        json={"name": "Bad", "color": "#3b82f6", "working_status": "PartTime"},
    )
    assert r.status_code == 422, r.text


def test_create_family_member_negative_age_returns_422(client):
    """``age=-1`` violates ``Field(ge=0)``; 422 from Pydantic."""
    r = client.post(
        "/api/family-members/",
        json={"name": "Bad", "color": "#3b82f6", "age": -1},
    )
    assert r.status_code == 422, r.text


def test_create_family_member_over_max_age_returns_422(client):
    """``age=200`` violates ``Field(le=120)``; 422 from Pydantic. The
    120 cap is a sanity bound (Phase 18+ can loosen to 150 if a real
    household profile demands it).
    """
    r = client.post(
        "/api/family-members/",
        json={"name": "Bad", "color": "#3b82f6", "age": 200},
    )
    assert r.status_code == 422, r.text


def test_update_family_member_relationship_status_and_age(client):
    """PUT mutates the household-profile fields on a non-Self row.
    The whitelist accepts ``relationship`` / ``working_status`` /
    ``age`` exactly like the create form does.
    """
    created = client.post(
        "/api/family-members/",
        json={"name": "Spouse", "color": "#3b82f6"},
    ).json()
    assert created["relationship"] is None
    r = client.put(
        f"/api/family-members/{created['id']}",
        json={
            "relationship": "Spouse",
            "working_status": "Retired",
            "age": 70,
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["relationship"] == "Spouse"
    assert updated["working_status"] == "Retired"
    assert updated["age"] == 70


def test_update_family_member_partial_skips_unset_profile_fields(client):
    """The whitelist contract: a PUT with only ``working_status``
    DOES NOT clear the existing ``relationship`` / ``age`` columns.
    ``model_dump()`` silently drops ``None``-valued keys so an unset
    field on the wire is the same as not writing the column.
    """
    created = client.post(
        "/api/family-members/",
        json={
            "name": "Spouse",
            "color": "#3b82f6",
            "relationship": "Spouse",
            "age": 35,
        },
    ).json()
    r = client.put(
        f"/api/family-members/{created['id']}",
        json={"working_status": "Employed"},
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    # Only ``working_status`` flipped; relationship + age preserved.
    assert updated["working_status"] == "Employed"
    assert updated["relationship"] == "Spouse"
    assert updated["age"] == 35


def test_self_row_relationship_locked_on_put(client):
    """PUT on the Self row with ``relationship='Spouse'`` is silently
    force-overridden to ``'Self'`` by the route layer (defence-in-
    depth alongside the FE's disabled dropdown). The user NEVER sees
    an auto-reverted value because the BE state after the PUT is
    internally consistent.
    """
    self_id = client.get("/api/family-members/").json()[0]["id"]
    r = client.put(
        f"/api/family-members/{self_id}",
        json={
            "name": "Self Renamed",
            "color": "#22c55e",
            "relationship": "Spouse",
            "working_status": "Employed",
            "age": 40,
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["is_self"] is True
    # ``relationship`` is locked: even though the wire payload said
    # 'Spouse', the BE forces 'Self' on the canonical Self row.
    assert updated["relationship"] == "Self"
    # ``name`` / ``working_status`` / ``age`` are freely mutable
    # on the Self row -- only ``relationship`` is locked.
    assert updated["name"] == "Self Renamed"
    assert updated["working_status"] == "Employed"
    assert updated["age"] == 40
