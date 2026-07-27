"""Phase 7 auth-route tests — devlogin + logout + production lockdown.

Tests pin the contract that the Next.js UI relies on:

1. POST /api/auth/devlogin returns a JWT-cookie for settings.local_user
   + a JSON body containing the raw token. UNCONDITIONALLY available in
   non-production environments.
2. POST /api/auth/devlogin returns 403 in production environments \u2014
   the local-first dev token contract is unsafe for public-internet
   deployments.
3. POST /api/auth/logout always succeeds (idempotent) and clears the
   ``fc_session`` cookie via Set-Cookie headers.
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


def test_devlogin_returns_token_and_cookie_in_dev(client):
    """dev environment (ENVIRONMENT=development, set by conftest.py) \u2192
    devlogin succeeds + sets fc_session cookie + returns a usable JWT."""
    r = client.post("/api/auth/devlogin")
    assert r.status_code == 200, f"unexpected {r.status_code}: {r.text}"
    body = r.json()
    assert "token" in body
    assert len(body["token"]) > 50  # HS256 token ~= 200+ chars
    assert body["subject"] == "alex"  # conftest sets LOCAL_USER=alex
    set_cookie_header = r.headers.get("set-cookie", "")
    assert "fc_session=" in set_cookie_header


def test_devlogin_with_sub_override_returns_token_for_that_subject(client):
    """devlogin accepts ?sub= override so the UI can render personalised
    dev sessions (e.g. testing multi-user flows in development)."""
    r = client.post("/api/auth/devlogin?sub=casey")
    assert r.status_code == 200
    body = r.json()
    assert body["subject"] == "casey"


def test_devlogin_refuses_in_production(client, monkeypatch):
    """``settings.environment == 'production'`` \u2192 devlogin returns 403.

    Critical: conftest.py direct-assigns ``os.environ["ENVIRONMENT"] =
    'development'`` at module load; ``monkeypatch.setenv('ENVIRONMENT',
    'production')`` doesn't propagate to the in-process ``settings``
    singleton (module-level-frozen at import time). So we patch the
    singleton attribute directly via ``monkeypatch.setattr`` \u2014 the
    only way to flip the live-settings environment without
    re-importing the module."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    # The Pydantic validators re-run at every Settings() construction,
    # but the route reads the module-level singleton (``from app.config
    # import settings``). Patching the singleton's attribute is the only
    # way to flip the in-process route's environment read.
    monkeypatch.setattr("app.config.settings.environment", "production", raising=False)

    # Sanity check the patch took effect.
    from app.config import settings as live_settings
    assert live_settings.environment == "production"

    r = client.post("/api/auth/devlogin")
    assert r.status_code == 403, (
        f"Production-environment lockdown failed: devlogin returned "
        f"{r.status_code} (expected 403). Response body: {r.text}"
    )
    detail = str(r.json().get("detail", "")).lower()
    assert "production" in detail or "disabled" in detail


def test_logout_clears_cookie(client):
    """``/api/auth/logout`` returns 200 + a Set-Cookie header that
    expires ``fc_session``. Idempotent: calling twice still returns 200."""
    r1 = client.post("/api/auth/logout")
    assert r1.status_code == 200
    r2 = client.post("/api/auth/logout")
    assert r2.status_code == 200
    set_cookie_header = r2.headers.get("set-cookie", "")
    assert "fc_session=" in set_cookie_header
