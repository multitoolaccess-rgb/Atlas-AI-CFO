"""Tests for the single-user JWT-cookie auth helper.

Six contracts the helper must hold (per ``docs/wealthiq-merge-plan.md`` §10
decision 4 + §4 reuse map item 3):

1. ``issue_token()`` defaults to ``settings.local_user``.
2. ``issue_token()`` and ``verify_token()`` roundtrip losslessly.
3. ``verify_token()`` rejects garbage strings with a 401.
4. ``verify_token()`` rejects tokens signed with a different secret.
5. ``set_auth_cookie(response, token)`` attaches the ``fc_session`` cookie,
   ``HttpOnly``-marked.
6. ``clear_auth_cookie(response)`` sends a deletion (Max-Age=0).
"""
import pytest
from fastapi import HTTPException, Response
from jose import jwt as _jose_jwt

from app.auth import (
    COOKIE_NAME,
    clear_auth_cookie,
    issue_token,
    set_auth_cookie,
    verify_token,
)
from app.config import settings


def test_issue_token_default_user_matches_settings_local_user():
    """No-arg ``issue_token()`` uses ``settings.local_user`` as the ``sub``."""
    token = issue_token()
    payload = _jose_jwt.get_unverified_claims(token)
    assert payload["sub"] == settings.local_user == "alex"


def test_issue_and_verify_roundtrip():
    """Token issued → verified returns the same payload."""
    token = issue_token()
    payload = verify_token(token)
    assert payload["sub"] == settings.local_user
    # Standard claims present.
    assert "iat" in payload and "exp" in payload


def test_verify_token_rejects_garbage():
    """Non-JWT string → 401 (does not crash, does not silently succeed)."""
    with pytest.raises(HTTPException) as exc:
        verify_token("not-a-jwt")
    assert exc.value.status_code == 401


def test_verify_token_rejects_token_signed_with_different_secret(monkeypatch):
    """Rotating ``jwt_secret`` mid-flight invalidates existing tokens."""
    token = issue_token()
    monkeypatch.setattr(settings, "jwt_secret", "rotated-secret")
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401


def test_verify_token_rejects_token_for_different_local_user(monkeypatch):
    """Rotating ``local_user`` mid-flight invalidates existing tokens."""
    token = issue_token()
    monkeypatch.setattr(settings, "local_user", "casey")
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401


def test_issue_token_includes_iss_claim_matching_app_name():
    """Hardening raised by Phase 2 code-review: tokens carry an ``iss`` claim."""
    token = issue_token()
    payload = _jose_jwt.get_unverified_claims(token)
    assert payload["iss"] == settings.app_name == "Finance Copilot"


def test_verify_token_rejects_token_with_wrong_iss(monkeypatch):
    """Tokens minted against a different ``iss`` are rejected, even with valid signature."""
    token = issue_token()
    monkeypatch.setattr(settings, "app_name", "OtherApp")
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "token issuer mismatch"


def test_set_auth_cookie_attaches_httponly_cookie_in_development():
    """``set_auth_cookie`` writes a `fc_session=...` `Set-Cookie` header (HttpOnly, non-secure in dev).

    Prod-only `Secure` flag is asserted separately to avoid OR-trivially-true bugs.
    """
    r = Response()
    set_auth_cookie(r, "the-jwt-value")
    # starlette ``Response.set_cookie`` populates ``RawHeaders`` (mutable list of
    # tuples). ``headers`` proxies through; check it directly.
    set_cookie = r.headers.get("set-cookie", "")
    assert set_cookie != ""
    assert f"{COOKIE_NAME}=the-jwt-value" in set_cookie
    assert "HttpOnly" in set_cookie
    # Dev must NOT carry Secure (https-only breaks http://localhost dev loops).
    assert "Secure" not in set_cookie


def test_set_auth_cookie_marks_secure_when_environment_is_production(monkeypatch):
    """Production must carry the Secure flag; the cookie refuses to ride over plaintext."""
    monkeypatch.setattr(settings, "environment", "production")
    r = Response()
    set_auth_cookie(r, "the-jwt-value")
    set_cookie = r.headers.get("set-cookie", "")
    assert "Secure" in set_cookie, (
        "production cookie must carry Secure; "
        "otherwise plaintext HTTP would expose the session cookie"
    )


def test_clear_auth_cookie_sends_deletion():
    """``clear_auth_cookie`` sends a ``Set-Cookie`` with Max-Age=0 / Expires=...past."""
    r = Response()
    clear_auth_cookie(r)
    deletion = r.headers.get("set-cookie", "")
    assert deletion != ""
    assert COOKIE_NAME in deletion
    # starlette's ``delete_cookie`` uses ``max_age=0`` which appears as
    # ``Max-Age=0`` in the Set-Cookie header.
    assert "Max-Age=0" in deletion
