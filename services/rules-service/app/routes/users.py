"""Phase 6 lift — /api/profile/ endpoints (auth-enforced).

Lift provenance: the legacy WealthIQ user-route module (see
``docs/wealthiq-merge-plan.md`` §4 Reuse Map item 14). Three substantive changes:

- Replaced ``get_or_create_demo_user`` -> ``get_or_create_local_user(db, settings.local_user)``
  so the row key is single-user ``Alex`` (per §10 decision 4) instead of
  ``demo@example.com``.
- Phase 6: added ``Depends(require_user)`` to BOTH the GET and PUT endpoints.
  The Phase 4 comment that said ``Phase 6 will tighten`` is now realized \u2014
  the GET-then-PUT route pair enforces the JWT-cookie contract from
  this turn forward. ``app.auth.require_user`` is a FastAPI dependency
  that decodes the cookie (or Bearer header) and validates the ``sub``
  claim against ``settings.local_user``.
- ``from app.db import get_db`` \u2192 ``from app.database import get_db`` (Phase 2 rename).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import User
from app.routes.shared import get_or_create_family_member_self, get_or_create_local_user
from app.schemas import UserProfileCreate, UserProfileResponse

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/", response_model=UserProfileResponse)
async def get_profile(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Return the local user's profile. Phase 6: requires a valid JWT-cookie
    (Phase 4 said this was deferred; now enforced)."""
    user = get_or_create_local_user(db, _current_user)
    return user


@router.put("/", response_model=UserProfileResponse)
async def update_profile(
    payload: UserProfileCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Update the local user's profile. Phase 6: requires valid JWT-cookie.

    **Phase 7 — identity-key split.** The ``email``, ``local_user_sub``,
    and ``id`` columns are identity-bearing and MUST NOT be settable
    through this endpoint: ``email`` would let a Settings-page save
    detach the row from the JWT-cookie's ``sub`` claim (re-creating the
    duplicate-user bug this phase just closed), ``local_user_sub`` is
    the identity key itself, and ``id`` is the SQLAlchemy PK. Every
    other Pydantic field on ``UserProfileCreate`` is mutable.
    """
    user = get_or_create_local_user(db, _current_user)
    # Whitelist of fields the client may mutate through this endpoint.
    # Listing them EXPLICITLY (instead of blacklisting ``email``,
    # ``local_user_sub``, ``id``, ...) keeps the endpoint robust against
    # future sensitive columns being added to ``users`` (e.g. ``is_active``,
    # ``hashed_password``, ``risk_profile``) — anything NOT whitelisted is
    # silently dropped, never written through. The whitelist is derived from
    # ``UserProfileCreate.model_fields`` so the Pydantic contract stays the
    # source of truth for what is editable on the profile endpoint.
    _MUTABLE_FIELDS = frozenset(UserProfileCreate.model_fields.keys())
    patch = {
        field: value
        for field, value in payload.model_dump().items()
        if value is not None and field in _MUTABLE_FIELDS
    }
    for field, value in patch.items():
        setattr(user, field, value)
    db.add(user)

    # Phase 54+ — sync the Self family member's name when the user
    # changes their display name. Without this, the Accounts page
    # (which renders FamilyMember.name, not User.full_name) would
    # show the stale "Alex" forever after a Settings rename.
    if "full_name" in patch:
        self_row = get_or_create_family_member_self(db, user)
        new_name = (patch["full_name"] or "").strip()
        if new_name and self_row.name != new_name:
            self_row.name = new_name
            db.add(self_row)

    db.commit()
    db.refresh(user)
    return user
