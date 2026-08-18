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
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from app.auth import require_user
from app.database import get_db
from app.models import Account, Category, MerchantRule, Transaction
from app.routes.shared import get_or_create_local_user
from app.schemas import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.categorizer import learn_alias_for_category

router = APIRouter(prefix="/api/categories", tags=["categories"])


# Phase 30h — sub-category hierarchy helpers.
def _resolve_parent(db: Session, parent_id: int) -> Category:
    """Fetch a parent category or 404."""
    parent = db.query(Category).filter(Category.id == parent_id).first()
    if parent is None:
        raise HTTPException(
            status_code=404,
            detail=f"Parent category id={parent_id} does not exist.",
        )
    return parent


def _assert_no_cycle(db: Session, category: Category, parent_id: int) -> None:
    """Reject a parent link that would create a cycle.

    ``category`` is the row being edited; ``parent_id`` is the proposed
    new parent. A cycle exists if the proposed parent IS the category
    itself, or if the proposed parent is one of the category's own
    descendants (walking UP from the parent must never reach the
    category).
    """
    if parent_id == category.id:
        raise HTTPException(
            status_code=400,
            detail="A category cannot be its own parent.",
        )
    cursor = db.query(Category).filter(Category.id == parent_id).first()
    seen: set[int] = set()
    while cursor is not None and cursor.parent_id is not None:
        if cursor.id in seen:
            break  # pre-existing cycle in data — stop, don't loop forever
        seen.add(cursor.id)
        if cursor.id == category.id or cursor.parent_id == category.id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Linking under parent id={parent_id} would create a "
                    "cycle: the parent is a descendant of this category."
                ),
            )
        cursor = db.query(Category).filter(
            Category.id == cursor.parent_id
        ).first()


def _category_payload(
    category: Category,
) -> dict:
    """Serialize a Category row to the wire shape (adds parent_name)."""
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "icon": category.icon,
        "color": category.color,
        "budget_group": category.budget_group,
        "group": category.group,
        "parent_id": category.parent_id,
        "parent_name": category.parent.name if category.parent else None,
    }


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

    Phase 30h — each row also carries ``parent_id`` / ``parent_name``
    (None for top-level categories) so the FE can render the
    sub-category hierarchy.
    """
    rows = db.query(Category).order_by(Category.name.asc()).all()
    return [_category_payload(c) for c in rows]


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
    # Phase 30h — resolve the parent (if any) BEFORE building the row
    # so we can 404 on a missing parent and inherit its ``group``. A
    # sub-category always lives in its parent's group (the payload's
    # ``group`` is ignored for children — the hierarchy is the source
    # of truth, not a redundant field that could drift).
    parent = None
    if payload.parent_id is not None:
        parent = _resolve_parent(db, payload.parent_id)

    # Build the row from the whitelisted payload fields so a future
    # Pydantic addition cannot leak through into the DB without an
    # explicit route update (Phase F4 whitelist contract).
    category = Category(
        name=name,
        description=(payload.description or None),
        icon=(payload.icon or None),
        color=payload.color,
        budget_group=payload.budget_group or "flexible",
        group=parent.group if parent else (payload.group or "Expenses"),
        parent_id=parent.id if parent else None,
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
    return _category_payload(category)


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
    # Phase 30h — ``parent_id`` is the one field where NULL is a
    # meaningful value (it CLEARS the sub-category link). ``exclude_
    # none=True`` drops it, so re-add it when the client EXPLICITLY
    # sent ``null`` (Pydantic v2 ``model_fields_set`` tracks which
    # fields were present on the wire vs defaulted).
    if "parent_id" in payload.model_fields_set and payload.parent_id is None:
        patch["parent_id"] = None
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

    # Phase 30h — validate the parent link before applying: the parent
    # must exist, must not be the category itself, and must not be a
    # descendant (cycle guard). When a parent is set and ``group`` is
    # not explicitly patched, inherit the parent's group so a child
    # never drifts into a mismatched taxonomy group.
    if "parent_id" in patch and patch["parent_id"] is not None:
        parent = _resolve_parent(db, int(patch["parent_id"]))
        _assert_no_cycle(db, category, parent.id)
        if "group" not in patch:
            patch["group"] = parent.group

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
    return _category_payload(category)


# ---------------------------------------------------------------------
# Phase 30h — accept an LLM Pass-4 new-category proposal.
# ---------------------------------------------------------------------
class AcceptProposalRequest(BaseModel):
    """Accept a Pass-4 ``is_new`` suggestion.

    ``proposed_category`` is the new category name the LLM suggested;
    ``proposed_parent`` the (optional) canonical parent it should nest
    under. ``keyword`` is the merchant text used to build a substring
    rule so future rows from the same merchant auto-categorise.
    """
    transaction_id: int
    proposed_category: str = Field(..., min_length=1, max_length=60)
    proposed_parent: Optional[str] = None
    keyword: Optional[str] = None


class AcceptProposalResponse(BaseModel):
    transaction_id: int
    category_id: int
    category_name: str
    category_created: bool
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None
    rule_id: Optional[int] = None
    rule_created: bool = False


@router.post(
    "/accept-proposal",
    response_model=AcceptProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_category_proposal(
    payload: AcceptProposalRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create the proposed category (+ optional parent link) and a
    merchant rule, then tag the transaction — in ONE atomic commit.

    This is the Accept action behind the Activity page's Pass-4
    ``is_new`` suggestions. Idempotent by construction:

    - Category: find-or-create by name (a repeat Accept reuses the
      existing row; ``category_created`` reports which happened).
    - Parent: resolved by name and must already exist (404 otherwise
      — the LLM only proposes under canonical parents, so a missing
      parent is a proposal bug, not something to silently create).
    - Rule: find-or-create ``UNIQUE(category_id, keyword)`` with
      ``source='llm'`` (the provenance value reserved for this flow);
      ``rule_created`` reports which happened.
    - Transaction: owner-scoped via ``Account.user_id`` (there is no
      ``Transaction.user_id`` column), tagged with the category, and
      passed through ``learn_alias_for_category`` so the same raw
      merchant text auto-categorises on future imports.

    Everything lands in one commit: a mid-flow failure rolls back the
    whole Accept rather than leaving a half-created category.
    """
    local_user = get_or_create_local_user(db, _current_user)
    txn = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Transaction.id == payload.transaction_id,
            Account.user_id == local_user.id,
        )
        .first()
    )
    if txn is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Transaction id={payload.transaction_id} not found for "
                "the current user."
            ),
        )

    proposed = payload.proposed_category.strip()
    # Resolve the parent by name (must already exist — the LLM only
    # proposes under canonical parents).
    parent: Optional[Category] = None
    if payload.proposed_parent:
        parent_name = payload.proposed_parent.strip()
        parent = (
            db.query(Category)
            .filter(Category.name == parent_name)
            .first()
        )
        if parent is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Parent category '{parent_name}' does not exist. "
                    "Proposals can only nest under an existing category."
                ),
            )

    # Find-or-create the category.
    category = (
        db.query(Category).filter(Category.name == proposed).first()
    )
    category_created = False
    if category is None:
        category = Category(
            name=proposed,
            description=f"Created from an LLM Pass-4 proposal",
            group=parent.group if parent else "Expenses",
            parent_id=parent.id if parent else None,
        )
        db.add(category)
        category_created = True
    # Flush so a freshly-created category has an id before we build
    # the merchant rule / tag the transaction (both need category.id).
    db.flush()

    # Find-or-create the merchant rule (source='llm').
    rule_id: Optional[int] = None
    rule_created = False
    if payload.keyword:
        keyword = payload.keyword.strip().upper()
        if keyword:
            rule = (
                db.query(MerchantRule)
                .filter(
                    MerchantRule.category_id == category.id,
                    MerchantRule.keyword == keyword,
                )
                .first()
            )
            if rule is None:
                max_priority = (
                    db.query(func.max(MerchantRule.priority))
                    .filter(MerchantRule.category_id == category.id)
                    .scalar()
                )
                rule = MerchantRule(
                    category_id=category.id,
                    keyword=keyword,
                    priority=(max_priority + 10) if max_priority else 100,
                    source="llm",
                )
                db.add(rule)
                rule_created = True
            # Flush so a freshly-created rule has an id for the
            # response (the final commit happens below).
            db.flush()
            rule_id = rule.id

    # Tag the transaction + learn the alias (mirrors the manual-tag
    # PUT path so repeat merchants auto-categorise).
    txn.category_id = category.id
    learn_alias_for_category(
        db,
        user_id=local_user.id,
        txn=txn,
        category_id=category.id,
    )

    db.commit()
    db.refresh(category)
    return AcceptProposalResponse(
        transaction_id=txn.id,
        category_id=category.id,
        category_name=category.name,
        category_created=category_created,
        parent_id=category.parent_id,
        parent_name=category.parent.name if category.parent else None,
        rule_id=rule_id,
        rule_created=rule_created,
    )
