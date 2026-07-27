"""Single-user JWT-as-cookie auth for Finlynq.

This module is a VERBATIM MIRROR of ``services/rules-service/app/auth.py``
except for the docstring. The JWT contract MUST be identical between the
two services so the ``fc_session`` cookie minted by
``POST /api/auth/devlogin`` on rules-service is accepted by Finlynq's
``Depends(require_user)`` dep without re-auth.

Why mirror and not import? ``services/finlynq`` and ``services/rules-service``
are siblings, not a parent/child. Cross-importing between siblings couples
their lifecycle (any change in rules-service app breaks Finlynq startup).
The cost of duplication is ~120 lines; the cost of cross-import is
subtle runtime breakage — duplication wins.

Cross-service invariant locked by ``tests/test_auth_contract.py`` (added in
Phase F2):
- The mint/verify paths round-trip with the SAME ``jwt_secret`` AND
  ``iss`` claim (``settings.app_name``) AND ``sub`` claim
  (``settings.local_user``).
- A token minted by rules-service is verified by Finlynq with no
  additional auth step required.

If this module drifts from rules-service's auth.py, the contract test
FAILS — fix one or the other to keep them in lockstep.
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

    Same hardening as rules-service: ``leeway=10`` for clock drift,
    ``options``-dict positional for python-jose 3.3.x.
    """
    try:
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
