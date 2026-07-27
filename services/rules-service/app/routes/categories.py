"""Local ORM CRUD for /api/categories/.

Phase F4 originally lifted this route as a thin httpx forwarder to
Finlynq's canonical ``/categories`` store (``benefitsiq-backend``).
The forwarder contract required Finlynq to be running + reachable
AND to return Pydantic-compatible JSON. In practice the forwarder
caused pervasive 5xx errors on the /settings page because Finlynq
was not always up, and ``classifyError`` would surface a misleading
"Network Error" instead of the user's intended action.

This rewrite keeps Phase F4's intent (``Category`` is a SHARED,
SINGLE-USER taxonomy — not per-user data) while making the rules-
service the canonical store. Cross-service sync is OUT OF SCOPE for
MVP; if a future Phase reintroduces Finlynq, this file is the only
one to rewrite.

The DB is the same SQLite-backed ``finance.db`` the categorizer
already reads from on every bulk auto-tag pass — re-pointing
``POST /api/categories/`` to write through the ORM is a net-zero
change for the existing categorizer service code.

Endpoints:

- ``GET    /api/categories/``              — list every category (single-user shared).
- ``POST   /api/categories/``              — create one; UNIQUE(name) 409 on duplicate.
- ``PUT    /api/categories/{category_id}`` — partial update; 404 if missing,
                                             409 if rename collides with an existing
                                             row (UNIQUE enforcement).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Category
from app.schemas import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("/", response_model=List[CategoryResponse])
async def list_categories(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Return every category, sorted by name ASC for a stable FE render.

    The list is intentionally un-scoped to ``user_id`` per Phase F4's
    single-user taxonomy: the category table is a REFERENCE TABLE,
    not user data, so every authenticated request sees the same set.
    Auth is enforced via ``Depends(require_user)`` so a stale cookie
    still 401s (defence-in-depth against accidental leaks — no
    cross-user leak vector because there is only ONE user, but the
    gate keeps the route shape consistent with every other resource).
    """
    return (
        db.query(Category)
        .order_by(Category.name.asc())
        .all()
    )


@router.post(
    "/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create a category; 409 on UNIQUE(name) collision.

    Empty-string guard mirrors Phase 7/16 conventions: an empty
    ``name`` would render as an empty chip on the Settings card's
    rule-dropdown. Pydantic ``Field(min_length=1)`` enforces this
    upstream; the route's defensive strip is belt-and-braces against
    a future Pydantic drift.
    """
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail="Category name must not be empty.",
        )
    # Build the row from the whitelisted payload fields so a future
    # Pydantic addition cannot leak through into the DB without an
    # explicit route update (Phase F4 whitelist contract).
    category = Category(
        name=name,
        description=(payload.description or None),
        icon=(payload.icon or None),
        color=payload.color,
        budget_group=payload.budget_group or "flexible",
        group=payload.group or "Expenses",
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A category named '{name}' already exists.",
        )
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Partial update. ``None`` values are silently dropped (``PATCH`` semantics)
    so an absent field on the wire leaves the row untouched. 404 on
    no-such-id; 409 on UNIQUE(name) collision when the rename crosses
    an existing row.
    """
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # ``exclude_none=True`` is the patch-semantic key: a client
    # sending ``{"name": null}`` (express unset) doesn't accidentally
    # blank out the stored name. The whitelist-loop accepts ANY
    # field on CategoryUpdate; identity columns (id) are intentionally
    # ABSENT from the schema so the whitelist cannot escalate.
    patch = {
        field: value
        for field, value in payload.model_dump(exclude_none=True).items()
        if value is not None
    }
    # Normalise ``name`` to a stripped non-empty string before
    # commit (mirrors the create-route's defensive guard).
    if "name" in patch:
        cleaned = (patch["name"] or "").strip()
        if not cleaned:
            raise HTTPException(
                status_code=400,
                detail="Category name must not be empty.",
            )
        patch["name"] = cleaned

    for field, value in patch.items():
        setattr(category, field, value)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Another category named '{patch.get('name', category.name)}' already exists.",
        )
    db.refresh(category)
    return category
