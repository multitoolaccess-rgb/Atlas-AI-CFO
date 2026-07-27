"""Single-user local-first authentication helper.

Built (no wealthiq source — wealthiq has no auth file; its ``routes/shared.py``
"gets or creates" a demo user on every request) per ``docs/wealthiq-merge-plan.md``
§10 decision 4: **single-user JWT-as-cookie**.

Contract:

- Exactly one user (default ``alex``; override via ``LOCAL_USER`` env).
- The user proves possession by presenting a valid HS256 JWT signed with
  ``settings.jwt_secret``.
- The token may travel in a cookie (``fc_session``) **OR** as an
  ``Authorization: Bearer <token>`` header (CLI/test client convenience).
- The ``sub`` claim must equal ``settings.local_user``. Tokens issued for a
  previous ``local_user`` are rejected after a rename — by design, this is
  safer than silently accepting them.

Usage:

- ``issue_token()``                            – mint a fresh token in tests.
- ``verify_token(token)``                      – decode a token or raise 401.
- ``get_current_user(...)``                    – FastAPI dependency; returns
                                                ``settings.local_user``.
- ``set_auth_cookie(response, token)``         – attach the cookie on login.
- ``clear_auth_cookie(response)``              – invalidate the cookie on logout.

Tokens are time-boxed via ``settings.jwt_expiration_hours`` (default 24h). No
persistent user table; the identity contract is the signed token, full stop.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Response, status
from jose import JWTError, jwt

from app.config import settings

COOKIE_NAME = "fc_session"


# --- Token mint / verify ---------------------------------------------------


def issue_token(username: Optional[str] = None) -> str:
    """Sign a JWT for ``username`` (defaults to ``settings.local_user``)."""
    sub = username or settings.local_user
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=settings.jwt_expiration_hours)
    payload = {
        "iss": settings.app_name,             # tie the token to this app
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict:
    """Decode ``token``; raise 401 on bad signature, expiry, wrong subject, or wrong issuer.

    Hardening raised by Phase 2 code-review:

    - ``iss`` claim set on encode and matched on decode — prevents a token minted
      by some other HS256 secret-holder from being accepted if our secret leaks.
    - ``leeway=10`` (seconds) so issuer/verifier clock drift doesn't reject
      otherwise valid tokens. python-jose default is 0, which is too strict.
    """
    try:
        # python-jose 3.3.0 puts `leeway` INSIDE the `options` dict, NOT as a
        # top-level kwarg. A direct `leeway=10` raises TypeError on first call.
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"leeway": 10},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {e}",
        )
    if payload.get("iss") != settings.app_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token issuer mismatch",
        )
    sub = payload.get("sub")
    if sub != settings.local_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token subject mismatch",
        )
    return payload


# --- Cookie helpers ---------------------------------------------------------


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the session cookie to ``response`` (HttpOnly; SameSite=Lax)."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.jwt_expiration_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Invalidate the session cookie on ``response``."""
    response.delete_cookie(key=COOKIE_NAME, path="/")


# --- FastAPI dependency -----------------------------------------------------


async def get_current_user(
    fc_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Resolve the current user from cookie or Bearer header; else 401."""
    token = fc_session
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    payload = verify_token(token)
    return payload["sub"]


# Common alias used by protected routes / dep ``Depends(require_user)``.
require_user = get_current_user
