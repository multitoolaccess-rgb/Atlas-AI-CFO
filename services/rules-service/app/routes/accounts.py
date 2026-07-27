"""Phase 6 lift — /api/accounts/ CRUD (auth-enforced).

Phase 4 lift provenance: wealthiq ``backend/app/routes/accounts.py`` (§4 item 16).
Phase 6 (this file): the auth contract is now enforced end-to-end. Every
endpoint accepts ``Depends(require_user)`` which decodes the JWT cookie
(or Bearer header) and validates the ``sub`` claim against
``settings.local_user``. ``require_user`` raises HTTP 401 on missing /
expired / wrong-subject tokens.

Substantive changes (Phase 4 + Phase 6 cumulative):

- ``get_or_create_demo_user`` -> ``get_or_create_local_user(db, _current_user)``
  where ``_current_user`` is the JWT subject (defaults to ``settings.local_user``).
- ``from app.db import get_db`` \u2192 ``from app.database import get_db``.
- ``Account.is_active == True`` -> ``Account.is_active.is_(True)``
  (safer SQLAlchemy 2.0 idiom on nullable booleans).
- Phase 6: every endpoint has ``Depends(require_user)``.
"""
from typing import List, Optional
import logging as _acct_log

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Account, Transaction
from app.account_types import CREDIT_ACCOUNT_TYPES
from app.routes.shared import (
    get_or_create_family_member_self,
    get_or_create_institution,
    get_or_create_local_user,
    recalculate_account_balance,
    recalculate_all_user_balances,
)
from app.schemas import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """List all active accounts belonging to the local user (Phase 6: auth-enforced)."""
    local_user = get_or_create_local_user(db, _current_user)
    accounts = (
        db.query(Account)
        .filter(Account.user_id == local_user.id, Account.is_active.is_(True))
        .all()
    )
    return accounts


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Get a single account by id (scoped to the local user; Phase 6: auth-enforced)."""
    local_user = get_or_create_local_user(db, _current_user)
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == local_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/", response_model=AccountResponse, status_code=201)
async def create_account(
    account_data: AccountCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create an account, attaching a (new or existing) institution (Phase 6: auth-enforced)."""
    local_user = get_or_create_local_user(db, _current_user)
    institution = get_or_create_institution(db, account_data.institution_name)
    # Phase 16 — every account belongs to a FamilyMember. The FE
    # is OPTIONAL on the request shape (``family_member_id`` defaults
    # to null in :class:`AccountCreate` for backwards-compat with the
    # post-Phase-7 wire shape) so the BE honours an explicit id when
    # provided (the Accounts page select dropdown) and falls back to
    # the local user's Self row when missing.\n
    # 404 guard: a non-existent family_member_id must NOT silently
    # land as Self (would confuse the user when the FE expected
    # "Spouse" but the row landed under Self). Validate first.
    if account_data.family_member_id is not None:
        from app.models import FamilyMember
        member = (
            db.query(FamilyMember)
            .filter(
                FamilyMember.id == account_data.family_member_id,
                FamilyMember.user_id == local_user.id,
                FamilyMember.is_archived.is_(False),
            )
            .first()
        )
        if member is None:
            raise HTTPException(
                status_code=404,
                detail="Family member not found or archived.",
            )
        family_member_id = member.id
    else:
        # Default to the local user's Self row. Bootstrap here
        # (instead of relying on a prior ``get_or_create_local_user``)
        # so a fresh-DB cold start never 500s on a missing Self FK.
        self_row = get_or_create_family_member_self(db, local_user)
        family_member_id = self_row.id

    account = Account(
        user_id=local_user.id,
        institution_id=institution.id,
        account_name=account_data.account_name,
        account_type=account_data.account_type,
        account_subtype=account_data.account_subtype,
        account_number=account_data.account_number,
        current_balance=account_data.current_balance,
        is_active=True,
        family_member_id=family_member_id,
        # Phase 40 — manual Add Account path. The route layer
        # always stamps ``source='manual'`` regardless of what
        # the FE sends; the upload routes overwrite with
        # ``"imported"`` and Plaid with ``"plaid"`` so the
        # surface stays auto-detected. ``description`` is
        # whatever the user typed in the Add form (None when
        # left empty).
        source=account_data.source or "manual",
        description=account_data.description,
        # Atlas Phase 1 — debt fields for liability accounts.
        interest_rate=account_data.interest_rate,
        credit_limit=account_data.credit_limit,
        minimum_payment=account_data.minimum_payment,
        term_months=account_data.term_months,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Partial update of an account (Phase 7: edit affordance for /accounts).

    Whitelist driven — only fields declared on :class:`AccountUpdate` are
    applied. Identity columns (``id``, ``user_id``, ``institution_id``) are
    intentionally NOT declared so clients cannot escalate or re-tie
    ownership via PUT. Renaming the bank hops through
    :func:`get_or_create_institution` so the FK stays valid.

    Reactivation: send ``{ "is_active": true }`` to flip a soft-deleted
    row (via :func:`DELETE`) back into the list. ``None`` values are
    skipped so partial semantics hold (a field absent in the payload is
    left untouched, not cleared).
    """
    local_user = get_or_create_local_user(db, _current_user)
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == local_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    patch = {k: v for k, v in payload.model_dump().items() if v is not None}

    # Phase 52+ — retroactive sign-flip when account_type crosses the
    # credit / non-credit boundary. The credit-card sign convention
    # (purchases=negative, payments=positive) is the inverse of a
    # checking account (deposits=positive, withdrawals=negative).
    # When the user imports a statement with the wrong type and later
    # corrects it (e.g. Citi PDF auto-detected as "checking" but
    # corrected to "credit_card"), the already-imported transactions
    # retain the WRONG signs from the original import. Flipping them
    # retroactively fixes the stored ledger without requiring a re-import.
    _old_account_type = account.account_type
    _new_account_type = patch.pop("account_type", None)
    _types_flipped = False
    if _new_account_type is not None:
        _old_is_credit = _old_account_type in CREDIT_ACCOUNT_TYPES
        _new_is_credit = _new_account_type in CREDIT_ACCOUNT_TYPES
        if _old_is_credit != _new_is_credit:
            # Crossing the boundary — flip every transaction's sign.
            _txns = (
                db.query(Transaction)
                .filter(Transaction.account_id == account_id)
                .all()
            )
            for _t in _txns:
                _t.amount = -_t.amount
                db.add(_t)
            _types_flipped = True
            _acct_log.getLogger(__name__).info(
                "Account #%d type %r → %r: flipped %d transaction(s) sign",
                account_id, _old_account_type, _new_account_type, len(_txns),
            )
        account.account_type = _new_account_type

    # Phase 16 — validate ``family_member_id`` BEFORE the generic
    # attr-overwrite loop so an attempt to assign an account to a
    # non-existent (or archived) member 404s cleanly. Mirrors the
    # create_account branch.
    if "family_member_id" in patch:
        from app.models import FamilyMember
        member = (
            db.query(FamilyMember)
            .filter(
                FamilyMember.id == patch["family_member_id"],
                FamilyMember.user_id == local_user.id,
                FamilyMember.is_archived.is_(False),
            )
            .first()
        )
        if member is None:
            raise HTTPException(
                status_code=404,
                detail="Family member not found or archived.",
            )
        # Carry the validated id straight into the attr-overwrite
        # loop below (no dead local variable).
        patch["family_member_id"] = member.id

    # Resolve institution FIRST (consumes `institution_name` from the patch)
    # before the generic attr-overwrite loop so we don't try to setattr a
    # non-Account column.
    if "institution_name" in patch:
        name = (patch["institution_name"] or "").strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail="institution_name must be a non-empty string when present.",
            )
        institution = get_or_create_institution(db, name)
        account.institution_id = institution.id
        # Don't carry the now-resolved field into the attr-overwrite loop.
        patch.pop("institution_name")

    for field, value in patch.items():
        if hasattr(account, field):
            setattr(account, field, value)

    db.add(account)
    db.commit()
    db.refresh(account)

    # Phase 52+ — after sign-flip: recalculate the account balance (the
    # sum of all flipped transactions) and re-categorize the affected
    # transactions so any categories assigned during the original import
    # (when the account had the WRONG type) are re-evaluated.
    if _types_flipped:
        recalculate_account_balance(db, account.id)
        db.commit()
        # Re-fetch flipped transactions to re-categorize.
        _flipped_txns = (
            db.query(Transaction)
            .filter(Transaction.account_id == account.id)
            .all()
        )
        if _flipped_txns:
            from app.services.categorizer import categorize_transactions
            _cat, _skip, _conf = categorize_transactions(db, _flipped_txns)
            db.commit()
            _acct_log.getLogger(__name__).info(
                "Account #%d: re-categorized %d transaction(s) after sign-flip",
                account.id, _cat,
            )

    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_account(
    account_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Soft-delete — flip ``is_active=False`` (Phase 7: deactivation affordance).

    Idempotent: a second DELETE on an already-inactive row still returns
    204. Reactivation is via :func:`update_account` with
    ``{"is_active": true}``.

    The row physically stays in ``accounts`` so ``transactions.account_id``
    and ``import_batches.account_id`` FKs remain valid (no cascade). The
    dashboard list endpoint ``GET /api/accounts/`` filters
    ``is_active.is_(True)`` so deactivated accounts stop surfacing.

    404 is returned ONLY when the row genuinely doesn't exist for this
    user — we don't leak existence to other users' rows.
    """
    local_user = get_or_create_local_user(db, _current_user)
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == local_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.is_active:
        account.is_active = False
        db.add(account)
        db.commit()
        db.refresh(account)
    # Idempotent path: already-inactive rows return 204 with no DB write.
    return None


@router.post("/reconcile")
async def reconcile_balances(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Recalculate ``current_balance`` for every active account.

    Safety valve — if a code path ever mutates transactions without
    calling :func:`recalculate_account_balance`, this endpoint lets the
    user repair the drift from the Settings page without touching the DB
    directly.
    """
    local_user = get_or_create_local_user(db, _current_user)
    updated = recalculate_all_user_balances(db, local_user.id)
    db.commit()
    return {"reconciled": updated}
