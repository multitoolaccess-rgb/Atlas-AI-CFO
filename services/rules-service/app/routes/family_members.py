"""Phase 16 — ``/api/family-members/`` CRUD (auth-enforced).

Every user has exactly ONE ``is_self=True`` row, bootstrapped on the
first authenticated request by :func:`app.routes.shared.get_or_create_local_user`.
Additional members (Spouse, Kid, Grandparent) are created via
``POST /api/family-members/`` and archived via ``DELETE /api/family-members/{id}``.

- ``GET    /api/family-members/``         — list the local user's non-archived members.
- ``POST   /api/family-members/``         — create (name + hex color).
- ``GET    /api/family-members/{member_id}`` — fetch a single member (404 if missing).
- ``PUT    /api/family-members/{member_id}`` — partial update of name + color.
- ``DELETE /api/family-members/{member_id}`` — soft-archive (409 if active accounts, 400 if Self).

All endpoints require a valid JWT cookie (``Depends(require_user)``).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Account, FamilyMember
from app.routes.shared import (
    get_or_create_family_member_self,
    get_or_create_local_user,
)
from app.schemas import FamilyMemberCreate, FamilyMemberResponse, FamilyMemberUpdate

router = APIRouter(prefix="/api/family-members", tags=["family-members"])


def _get_user_family_member(
    db: Session, member_id: int, user_id: int
) -> FamilyMember:
    """Fetch a single FamilyMember owned by the local user. Raises 404 if missing.

    Centralized 404 helper — the ``GET / PUT / DELETE`` endpoints all
    need the same query-by-id-and-user lookup, and duplicating it
    three times would let a future refactor diverge (e.g. one path
    forgetting the ``user_id`` filter and leaking rows from other
    users). Centralizing keeps the scope-invariants in one place.
    """
    member = (
        db.query(FamilyMember)
        .filter(FamilyMember.id == member_id, FamilyMember.user_id == user_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Family member not found")
    return member


@router.get("/", response_model=List[FamilyMemberResponse])
async def list_family_members(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """List the local user's non-archived members (including Self).

    The first call for a brand-new user bootstraps the Self row via
    :func:`get_or_create_family_member_self` (mirrors Goal's
    ``Default $15M Goal`` auto-seed). Idempotent across calls — once
    a Self row exists, subsequent GETs skip the seed branch.
    """
    local_user = get_or_create_local_user(db, _current_user)
    get_or_create_family_member_self(db, local_user)
    rows = (
        db.query(FamilyMember)
        .filter(
            FamilyMember.user_id == local_user.id,
            FamilyMember.is_archived.is_(False),
        )
        .order_by(FamilyMember.is_self.desc(), FamilyMember.created_at.asc())
        .all()
    )
    return rows


@router.post(
    "/", response_model=FamilyMemberResponse, status_code=status.HTTP_201_CREATED
)
async def create_family_member(
    payload: FamilyMemberCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create a family member owned by the local user.

    Color is validated by Pydantic's ``Field(pattern=...)`` — non-hex
    values are rejected at the schema layer with HTTP 422 (no
    business logic in the route).

    Defensive regressions:
    - ``name`` must be a non-empty string after ``str.strip()`` —
      an empty name would break the FE chip on the Settings page.
    - UNIQUE (user_id, name) is enforced by the model; a duplicate
      is caught here and re-emitted as HTTP 409 with a friendly
      detail. The same envelope is enforced by the global
      IntegrityError handler in ``app.main``, but inlining gives
      callers a more actionable message ("member already exists"
      rather than the generic handler "A record with that value
      already exists.").
    """
    local_user = get_or_create_local_user(db, _current_user)
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail="Family member name must not be empty.",
        )
    member = FamilyMember(
        user_id=local_user.id,
        name=name,
        color=payload.color,
        # Phase 16+ — forward the household-profile fields straight
        # through. ``None`` on the wire (the documented 'two-click
        # create' path) persists as a NULL column so a later PUT can
        # layer in the data without overwriting a stored value with
        # ``None``. Pydantic Literal types on the schema keep the
        # values constrained at the API boundary; the route is
        # pure-pass-through so a future "household-profile
        # enrichment" feature (Phase 18+) only has to touch the
        # Pydantic + ORM layers.
        relationship=payload.relationship,
        working_status=payload.working_status,
        age=payload.age,
        is_self=False,  # Self is bootstrapped, not POSTable
        is_archived=False,
    )
    db.add(member)
    try:
        db.commit()
    except SQLAlchemyIntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A family member named '{name}' already exists.",
        )
    db.refresh(member)
    return member


@router.get("/{member_id}", response_model=FamilyMemberResponse)
async def get_family_member(
    member_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Fetch a single member by id, scoped to the local user."""
    local_user = get_or_create_local_user(db, _current_user)
    return _get_user_family_member(db, member_id, local_user.id)


@router.put("/{member_id}", response_model=FamilyMemberResponse)
async def update_family_member(
    member_id: int,
    payload: FamilyMemberUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Partial update of a family member.

    Whitelist-driven: only fields declared on :class:`FamilyMemberUpdate`
    are written (name, color — ``is_self`` is INTENTIONALLY excluded
    so clients can NEVER promote an arbitrary member to ``is_self=True``).
    The route additionally rejects an empty ``name`` to keep the FE
    chip non-blank.

    Empty-string guard mirrors Phase 7's account name defense — an
    empty ``name`` would render as an empty chip on the Settings
    Family Members card, breaking the layout.
    """
    local_user = get_or_create_local_user(db, _current_user)
    member = _get_user_family_member(db, member_id, local_user.id)
    _MUTABLE_FIELDS = frozenset(FamilyMemberUpdate.model_fields.keys())
    patch = {
        field: value
        for field, value in payload.model_dump().items()
        if value is not None and field in _MUTABLE_FIELDS
    }
    if "name" in patch:
        cleaned = (patch["name"] or "").strip()
        if not cleaned:
            raise HTTPException(
                status_code=400,
                detail="Family member name must not be empty.",
            )
        patch["name"] = cleaned
    for field, value in patch.items():
        setattr(member, field, value)
    # Phase 16+ -- Self-row ``relationship`` lock. Whichever value the
    # client sent (or omitted) is overwritten to ``'Self'`` for the
    # Self row. Defence-in-depth: the FE's Settings card already
    # disables the relationship <select> while editing the Self row
    # (see ``ui/app/settings/page.tsx#submitEditMember``), but if a
    # user races through a raw curl call we'd rather honor the BE
    # contract than risk a Spouse row sneaking into the canonical
    # Self bucket. Sibling rows (``is_self=False``) keep whatever
    # ``relationship`` value the client sends so the user can flip
    # a Spouse to ``'Sibling'`` if their situation evolves.
    if member.is_self:
        member.relationship = "Self"
    db.add(member)
    try:
        db.commit()
    except SQLAlchemyIntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A family member named '{patch.get('name')}' already exists.",
        )
    db.refresh(member)
    return member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_family_member(
    member_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Soft-archive a family member — flips ``is_archived=True``.

    Three guarded branches, in priority order:

    1. ``is_self=True`` → ``HTTP 400`` with detail "Cannot archive
       the Self member." Every user has exactly one Self row;
       archiving it would orphan every account that defaults to it.
    2. ``query(Account).filter(family_member_id=X, is_active=True)
       .count() >= 1`` → ``HTTP 409`` with detail "Cannot archive:
       N active accounts still linked to this member." The user
       must archive / reassign those accounts first.
    3. Otherwise → flip ``is_archived=True`` and commit.

    Idempotent on already-archived rows (re-archive is a no-op,
    204 No Content either way). The row stays in the DB so FK
    references resolve (no CASCADE).
    """
    local_user = get_or_create_local_user(db, _current_user)
    member = _get_user_family_member(db, member_id, local_user.id)
    if member.is_self:
        raise HTTPException(
            status_code=400,
            detail="Cannot archive the Self member.",
        )
    active_count = (
        db.query(Account)
        .filter(
            Account.family_member_id == member_id,
            Account.user_id == local_user.id,
            Account.is_active.is_(True),
        )
        .count()
    )
    if active_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot archive '{member.name}': "
                f"{active_count} active account(s) still linked to this member. "
                f"Archive or reassign those accounts first."
            ),
        )
    if not member.is_archived:
        member.is_archived = True
        db.add(member)
        db.commit()
    return None
