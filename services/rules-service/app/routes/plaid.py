"""Phase 6 lift — /api/plaid/ endpoints (auth-aware, schema-centralized).

Phase 4 lifted the wealthiq ``backend/app/routes/plaid.py`` (§4 item 19, §10
decision 1). Phase 6 fixes the Plaid schema duplication LEFT OVER FROM
PHASE 5 \u2014 the route had inline ``CreateLinkTokenResponse`` and
``ExchangePublicTokenRequest`` classes; Phase 5 added the canonical
``PlaidLinkTokenResponse`` + ``PlaidExchangeRequest`` to
``app/schemas/__init__.py``. Phase 6 makes the route import the
central schemas (DRY) and the route's inline classes go away.

Endpoint-design choice (Phase 4 + \u00a710 decision 1):

- The two endpoints stay as 501 ``NotImplemented`` shape when
  ``PLAID_CLIENT_ID`` is unset, with HTTP 501 NOT 400. 501 is the
  semantically-correct code for an endpoint that is wired and
  reachable but whose underlying integration is intentionally not
  configured in this deployment. Phase 7 will replace the body with a
  real Plaid SDK call \u2014 the route already imports the SDK lazily so
  the failure is isolated.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models import Account
from app.routes.shared import (
    get_or_create_family_member_self,
    get_or_create_institution,
    get_or_create_local_user,
)
from app.schemas import PlaidExchangeRequest, PlaidLinkTokenResponse

router = APIRouter(prefix="/api/plaid", tags=["plaid"])


def _assert_plaid_configured() -> None:
    """Raise 501 if Plaid is not configured. Centralised so both
    endpoints share the same error path + the same user-facing message
    + the same audit trail (Phase 7 wiring-on will reuse this)."""
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise HTTPException(
            status_code=501,
            detail="Plaid not configured (set PLAID_CLIENT_ID and PLAID_SECRET); "
            "use /api/imports/upload for CSV/PDF statement ingest",
        )


@router.post("/create_link_token", response_model=PlaidLinkTokenResponse)
async def create_link_token(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create a Plaid Link token for the frontend (Phase 6: auth-enforced).

    Requires ``PLAID_CLIENT_ID`` + ``PLAID_SECRET`` env vars. Per
    decision 1, this endpoint is one of several ingest paths (alongside
    CSV/PDF statement uploads); the choice between them is made by the
    user.
    """
    _assert_plaid_configured()

    try:
        from plaid import Client
    except Exception:
        raise HTTPException(status_code=500, detail="Plaid SDK not installed")

    client = Client(
        client_id=settings.plaid_client_id,
        secret=settings.plaid_secret,
        environment=settings.plaid_env,
    )

    result = client.LinkToken.create(
        {
            "user": {"client_user_id": settings.local_user},
            "client_name": settings.app_name,
            "products": ["transactions"],
            "country_codes": ["US"],
            "language": "en",
        }
    )

    link_token = result.get("link_token")
    if not link_token:
        raise HTTPException(status_code=500, detail="Failed to create link token")
    return PlaidLinkTokenResponse(link_token=link_token)


@router.post("/exchange_public_token")
async def exchange_public_token(
    req: PlaidExchangeRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Exchange Plaid public_token for access_token, fetch accounts, persist locally
    (Phase 6: auth-enforced, schema-centralized)."""
    _assert_plaid_configured()

    try:
        from plaid import Client
    except Exception:
        raise HTTPException(status_code=500, detail="Plaid SDK not installed")

    client = Client(
        client_id=settings.plaid_client_id,
        secret=settings.plaid_secret,
        environment=settings.plaid_env,
    )

    try:
        exchange_resp = client.Item.public_token.exchange(req.public_token)
        access_token = exchange_resp.get("access_token")
        item_id = exchange_resp.get("item_id")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange public token: {e}")

    try:
        accounts_resp = client.Accounts.get(access_token)
        accounts = accounts_resp.get("accounts", [])
    except Exception:
        accounts = []

    local_user = get_or_create_local_user(db, _current_user)
    # Phase 16 — every Plaid-linked account owns a family_member_id
    # NOT NULL FK. Bootstrap the local user's Self row ONCE before the
    # loop so each Plaid account lands under Self (matching the
    # cold-start behaviour of POST /api/accounts/ + the imports route's
    # lazy "Imported Statements" account creation). Calling this
    # inside the loop would be idempotent but wastes a SELECT round-trip.
    self_row = get_or_create_family_member_self(db, local_user)

    created_accounts = []
    for acct in accounts:
        name = acct.get("name") or acct.get("official_name") or "Plaid Account"
        acct_type = acct.get("type", "other")
        subtype = acct.get("subtype")
        balance = acct.get("balances", {}).get("current") or 0.0

        inst_name = f"Plaid Institution ({item_id})"
        institution = get_or_create_institution(db, inst_name, plaid_id=item_id)

        account = Account(
            user_id=local_user.id,
            institution_id=institution.id,
            account_name=name,
            account_type=acct_type,
            account_subtype=subtype,
            current_balance=balance,
            is_active=True,
            family_member_id=self_row.id,
            # Phase 40 — Plaid-linked account. Distinct from
            # ``source='imported'`` so a future "Re-sync from
            # Plaid" affordance can filter to plaid rows only.
            # ``inst_name`` is the per-link institution string
            # (``Plaid Institution (<item_id>)``) so the user
            # can tell at a glance which Plaid link created
            # which account.
            source="plaid",
            description=f"Plaid-linked: {inst_name}",
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        created_accounts.append(account)

    return {"created": len(created_accounts)}
