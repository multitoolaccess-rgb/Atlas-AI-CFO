"""Phase 6 + Phase 11 + Phase-F4 lift — /api/transactions/ list, read,
update, AND the bulk categorize forwarder.

Phase-F4 update: ``POST /api/transactions/categorize`` becomes a
thin httpx forwarder to Finlynq's canonical heuristc at
``POST /categorize``. The forwarder emits
``{categorized, skipped, total}`` verbatim — the same shape rules-service
returned PRE-F4 via the local ``categorize_transactions`` bulk helper.
The FE contracts stay unchanged.

Why a forwarder instead of local categorizer: Phase-F2's shared-DB
wiring binds both services to the SAME database file; the local
bulk-helper on rules-service would race against Finlynq's own
write path. A pure forwarder eliminates that race.

Endpoints:
- ``GET    /api/transactions/``              — list with filters (Phase 11).
- ``GET    /api/transactions/{id}``          — fetch one.
- ``PUT    /api/transactions/{id}``          — partial update.
- ``POST   /api/transactions/categorize``    — forwarder to Finlynq.

All routes still require a valid JWT cookie.
"""
import logging
from datetime import datetime
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session, joinedload

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models import Account, Category, Transaction
from app.routes.shared import get_or_create_local_user
from app.schemas import TransactionResponse, TransactionUpdate
from pydantic import BaseModel
from app.services.categorizer import (
    build_merchant_rules,
    categorize_transactions,
    find_all_matching_rules,
    learn_alias_for_category,
)
from app.models import MerchantRule

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

_logger = logging.getLogger(__name__)


# Phase 54+ — duplicate resolution schemas.
class DuplicateResolveResponse(BaseModel):
    """Response for the resolve-duplicate endpoint."""
    kept_id: Optional[int] = None
    deleted_id: Optional[int] = None
    action: str
    message: str


_SORTABLE_COLUMNS = {
    "transaction_date": Transaction.transaction_date,
    "amount": Transaction.amount,
    "description": Transaction.description,
    "created_at": Transaction.created_at,
}


@router.get("/", response_model=List[TransactionResponse])
async def list_transactions(
    account_id: Optional[int] = Query(None, description="Filter by account id (auth-scoped)."),
    account_type: Optional[str] = Query(None, description="Filter by account type."),
    from_date: Optional[datetime] = Query(None, description="ISO 8601 inclusive lower bound."),
    to_date: Optional[datetime] = Query(None, description="ISO 8601 inclusive upper bound."),
    category_id: Optional[int] = Query(None, description="Filter by category id."),
    is_pending: Optional[bool] = Query(None, description="Filter by pending flag."),
    # Phase 28 — uncategorized rows shortcut. When True, restricts the
    # result to rows where ``category_id IS NULL`` (the same set the
    # Activity page's "Promote to rule" affordance and the "Untagged"
    # status filter can act on). When False (default) this filter is
    # a no-op so existing call-sites are unaffected. An EXPLICIT
    # ``category_id`` and an EXPLICIT ``uncategorized=true`` are
    # mutually exclusive: the BE honours ``uncategorized=true`` and
    # ignores ``category_id`` (the user wants "all uncategorized",
    # not "all rows tagged with category X"; both filters AND-ed
    # together would always return zero rows).
    uncategorized: bool = Query(
        False,
        description=(
            "When True, restrict to rows with category_id IS NULL. "
            "Combines with the other filters (account_id, date range, "
            "search, etc.) via AND. Mutually exclusive with category_id: "
            "if both are set, uncategorized wins."
        ),
    ),
    search: Optional[str] = Query(None, description="Case-insensitive substring match."),
    sort_by: Optional[str] = Query(None, description="One of: transaction_date | amount | description | created_at."),
    sort_dir: Optional[str] = Query(None, description="asc | desc."),
    limit: int = Query(200, ge=1, le=10000),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """List the local user's transactions, optionally filtered."""
    local_user = get_or_create_local_user(db, _current_user)

    query = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(Account.user_id == local_user.id)
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    if account_type:
        query = query.filter(Account.account_type == account_type.lower())
    if from_date is not None:
        query = query.filter(Transaction.transaction_date >= from_date)
    if to_date is not None:
        query = query.filter(Transaction.transaction_date <= to_date)
    # ``uncategorized`` wins over an explicit ``category_id`` (mutually
    # exclusive per the Query docstring above). Implemented as an
    # early-branch IF so a future change that adds another category-
    # scoped filter can stack on top of the canonical category_id
    # path without surprising this branch.
    if uncategorized:
        query = query.filter(Transaction.category_id.is_(None))
    elif category_id is not None:
        query = query.filter(Transaction.category_id == category_id)
    if is_pending is not None:
        query = query.filter(Transaction.is_pending == is_pending)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Transaction.description.ilike(term),
                Transaction.merchant_name.ilike(term),
            )
        )

    if sort_by and sort_by in _SORTABLE_COLUMNS:
        col = _SORTABLE_COLUMNS[sort_by]
        order = asc(col) if (sort_dir or "").lower() == "asc" else desc(col)
        query = query.order_by(order)
    else:
        query = query.order_by(
            desc(Transaction.transaction_date),
            desc(Transaction.id),
        )

    rows = query.options(
        joinedload(Transaction.account),
        joinedload(Transaction.category),
    ).limit(limit).all()

    response: List[TransactionResponse] = []
    for t in rows:
        response.append(
            TransactionResponse(
                id=t.id,
                description=t.description,
                amount=t.amount,
                # Phase 52+ — surface the dual-column bookkeeping values
                # directly off the ORM row. The TransactionResponse schema
                # declares both as Optional[float] = None, so omitting
                # the keys here would Pydantic-default them to NULL and
                # the FE's Debit / Credit columns would render as
                # em-dashes for every row. The Activity page +
                # dashboard RecentActivity assume these keys are present
                # for credit_card rows (Phase 52+ dual-column layout).
                debit=t.debit,
                credit=t.credit,
                transaction_date=t.transaction_date,
                merchant_name=t.merchant_name,
                is_pending=t.is_pending,
                account_id=t.account_id,
                account_name=t.account.account_name if t.account else None,
                account_type=t.account.account_type if t.account else None,
                category_id=t.category_id,
                category_name=t.category.name if t.category else None,
                is_duplicate=t.is_duplicate,
                duplicate_of_id=t.duplicate_of_id,
            )
        )
    return response


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    local_user = get_or_create_local_user(db, _current_user)
    txn = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
        )
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Transaction.id == transaction_id,
            Account.user_id == local_user.id,
        )
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionResponse(
        id=txn.id,
        description=txn.description,
        amount=txn.amount,
        debit=txn.debit,
        credit=txn.credit,
        transaction_date=txn.transaction_date,
        merchant_name=txn.merchant_name,
        is_pending=txn.is_pending,
        account_id=txn.account_id,
        account_name=txn.account.account_name if txn.account else None,
        account_type=txn.account.account_type if txn.account else None,
        category_id=txn.category_id,
        category_name=txn.category.name if txn.category else None,
        is_duplicate=txn.is_duplicate,
        duplicate_of_id=txn.duplicate_of_id,
    )


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Partial update of a transaction.

    Today only ``category_id`` (manual override after auto-categorize)
    + ``merchant_name`` (correct a parser lookup, e.g. "SQ *STARBUCKS"
    → "Starbucks") are mutable.

    Foreign-key sanity: ``category_id`` is validated against the
    ``Category`` table BEFORE the patch is applied — a bad id would
    400 instead of raising a SQLite/postgres FK violation mid-commit.
    """
    local_user = get_or_create_local_user(db, _current_user)
    txn = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Transaction.id == transaction_id,
            Account.user_id == local_user.id,
        )
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Phase 28 — detach-affordance bug fix. The previous
    # ``{k: v for k, v in payload.model_dump().items() if v is not None}``
    # filter SILENTLY dropped an explicit ``category_id: null`` sent
    # by the FE's detach button — ``None`` was treated as "absent"
    # and the field never reached the for-loop below, so the row's
    # category_id stayed unchanged and the click appeared to do
    # nothing. Switching to ``model_dump(exclude_unset=True)``
    # distinguishes "field absent in the payload" (the FE didn't
    # touch it — keep the current value) from "field present and
    # explicitly null" (the FE wants to detach — set the column to
    # None). Without this fix the Activity page's per-row chip
    # detach affordance is a dead button. The same fix applies to
    # merchant_name: a client that explicitly wants to clear the
    # merchant text can now PUT ``{merchant_name: null}``.
    # Phase 39 — capture original category BEFORE the patch so the
    # detach→archive logic knows which category to target.
    original_category_id = txn.category_id
    original_category_name = txn.category.name if txn.category else None

    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}

    if "category_id" in patch:
        cid = patch["category_id"]
        if cid is not None:
            try:
                cid_int = int(cid)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="category_id must be an integer or null.",
                )
            if cid_int > 0:
                cat = db.query(Category).filter(Category.id == cid_int).first()
                if not cat:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Category id {cid_int} does not exist.",
                    )
                patch["category_id"] = cid_int
            else:
                patch["category_id"] = None

    for field, value in patch.items():
        if hasattr(txn, field):
            setattr(txn, field, value)
    db.add(txn)

    # Phase 39 — detach → archive. When the user clears a category
    # (clicks the "detach" chip on a tagged transaction), find ALL
    # substring rules that would have matched this transaction for
    # the original category and archive them (soft-delete via
    # is_archived=True). This prevents duplicate/conflicting rules
    # from re-tagging the same transaction on the next auto-categorize.
    #
    # Guard: only fire when category was EXPLICITLY cleared (in patch
    # and final value is None) AND the txn previously had a category.
    if (
        "category_id" in patch
        and txn.category_id is None
        and original_category_id is not None
        and original_category_name is not None
    ):
        rules_dict, _ = build_merchant_rules(db)
        all_matches = find_all_matching_rules(
            txn.merchant_name, txn.description, rules_dict,
        )
        archived_count = 0
        for match in all_matches:
            if match.get("category_name") != original_category_name:
                continue
            kw = str(match.get("keyword", ""))
            # Find the DB row by keyword + category_name (via the
            # rules_dict's category_name → keywords mapping).
            rule = (
                db.query(MerchantRule)
                .join(Category, Category.id == MerchantRule.category_id)
                .filter(
                    Category.name == original_category_name,
                    MerchantRule.keyword == kw,
                    MerchantRule.is_archived.is_(False),
                )
                .first()
            )
            if rule is not None:
                rule.is_archived = True
                db.add(rule)
                archived_count += 1
        if archived_count > 0:
            _logger.info(
                "Detach→archive: txn #%d (%r) — archived %d rule(s) "
                "in category %r",
                txn.id, (txn.description or "")[:60],
                archived_count, original_category_name,
            )

    # Phase 18 — manual-tag alias learning. The user explicitly
    # assigned ``category_id`` (e.g. by clicking the inline ``<select>``
    # on the activity page); write an alias row so the same raw
    # merchant text on future imports hits Pass 1 (alias) instead of
    # falling back to Pass 2 substring or Pass 3 fuzzy. The alias_key
    # canonicalisation preserves numeric tokens ("DOORDASH 1234" is
    # distinct from "DOORDASH 5678"), so a one-off user override
    # only locks the EXACT raw text — substring Pass 2 retains its
    # safety-net role for the bare merchant name. Atomic with the
    # category_id write (no separate commit — a unique-constraint
    # conflict rolls back both in one round-trip).
    if "category_id" in patch and txn.category_id is not None:
        learn_alias_for_category(
            db,
            user_id=local_user.id,
            txn=txn,
            category_id=txn.category_id,
        )

    db.commit()
    db.refresh(txn)

    return TransactionResponse(
        id=txn.id,
        description=txn.description,
        amount=txn.amount,
        debit=txn.debit,
        credit=txn.credit,
        transaction_date=txn.transaction_date,
        merchant_name=txn.merchant_name,
        is_pending=txn.is_pending,
        account_id=txn.account_id,
        account_name=txn.account.account_name if txn.account else None,
        account_type=txn.account.account_type if txn.account else None,
        category_id=txn.category_id,
        category_name=txn.category.name if txn.category else None,
        is_duplicate=txn.is_duplicate,
        duplicate_of_id=txn.duplicate_of_id,
    )


@router.post("/resolve-duplicates", response_model=DuplicateResolveResponse)
async def resolve_all_duplicates(
    action: Literal["keep_this", "keep_original", "keep_all"] = "keep_all",
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Resolve ALL duplicate transactions for the local user.

    Bulk endpoint — resolves every ``is_duplicate=True`` row in one call.
    Three actions:
    - ``'keep_all'``: clear ``is_duplicate`` flag on all duplicate rows
      (accept them as legitimate).
    - ``'keep_original'``: delete all duplicate rows, clear flag on originals.
    - ``'keep_this'``: delete the originals, clear flag on duplicates.

    Returns counts so the FE can render a summary toast.
    """
    local_user = get_or_create_local_user(db, _current_user)
    dupes = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.user_id == local_user.id,
            Transaction.is_duplicate.is_(True),
        )
        .all()
    )
    if not dupes:
        return DuplicateResolveResponse(
            action=action,
            message="No duplicate transactions to resolve.",
        )

    if action == "keep_all":
        for d in dupes:
            d.is_duplicate = False
            d.duplicate_of_id = None
        db.commit()
        return DuplicateResolveResponse(
            action=action,
            kept_id=None,
            deleted_id=None,
            message=f"Marked {len(dupes)} duplicate(s) as non-duplicate.",
        )
    elif action == "keep_original":
        # Delete the duplicate rows, keep originals
        deleted_ids = [d.id for d in dupes]
        # Also clear is_duplicate on any originals that were themselves
        # flagged (edge case: chain dupes A->B->C)
        original_ids = set(d.duplicate_of_id for d in dupes if d.duplicate_of_id)
        for d in dupes:
            db.delete(d)
        # Clear flag on originals
        if original_ids:
            originals = db.query(Transaction).filter(Transaction.id.in_(original_ids)).all()
            for o in originals:
                o.is_duplicate = False
                o.duplicate_of_id = None
        db.commit()
        return DuplicateResolveResponse(
            action=action,
            deleted_id=deleted_ids[0] if len(deleted_ids) == 1 else None,
            message=f"Deleted {len(deleted_ids)} duplicate(s), kept originals.",
        )
    else:  # keep_this
        # Delete the originals, keep the duplicate rows
        original_ids = set(d.duplicate_of_id for d in dupes if d.duplicate_of_id)
        for d in dupes:
            d.is_duplicate = False
            d.duplicate_of_id = None
        if original_ids:
            originals = db.query(Transaction).filter(Transaction.id.in_(original_ids)).all()
            for o in originals:
                db.delete(o)
        db.commit()
        return DuplicateResolveResponse(
            action=action,
            deleted_id=list(original_ids)[0] if len(original_ids) == 1 else None,
            message=f"Kept {len(dupes)} duplicate(s), deleted {len(original_ids)} original(s).",
        )


@router.post("/{transaction_id}/resolve-duplicate", response_model=DuplicateResolveResponse)
async def resolve_single_duplicate(
    transaction_id: int,
    action: Literal["keep_both", "keep_original", "keep_this"] = "keep_both",
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Resolve a single duplicate transaction.

    Three actions:
    - ``'keep_both'``: accept this transaction as legitimate (clear duplicate flags).
    - ``'keep_original'``: delete THIS duplicate, keep the original it points to.
    - ``'keep_this'``: delete the original, keep THIS duplicate.
    """
    local_user = get_or_create_local_user(db, _current_user)
    txn = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Transaction.id == transaction_id,
            Account.user_id == local_user.id,
            Transaction.is_duplicate.is_(True),
        )
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Duplicate transaction not found")

    original_id = txn.duplicate_of_id

    if action == "keep_both":
        txn.is_duplicate = False
        txn.duplicate_of_id = None
        # Also clear the original's flag if it was itself flagged
        if original_id:
            orig = db.query(Transaction).filter(Transaction.id == original_id).first()
            if orig and orig.is_duplicate:
                orig.is_duplicate = False
                orig.duplicate_of_id = None
        db.commit()
        return DuplicateResolveResponse(
            action=action, kept_id=txn.id,
            message="Kept both transactions.",
        )
    elif action == "keep_original":
        db.delete(txn)
        db.commit()
        return DuplicateResolveResponse(
            action=action, deleted_id=transaction_id,
            message="Deleted duplicate, kept original.",
        )
    else:  # keep_this
        txn.is_duplicate = False
        txn.duplicate_of_id = None
        if original_id:
            original = db.query(Transaction).filter(Transaction.id == original_id).first()
            if original:
                db.delete(original)
        db.commit()
        return DuplicateResolveResponse(
            action=action, kept_id=txn.id, deleted_id=original_id,
            message="Kept duplicate, deleted original.",
        )


@router.post("/categorize")
async def auto_categorize_transactions(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Bulk auto-categorize EVERY transaction the local user owns.

    Phase-F4 round-up fix: the endpoint runs the LIFTED categorizer
    helper locally (the heuristic is identical to Finlynq's
    ``MERCHANT_RULES`` because both services bind to the SAME
    database file per Phase-F2 wiring + the categorizer code itself is
    byte-equivalent). A pure forwarder cannot satisfy this contract
    because the persistence target is rules-service's local
    ``Transaction`` rows — the FE's "tagged N of M" toast reads back
    the local row's ``category_id`` AFTER this endpoint persists, so
    a forwarder to Finlynq that only returns counts leaves the local
    DB unchanged and surfaces "0 of 0".

    Phase 33 fix — the endpoint previously only fetched uncategorized
    rows (``category_id IS NULL``). After a user creates a new rule
    (e.g. "zelle payment from" → Income), rows that were already
    auto-categorized to "Transfer" on import would NOT be
    re-evaluated — the user's click appeared to do nothing. We now
    fetch ALL rows so every transaction is re-scanned against the
    current ruleset. The categorizer's ``categorize_transactions``
    helper already guards ``txn.category_id == matched_category.id``
    (skips rows that are already correct) and Pass 1 alias lookup
    protects manual overrides — only rows whose suggested category
    differs from the stored category are touched.

    Returns ``{categorized: int, skipped: int, total: int}`` so the
    FE can render a "tagged N of M" toast with no follow-up GET.
    ``skipped`` counts already-correct ``category_id`` rows + the
    ``"Other"`` fallback when ``allow_other=False``.
    """
    local_user = get_or_create_local_user(db, _current_user)
    all_txns = (
        db.query(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .filter(Account.user_id == local_user.id)
        .all()
    )
    # Phase 33 — count uncategorized rows separately so the FE toast
    # ("Tagged N of M") shows a meaningful denominator (only the rows
    # that WERE uncategorized before this run), while the categorizer
    # still processes ALL rows so new/edited rules can re-tag rows
    # that were previously auto-categorized to a different bucket.
    before = sum(1 for t in all_txns if t.category_id is None)
    categorized, skipped, conflicts = categorize_transactions(db, all_txns)
    db.commit()
    _logger.info(
        "Auto-categorize: user=%s total=%d tagged=%d skipped=%d",
        local_user.email, before, categorized, skipped,
    )
    return {
        "categorized": categorized,
        "skipped": skipped,
        "total": before,
        "conflicts": conflicts,
    }
