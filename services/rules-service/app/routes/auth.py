"""Phase 7 auth route — local-only dev login.

``POST /api/auth/devlogin`` issues a JWT cookie for
``settings.local_user`` (or a ``sub`` query/body override) WHEN
``settings.environment != "production"`` \u2014 in production the route
returns 403 because the local-first dev token contract is unsafe for
public-internet deployments.

The lift follows the same single-user JWT-cookie auth model used by the
rest of the service; see ``docs/wealthiq-merge-plan.md`` \u00a710 decision 4
and ``app/auth.py``. The devlogin endpoint exists ONLY for the local
Next.js UI to bootstrap its session on cold start \u2014 the curl/test
clients use ``app.auth.issue_token`` directly.

Security posture:

- Refuses the request in production (``environment == ``productions``),
  regardless of who's calling. Phase 8 (out of scope) flips this to a
  real OAuth flow with a user database if multi-user is ever wanted.
- Issues a JWT-aligned-with-app.auth's contracts: same HS256 algorithm,
  same ``iss`` claim + ``sub`` validation, same ``exp`` window.
- Sets the cookie via SetCookie headers the SAME WAY as the rest of the
  service so the UI's axios call + browser cookie jar round-trip works
  on ``httpOnly; SameSite=Lax`` defaults.

Endpoints:

- ``POST /api/auth/devlogin`` (with optional ``sub`` query param):
  returns ``{"token": "..."} `` and sets the ``fc_session`` cookie.
- ``POST /api/auth/logout``: clears the ``fc_session`` cookie (no-op
  on the server, the cookie is the source of truth).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.auth import clear_auth_cookie, issue_token, set_auth_cookie
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _ensure_not_production() -> None:
    """Refuse ``/api/auth/devlogin`` in production environments."""
    if settings.environment.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="dev login is disabled in production environments",
        )


@router.post("/devlogin")
async def devlogin(
    response: Response,
    sub: Optional[str] = Query(
        default=None,
        description="Optional subject override; defaults to settings.local_user.",
    ),
):
    """Mint a JWT for ``sub`` (or settings.local_user) and set the
    ``fc_session`` cookie + return the raw token in the body. Phase 7
    contract: in non-production environments, this endpoint is how the
    UI's first cold-start call bootstraps the session."""
    _ensure_not_production()
    token = issue_token(username=sub)
    set_auth_cookie(response, token)
    return {"token": token, "subject": sub or settings.local_user}


@router.post("/logout")
async def logout(response: Response):
    """Clear the ``fc_session`` cookie. Idempotent; safe to call even
    if no cookie was set."""
    clear_auth_cookie(response)
    return {"logged_out": True}
