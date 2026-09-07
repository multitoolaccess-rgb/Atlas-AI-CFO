from __future__ import annotations

"""Single-user local-first authentication helper.

...

"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, get_db
from app.models import User

COOKIE_NAME = "fc_session"


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


async def get_current_user(
    fc_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Resolve the current user from cookie or Bearer header; else 401.

    Returns the ``local_user_sub`` identity string (e.g. ``"alex"``) — the
    original Phase-7 contract. Do NOT change this return type: legacy routes
    pass the value straight into ``get_or_create_local_user(db, sub)`` and
    similar helpers. Routes that need the integer ``users.id`` should depend
    on :func:`get_current_user_id` instead.
    """
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


async def get_current_user_id(
    user_sub: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> int:
    """Resolve the authenticated identity string to its integer ``users.id``."""
    user = db.query(User).filter(User.local_user_sub == user_sub).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found",
        )
    return user.id


# Common alias used by protected routes — STRING identity contract.
require_user = get_current_user
# Integer-ID variant for routes that query ``*.user_id`` columns directly.
require_user_id = get_current_user_id