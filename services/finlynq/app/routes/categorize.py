"""Finlynq /categorize + /categories endpoint implementations (Phase F4).

Phase F4 ships the real implementation that replaces the F1 501 stubs:

- ``POST /categorize`` — bulk auto-categorize via the lifted
  ``MERCHANT_RULES`` heuristic. Accepts a list of transaction-shaped
  rows (id, merchant_name, description) and returns
  ``{categorized, skipped, total}`` mirroring rules-service's
  ``POST /api/transactions/categorize`` shape exactly.

- ``GET    /categories``      — list the canonical ``categories`` rows.
- ``POST   /categories``      — insert a new row (UNIQUE on name).
- ``PUT    /categories/{id}`` — partial update (whitelisted fields).

All endpoints require a valid JWT cookie (``Depends(require_user)``).
Finlynq's auth dep is byte-for-byte identical to rules-service's —
the cookie minted on one is accepted by the other.

Cross-service wiring (Phase F2 + F4 wire lock):

- ``POST /categorize`` is the canonical-store heuristic. Rules-service's
  ``POST /api/transactions/categorize`` becomes a 5-line httpx forwarder
  (matches the F3 import-parser forwarder pattern).

- ``GET / POST / PUT /categories`` are the canonical CRUD. Rules-service's
  ``/api/categories/`` equivalents become httpx forwarders.

- The cross-service integration test
  ``tests/test_shared_db_across_services.py`` (F4 follow-up) writes a
  new category via Finlynq's POST /categories and reads it via
  rules-service's GET /api/categories/ forwarder — proving the
  shared-DB invariant.
"""
from typing import List, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Category
from app.services.categorizer import build_category_lookup, count_categorize_matches


# ---- /categorize ----------------------------------------------------------

router = APIRouter(prefix="/categorize", tags=["categorize"])


class CategorizeRequest(BaseModel):
    """Locked shape for bulk-categorize. Phase F4 accepts the per-row
    payment shape the FE sends today; additional fields (amount,
    transaction_date) ignored if present.
    """
    transactions: list[dict]


class CategorizeResponse(BaseModel):
    categorized: int
    skipped: int
    total: int


@router.post("", response_model=CategorizeResponse)
async def categorize(
    payload: CategorizeRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> CategorizeResponse:
    """Bulk heuristic auto-categorize.

    Runs the lifted ``categorizer.categorize_transactions`` against the
    payload's transactions list. The function returns
    ``(categorized, skipped)``; we extend with ``total`` so the FE
    can render "tagged N of M" toasts without a follow-up GET.

    Phase-F4 contract: idempotent — re-POSTing the same list with the
    SAME merchant descriptions yields the SAME counts (the heuristic
    is deterministic; no row updates are persisted because we're
    operating on plain dicts not ORM rows in this entry point).
    """
    total = len(payload.transactions)
    if total == 0:
        return CategorizeResponse(categorized=0, skipped=0, total=0)
    lookup = build_category_lookup(db)
    categorized, skipped = count_categorize_matches(payload.transactions, lookup)
    return CategorizeResponse(categorized=categorized, skipped=skipped, total=total)


# ---- /categories CRUD -----------------------------------------------------

categories_router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryCreatePayload(BaseModel):
    """Mirrors rules-service's CategoryCreate — same field set so the
    forwarder at rules-service's POST /api/categories/ is a 5-line proxy.
    """
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class CategoryUpdatePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class CategoryOut(BaseModel):
    """Mirrors rules-service's CategoryResponse — wire-shape parity locked
    by ``test_cross_service_schema.py`` (F7 follow-up)."""
    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


@categories_router.get("", response_model=List[CategoryOut])
async def list_categories(db: Session = Depends(get_db)) -> List[CategoryOut]:
    """List every category in the canonical ``categories`` table, ordered
    by name ASC. The activity-page filter + the categorize dropdown
    both populate from this endpoint.
    """
    return db.query(Category).order_by(Category.name.asc()).all()


@categories_router.post(
    "", response_model=CategoryOut, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryCreatePayload,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> CategoryOut:
    """Insert a new category.

    ``name`` is enforced UNIQUE by the ORM. A duplicate name surfaces
    as a SQLAlchemy IntegrityError caught here; we map it to HTTP 409
    with a stable detail message that matches the CORS-aware global
    exception handler in ``app.main.py``. Re-using a name also
    closes the same idempotency contract — re-POSTing the same name
    returns 409 (NOT 201 / NOT 200) so the FE knows it's a
    duplicate (the load-bearing contract the F4 idempotency test
    asserts).
    """
    cleaned_name = (payload.name or "").strip()
    if not cleaned_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name must not be empty.",
        )
    category = Category(
        name=cleaned_name,
        description=payload.description,
        icon=payload.icon,
        color=payload.color,
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with that name already exists.",
        )
    db.refresh(category)
    return category


@categories_router.put("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    payload: CategoryUpdatePayload,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> CategoryOut:
    """Partial update of a category. Only fields declared on
    ``CategoryUpdatePayload`` are written; any key not declared is
    silently dropped by ``model_dump()``.

    Renaming works the same as renaming in rules-service — we
    rewrite the row's ``name`` and any future ``Transaction.category_id``
    FKs remain valid (the FK is by id, not by name).
    """
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )
    _MUTABLE_FIELDS = frozenset(CategoryUpdatePayload.model_fields.keys())
    patch = {
        field: value
        for field, value in payload.model_dump().items()
        if value is not None and field in _MUTABLE_FIELDS
    }
    if "name" in patch:
        cleaned = (patch["name"] or "").strip()
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
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
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with that name already exists.",
        )
    db.refresh(category)
    return category
