"""Phase 6 route tests — /api/profile/ (users).

Phase 6 update: the auth contract is now enforced via Depends(require_user).
The "unauthed request returns sane status" sentinel (formerly a soft
allowance for the Phase 4 lenient state) now asserts the EXPECTED 401 \u2014 the
Phase 4 comment that said "Phase 6 will swap to Depends(require_user). This
test pins the CURRENT (lenient) state..." has now materialised, and the
test pins the EXPECTED new state.
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


def test_get_profile_creates_default_row_returns_alex(client):
    """GET ``/api/profile/`` on a fresh DB seeds the Alex user row + returns it.

    Tight assertions: verifies the response shape (id key + value type),
    the right user was returned (matches ``LOCAL_USER``), and the schema
    defaults are populated. Catches regressions in: response model, user
    seeding logic, schema default values.
    """
    # Schema field is `id` (not `user_id`) — see `UserProfileResponse` in
    # `app/schemas/__init__.py`. `currency_preference` defaults to "USD"
    # in the schema definition; we mirror that here so the test still
    # catches a Phase 6 default drift.
    r = client.get("/api/profile/")

    assert r.status_code == 200, (
        f"auth should pass for the test fixture's JWT cookie; got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert isinstance(body["id"], int)
    assert body["email"] == "alex"  # LOCAL_USER default
    assert body["full_name"] == "Alex"
    assert body["currency_preference"] == "USD"  # schema default


def test_update_profile_then_get_returns_changes(client):
    """PUT ``/api/profile/`` then GET — round-trips the patch."""
    r = client.put(
        "/api/profile/",
        json={
            "full_name": "Alex Phase 6",
            "goals": "single-user test",
            "risk_profile": "aggressive",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "Alex Phase 6"
    assert body["goals"] == "single-user test"
    assert body["risk_profile"] == "aggressive"

    # Re-fetch and confirm persistence.
    r = client.get("/api/profile/")
    assert r.json()["full_name"] == "Alex Phase 6"


def test_unauthed_request_returns_401(client):
    """Phase 6 expected-state: requests WITHOUT a valid JWT cookie
    return HTTP 401 (Unauthorized). Phase 4 deferred this; Phase 6
    enforces it via ``Depends(require_user)`` on every /api/profile/
    endpoint. The test is a sentinel \u2014 if this flips back to 200 the
    reviewer/Phase 7 introduces a SECURITY REGRESSION.
    """
    from fastapi.testclient import TestClient

    unauth = TestClient(client.app)  # no Cookie header
    r = unauth.get("/api/profile/")
    assert r.status_code == 401, (
        f"Phase 6 expects 401 for missing/invalid JWT cookie; "
        f"got {r.status_code} \u2014 a regression from Phase 6 auth-tightening has been introduced. "
        f"Response body: {r.text}"
    )


def test_unauthed_put_also_returns_401(client):
    """PUT is also Phase 6-protected \u2014 sentinel for symmetry."""
    from fastapi.testclient import TestClient

    unauth = TestClient(client.app)  # no Cookie header
    r = unauth.put("/api/profile/", json={"full_name": "sneaky"})
    assert r.status_code == 401, (
        f"Phase 6 expects 401 for unauthenticated PUT; got {r.status_code}"
    )


def test_invalid_cookie_subject_returns_401(client):
    """A cookie whose ``sub`` claim does NOT match ``settings.local_user``
    is rejected with 401 (Phase 6 hardening)."""
    from fastapi.testclient import TestClient
    from app.auth import issue_token

    # Issue a token for a different subject — NOT settings.local_user.
    bad_token = issue_token("not-alex")
    bad_client = TestClient(client.app)
    bad_client.headers["Cookie"] = f"fc_session={bad_token}"

    r = bad_client.get("/api/profile/")
    assert r.status_code == 401, (
        f"Phase 6 expects 401 for wrong-subject token; got {r.status_code}"
    )


def test_expired_cookie_returns_401(client):
    """A token whose ``exp`` claim is in the past is rejected with 401.
    Mints a token manually with exp=now-1h so we don't have to wait."""
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from jose import jwt

    expired_payload = {
        "iss": "Finance Copilot",
        "sub": "alex",
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
    }
    # Settings pulls jwt_secret at import time; the conftest sets the
    # pytest override so we use it directly.
    from app.config import settings
    expired_token = jwt.encode(
        expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    bad_client = TestClient(client.app)
    bad_client.headers["Cookie"] = f"fc_session={expired_token}"

    r = bad_client.get("/api/profile/")
    assert r.status_code == 401, (
        f"Phase 6 expects 401 for expired token; got {r.status_code}"
    )


def test_bogus_signature_returns_401(client):
    """A token signed with the WRONG secret is rejected with 401 (sign
    with one secret, verify with the real settings.jwt_secret)."""
    from fastapi.testclient import TestClient
    from jose import jwt
    from datetime import datetime, timedelta, timezone

    payload = {
        "iss": "Finance Copilot",
        "sub": "alex",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    bad_token = jwt.encode(payload, "wrong-secret-totally-not-the-real-one", algorithm="HS256")
    bad_client = TestClient(client.app)
    bad_client.headers["Cookie"] = f"fc_session={bad_token}"

    r = bad_client.get("/api/profile/")
    assert r.status_code == 401, (
        f"Phase 6 expects 401 for wrong-signature token; got {r.status_code}"
    )


def test_update_profile_can_change_email_under_local_user_sub_identity(client):
    """Phase 7 invariant: ``email`` is now display-only, NOT the identity
    key. The identity key is ``local_user_sub`` (the JWT ``sub`` claim).
    Once the lookup moved off ``email``, putting a new email through the
    profile endpoint is safe (no row fork) and is in fact the WHOLE POINT
    of Phase 7 — the Settings page exists to let the user set their real
    email. This test pins the inverted Phase-7 semantics: PUTting an
    ``email`` field on the profile round-trips through, but a subsequent
    lookup returns the SAME row (Phase-7 invariant).

    Round-1 draft of this test asserted the OPPOSITE (``email`` MUST NOT
    change). That draft was written against the Round-1 blacklist which
    silently dropped ``email``. Round 2 replaced the blacklist with a
    whitelist derived from ``UserProfileCreate.model_fields.keys()``, which
    DOES include ``email`` (display-only), so PUT now mutates ``email``
    correctly — and a parallel test guards that ``local_user_sub``/``id``
    are still dropped because they are NOT in the Pydantic schema.
    """
    from app.database import SessionLocal
    from app.models import User

    # Seed the local user.
    seed = client.get("/api/profile/")
    assert seed.status_code == 200
    original_id = seed.json()["id"]
    original_email = seed.json()["email"]

    new_email = "phase7-vijay@new-domain.example.com"
    payload = {
        "full_name": "Vijay Phase 7",
        "email": new_email,
        "currency_preference": "USD",
    }
    r = client.put("/api/profile/", json=payload)
    assert r.status_code == 200, f"PUT unexpectedly failed: {r.text}"
    body = r.json()
    # Phase 7: email IS mutable (display-only).
    assert body["email"] == new_email, (
        f"Phase 7: PUT should round-trip a new email, but the response "
        f"shows email={body['email']!r} (expected {new_email!r})."
    )
    assert body["full_name"] == "Vijay Phase 7"
    # Phase 7 invariant: the identity lookup must still return the SAME
    # row despite the email flip. If the lookup key were still ``email``
    # the next call would silently create a SECOND row.
    assert body["id"] == original_id, (
        f"Phase 7 invariant violated: email flip caused the row id to "
        f"change (was {original_id}, now {body['id']})."
    )

    # Confirm persistence + invariant from a fresh request.
    s = SessionLocal()
    try:
        rows = s.query(User).filter(User.local_user_sub == "alex").all()
        assert len(rows) == 1, (
            f"Phase 7 invariant violated: expected 1 row keyed by "
            f"local_user_sub='alex', found {len(rows)}."
        )
        assert rows[0].id == original_id
        assert rows[0].email == new_email
    finally:
        s.close()


def test_update_profile_does_not_change_local_user_sub(client):
    """Phase 7: ``local_user_sub`` is the new identity key (Phase 7+
    schema). The whitelist (``UserProfileCreate.model_fields.keys()``)
    does NOT include ``local_user_sub``, so PUTting a payload that
    contains ``local_user_sub`` is silently dropped — the user-visible
    identity stays locked to ``settings.local_user``.
    """
    from app.database import SessionLocal
    from app.models import User

    # Seed the local user.
    seed = client.get("/api/profile/")
    assert seed.status_code == 200
    original_id = seed.json()["id"]

    r = client.put(
        "/api/profile/",
        json={"full_name": "X", "local_user_sub": "rogue"},
    )
    assert r.status_code == 200, f"PUT unexpectedly failed: {r.text}"

    s = SessionLocal()
    try:
        u = s.query(User).filter(User.local_user_sub == "alex").one()
        assert u is not None
        assert u.id == original_id
        # Confirm the rogue sub-never took.
        rogue = s.query(User).filter(User.local_user_sub == "rogue").all()
        assert rogue == [], (
            f"Phase 7 invariant violated: a PUT containing "
            f"``local_user_sub='rogue'`` produced a row: {rogue}"
        )
        # Confirm the legitimate mutable field DID apply.
        assert u.full_name == "X"
    finally:
        s.close()


def test_update_profile_ignores_identity_and_security_fields(client):
    """Phase 7 security guard: PUT a payload containing BOTH identity keys
    (``local_user_sub``, ``id``) and security-sensitive columns
    (``is_active``, ``hashed_password``, ``goals``) — only the fields
    declared in ``UserProfileCreate`` (the explicit profile-edit contract)
    must mutate, every other field is silently dropped.

    Without this guard, a malicious or buggy client could:
      * reset the identity key via ``local_user_sub``,
      * overwrite another user's row via ``id``,
      * disable the account via ``is_active=False``,
      * corrupt auth via ``hashed_password`` (the JWT-cookie path does
        not hash a password, but the column exists for Phase 2 parity).
    """
    from app.database import SessionLocal
    from app.models import User

    # Seed the local user.
    seed = client.get("/api/profile/")
    assert seed.status_code == 200
    original_id = seed.json()["id"]
    original_local_user_sub = "alex"

    payload = {
        # Legitimate mutable fields (UserProfileCreate-declared):
        "full_name": "Whitelisted",
        "currency_preference": "EUR",
        # Identity-bearing (must be dropped):
        "local_user_sub": "hacker",
        "id": 9999,
        # Security-sensitive (must be dropped):
        "is_active": False,
        "hashed_password": "rotated",
    }
    r = client.put("/api/profile/", json=payload)
    assert r.status_code == 200, f"PUT unexpectedly failed: {r.text}"
    body = r.json()
    assert body["full_name"] == "Whitelisted"
    assert body["currency_preference"] == "EUR"
    assert body["id"] == original_id, (
        "PUT must NOT honour a client-supplied ``id``; the whitelist "
        "filters it because ``id`` is not declared in UserProfileCreate."
    )

    # Authoritative DB check.
    s = SessionLocal()
    try:
        u = s.query(User).one()
        assert u.local_user_sub == original_local_user_sub
        assert u.is_active is True, (
            "Phase 7: ``is_active`` is NOT in UserProfileCreate; the "
            "whitelist silently dropped the malicious payload."
        )
        assert u.hashed_password != "rotated"
    finally:
        s.close()


def test_update_profile_full_name_syncs_self_family_member(client, db_session):
    """Phase 54+ — when the user renames themselves via Settings, the
    Self family member's name must update too. Without this sync, the
    Accounts page (which renders FamilyMember.name) would show the
    stale "Alex" forever after a Settings rename.
    """
    from app.models import FamilyMember, User

    # Seed the local user + Self family member via GET.
    seed = client.get("/api/profile/")
    assert seed.status_code == 200
    assert seed.json()["full_name"] == "Alex"

    # Verify the Self member starts with "Alex" via the API.
    r0 = client.get("/api/family-members/")
    assert r0.status_code == 200
    members_before = r0.json()
    self_before = next((m for m in members_before if m["is_self"]), None)
    assert self_before is not None, "Self member should exist after profile GET"
    assert self_before["name"] == "Alex", (
        f"Self member should start as 'Alex'; got {self_before['name']!r}"
    )

    # Rename via Settings.
    r = client.put("/api/profile/", json={"full_name": "Vijay"})
    assert r.status_code == 200, f"PUT failed: {r.text}"
    assert r.json()["full_name"] == "Vijay"

    # Verify the Self member name was synced via the API.
    r2 = client.get("/api/family-members/")
    assert r2.status_code == 200
    members_after = r2.json()
    self_after = next((m for m in members_after if m["is_self"]), None)
    assert self_after is not None, "Self member should still exist"
    assert self_after["name"] == "Vijay", (
        f"Self member name must sync to 'Vijay' after profile rename; "
        f"got {self_after['name']!r}"
    )

    # Authoritative DB check via the shared db_session fixture.
    user = db_session.query(User).filter(User.local_user_sub == "alex").one()
    self_fm = db_session.query(FamilyMember).filter(
        FamilyMember.user_id == user.id,
        FamilyMember.is_self.is_(True),
    ).one()
    assert self_fm.name == "Vijay", (
        f"DB-level Self member name must be 'Vijay'; got {self_fm.name!r}"
    )


def test_get_or_create_uses_local_user_sub_after_email_change():
    """Phase 7 invariant: even if the row's ``email`` mutates, the
    identity-keyed lookup returns the same row. This is the
    precondition that prevents the original duplicate-user bug -- a
    prior ``PUT`` that changed the email used to break the next
    ``get_or_create_local_user`` lookup and silently created a second
    row.
    """
    import sqlalchemy as sa
    from app.database import SessionLocal
    from app.routes.shared import get_or_create_local_user

    s = SessionLocal()
    try:
        u1 = get_or_create_local_user(s, "alex")
        # Mutate email out from under the identity column.
        s.execute(
            sa.text("UPDATE users SET email = 'changed@example.com' WHERE id = :i"),
            {"i": u1.id},
        )
        s.commit()

        u2 = get_or_create_local_user(s, "alex")
        assert u2.id == u1.id, (
            "Phase 7 invariant violated: a mutate-the-email-then-look-up "
            "sequence forked the user row (got a NEW id instead of the "
            f"original -- id1={u1.id} id2={u2.id})."
        )
        assert u2.email == "changed@example.com"
    finally:
        s.close()
