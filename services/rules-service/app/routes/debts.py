"""Atlas Phase 2 — Debts summary endpoint.

Aggregates debt accounts with APR, minimum payments, and utilization
for the Debts page.

Endpoints:
- GET /api/debts/summary — debt aggregation with blended APR
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_user
from app.account_types import CREDIT_ACCOUNT_TYPES
from app.database import get_db
from app.models import Account
from app.routes.shared import get_or_create_local_user

router = APIRouter(prefix="/api/debts", tags=["debts"])


@router.get("/summary")
async def get_debts_summary(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Debt aggregation with APR, min payments, and utilization."""
    local_user = get_or_create_local_user(db, _current_user)

    debt_accounts = (
        db.query(Account)
        .filter(
            Account.user_id == local_user.id,
            Account.is_active.is_(True),
            Account.account_type.in_(set(CREDIT_ACCOUNT_TYPES)),
        )
        .all()
    )

    debts = []
    total_debt = 0.0
    weighted_apr_sum = 0.0
    total_minimum = 0.0

    for acc in debt_accounts:
        balance = abs(acc.current_balance)
        total_debt += balance

        interest_rate = acc.interest_rate
        minimum_payment = acc.minimum_payment or 0.0
        total_minimum += minimum_payment

        # Weighted APR for blended calculation
        if interest_rate and interest_rate > 0:
            weighted_apr_sum += balance * (interest_rate / 100.0)

        # Credit card utilization
        utilization = None
        if acc.account_type == "credit_card" and acc.credit_limit and acc.credit_limit > 0:
            utilization = round((balance / acc.credit_limit) * 100, 1)

        debts.append({
            "account_id": acc.id,
            "account_name": acc.account_name,
            "account_type": acc.account_type,
            "balance": round(balance, 2),
            "interest_rate": interest_rate,
            "minimum_payment": minimum_payment,
            "credit_limit": acc.credit_limit,
            "term_months": acc.term_months,
            "utilization": utilization,
        })

    # Sort by balance descending
    debts.sort(key=lambda d: -d["balance"])

    blended_apr = round((weighted_apr_sum / total_debt * 100) if total_debt > 0 else 0, 2)

    return {
        "total_debt": round(total_debt, 2),
        "blended_apr": blended_apr,
        "total_monthly_minimum": round(total_minimum, 2),
        "debts": debts,
    }
