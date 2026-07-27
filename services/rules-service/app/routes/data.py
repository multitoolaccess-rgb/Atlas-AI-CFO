"""Data management — ``DELETE /api/data`` (auth-enforced).

Provides a single nuke-orbit endpoint that hard-deletes ALL financial
data for the local user while preserving the user profile, categories,
and institutions (those are reference data, not user-generated content).

Deletion order respects FK constraints:

1. ``transactions``     — leaf (FK to accounts, import_batches, categories)
2. ``import_batches``   — FK to accounts, users
3. ``budgets``          — FK to users, categories
4. ``holdings``         — FK to accounts (Phase 39, added Phase 52)
5. ``goals``            — FK to users
6. ``accounts``         — FK to users, institutions

What survives:
- ``users`` row         — the profile (name, email, preferences)
- ``categories`` rows   — the taxonomy (shared reference data)
- ``institutions`` rows — the bank names (shared reference data)

Why hard-delete instead of soft-archive:
This is a "factory reset" action. The user explicitly confirms via a
2-step modal in the Settings page. Soft-archiving would leave ghost
rows that bloat every query's filter clause.
"""
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Account, Budget, Goal, Holding, ImportBatch, Transaction
from app.routes.shared import get_or_create_local_user

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])


@router.delete("/", status_code=status.HTTP_200_OK)
async def delete_all_data(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Hard-delete ALL financial data for the local user.

    Returns a JSON summary of deleted row counts so the FE can render
    a confirmation toast ("Deleted 523 transactions, 4 batches, ...").

    The user profile, categories, and institutions are intentionally
    preserved — they're reference data, not user-generated content.
    """
    local_user = get_or_create_local_user(db, _current_user)

    # 1. Transactions (leaf — FK to accounts, import_batches, categories)
    # Two-pass safety net: first delete by user's accounts, then by user's
    # import batches. In a single-user local-first app this is belt-and-
    # suspenders, but it catches any orphaned rows whose account_id was
    # nulled or points at a stale FK (the codebase has no ondelete=CASCADE).
    user_account_ids = db.query(Account.id).filter(Account.user_id == local_user.id)
    user_batch_ids = db.query(ImportBatch.id).filter(ImportBatch.user_id == local_user.id)
    deleted_txns = (
        db.query(Transaction)
        .filter(
            (Transaction.account_id.in_(user_account_ids)) |
            (Transaction.import_batch_id.in_(user_batch_ids))
        )
        .delete(synchronize_session=False)
    )

    # 2. Import batches (FK to accounts, users)
    deleted_batches = (
        db.query(ImportBatch)
        .filter(ImportBatch.user_id == local_user.id)
        .delete(synchronize_session=False)
    )

    # 3. Budgets (FK to users, categories)
    deleted_budgets = (
        db.query(Budget)
        .filter(Budget.user_id == local_user.id)
        .delete(synchronize_session=False)
    )

    # 4. Holdings (FK to accounts — delete BEFORE accounts to avoid
    #    FK violations. Added Phase 52; the holdings table was created
    #    in Phase 39 but never plumbed into delete-all-data).
    deleted_holdings = (
        db.query(Holding)
        .filter(Holding.account_id.in_(user_account_ids))
        .delete(synchronize_session=False)
    )

    # 5. Goals (FK to users)
    deleted_goals = (
        db.query(Goal)
        .filter(Goal.user_id == local_user.id)
        .delete(synchronize_session=False)
    )

    # 6. Accounts (FK to users, institutions)
    deleted_accounts = (
        db.query(Account)
        .filter(Account.user_id == local_user.id)
        .delete(synchronize_session=False)
    )

    db.commit()

    _logger.info(
        "Deleted all data for user %s: %d transactions, %d batches, "
        "%d holdings, %d budgets, %d goals, %d accounts",
        local_user.local_user_sub,
        deleted_txns, deleted_batches, deleted_holdings,
        deleted_budgets, deleted_goals, deleted_accounts,
    )

    return {
        "deleted_transactions": deleted_txns,
        "deleted_import_batches": deleted_batches,
        "deleted_holdings": deleted_holdings,
        "deleted_budgets": deleted_budgets,
        "deleted_goals": deleted_goals,
        "deleted_accounts": deleted_accounts,
    }
