"""Phase 4 + Phase 7 shared helpers used by every route module.

Lift provenance: the legacy WealthIQ shared-route module (see
``docs/wealthiq-merge-plan.md`` §4 Reuse Map item 13). One substantive change
plus a Phase 7 fix that closes the duplicate-user bug:

Substantive change (per ``docs/wealthiq-merge-plan.md`` §10 decision 4):

- ``get_or_create_demo_user`` (always returns ``demo@example.com``) is
  replaced by ``get_or_create_local_user(db, sub)`` — looks up by the
  **identity key**, which after Phase 7 is the JWT ``sub`` claim
  (``settings.local_user``, default ``"alex"``). All Phase 4+ routes pass
  ``_current_user`` (the decoded JWT ``sub``) here.

Phase 7 fix (the cause of the Settings-page "Network Error"): prior to
Phase 7 this helper looked up ``WHERE email = sub``. The Settings PUT
overwrites the local user's row with a new ``email``, so the NEXT
request's lookup ``WHERE email = "alex"`` no longer matches the
original row, the helper silently inserts a SECOND user row, and every
PUT thereafter collides on ``users.email UNIQUE``. Phase 7 adds the
``local_user_sub`` column with a UNIQUE index and switches the lookup
key to that column. ``email`` stays UNIQUE for display parity, but the
identity/lookup path no longer depends on it.

Adaptations:

- The single User row carries ``hashed_password`` (still in the schema
  for Phase 2 lift-contract parity) but the value is a textual
  placeholder (``"auth-via-jwt-cookie-no-password"``). Nothing in the
  JWT-cookie path hashes a password; the column is kept only so the
  Phase 2 ORM shape still matches the lift source.
- ``get_or_create_institution`` lifted verbatim.
"""
import json as _json
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Institution, User

# Module-level logger used by :func:`forward_to_finlynq` so operators
# grepping ``.run/backend.log`` for ``Finlynq upstream`` see the
# envelope decision. Bound at import time, before any forwarder
# call; safe because ``logging.getLogger(__name__)`` is the standard
# pattern and never raises.
_logger = logging.getLogger(__name__)


def forward_detail(response: httpx.Response) -> str:
    """Best-effort extraction of an upstream error detail string.

    Used by every Finlynq-httpx forwarder in ``app/routes/`` to
    surface a meaningful error body to the FE. The shape MUST be
    stable (always returns a ``str``) because every caller invokes
    this inside the ``detail=`` arg of an ``HTTPException(...)``
    constructor — an exception leaking out of this function would
    surface as a misleading 500 instead of the real upstream cause.

    Robustness:
    - ``JSONDecodeError`` (``ValueError``) → fall back to
      ``response.text[:200]`` so a HTML / plain-text 4xx body
      (uvicorn 502 cold-start HTML, plain-text 401) doesn't crash.
    - ``TypeError`` from ``json.dumps`` on exotic body types
      (datetime, Decimal, MagicMock from a test stub) → fall back
      to ``str(body)[:200]``.
    - Any other unexpected exception → fall back to
      ``f"HTTP {response.status_code}"`` so the caller always gets
      a usable detail.

    Phase-F2 #1 round-1: promoted from ``categories.py``'s
    underscore-prefixed ``_forward_detail`` to a public helper so
    any forwarder can import it without a private cross-module
    import.
    """
    status = response.status_code
    try:
        body = response.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
        if body is None or isinstance(
            body, (str, int, float, list, dict, bool)
        ):
            try:
                return _json.dumps(body)[:200]
            except (TypeError, ValueError):
                return str(body)[:200]
        return f"HTTP {status}"
    except ValueError:  # JSONDecodeError IS-A ValueError subclass
        # ``response.text`` access can legitimately raise
        # ``AttributeError`` (closed stream) or ``RuntimeError``
        # (``httpx.ResponseNotRead`` IS-A RuntimeError when the body
        # stream was never read). Catch those, not the broad
        # Exception — so a real bug like ``KeyError('detail')``
        # still surfaces.
        try:
            text = response.text
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return f"HTTP {status}"
        return (text or "")[:200] or f"HTTP {status}"
    except (ValueError, TypeError, AttributeError, RuntimeError):
        # ``ValueError``     → ``JSONDecodeError`` on non-JSON body
        # ``TypeError``       → ``json.dumps`` on exotic body types
        #                     (datetime, Decimal, MagicMock from
        #                     test stubs)
        # ``AttributeError``  → ``response.<attr>`` typos
        # ``RuntimeError``    → ``httpx.ResponseNotRead`` /
        #                       ``httpx.ResponseStreamClosed``
        #                       (real-world cold-start streaming
        #                       glitches from Finlynq)
        # NOT in this tuple: ``KeyError`` (``body["detail"]`` typo),
        # ``NameError`` (typo in module), ``OSError`` / ``IOError``
        # (file-handle issues that would mask a real bug).
        return f"HTTP {status}"


# Return contract for :func:`forward_to_finlynq`. Enforced as a
# TypedDict so the route modules can read ``result["status_code"]`,
# ``result["detail"]``, and ``result["body"]`` without ``mypy`` flags.
#   - ``status_code``: the status the calling route must raise as an
#     ``HTTPException(status_code=...)`` (or return on 2xx success).
#   - ``detail``: the FE-facing string for non-2xx cases.
#   - ``body``: the upstream parsed JSON body — only set on 2xx so
#     the caller can hand it to ``Pydantic(**body)`` directly.

from typing import Any, Optional, TypedDict


class ForwardResult(TypedDict):
    """Typed dict shape returned by :func:`forward_to_finlynq`.

    ``status_code`` is the status the calling route should
    raise/return; ``detail`` is the FE-facing string for non-2xx
    cases; ``body`` is the upstream JSON parsed object, set on 2xx
    so the caller can hand it to ``Pydantic(**body)`` directly.
    """

    status_code: int
    detail: str
    body: Optional[Any]


def resolve_fc_token(
    fc_session: Optional[str] = None,
    authorization: Optional[str] = None,
) -> Optional[str]:
    """Extract the JWT token from either the ``fc_session`` cookie or the
    ``Authorization: Bearer <token>`` header.

    The FE's AuthBootstrapProvider stores the token in localStorage AND
    sets it as an HttpOnly cookie (``fc_session``). When the cookie is
    absent (e.g. a fresh tab before cookie-settled, or a CLI/test client
    using Bearer), this helper falls back to the Authorization header so
    Finlynq always receives a valid JWT.

    Priority: cookie first (matches the historical forwarder behavior),
    then Authorization header.
    """
    if fc_session:
        return fc_session
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        return token or None
    return None


# 4xx bucket split used by every Finlynq forwarder. The two
# mutually-exclusive lists pin the cross-service wire contract:
#   - 401 / 403: ALWAYS a downstream config drift (Phase F2 #2,
#     fixes the "Session expired" flash on auth-mismatch). The FE
#     shows 'Downstream service is unavailable. Your session is
#     fine…' — the user's cookie is valid locally.
#   - 400 / 409 / 422 / 429: USER-fixable errors from Finlynq
#     (e.g. duplicate CSV row, rate-limited). Forwarded verbatim
#     so the FE shows the actionable upstream detail (e.g.
#     "category exists" instead of a generic 502).
# Anything NOT in either list is forward-verbatim with the upstream
# status code (covers future status codes that don't fit the drift
# bucket). Belt-and-braces + DRY: every forwarder in
# ``routes/dashboard.py/imports.py/categories.py/analyst_ratings.py``
# routes through this check; a future status code gets classified by
# ONE helper instead of N parallel if/else chains.
DRIFT_SAFE_4XX_AUTH = frozenset({401, 403})
DRIFT_SAFE_4XX_USER = frozenset({400, 409, 422, 429})


def _drift_safe_4xx_mapping(upstream_status: int) -> Optional[int]:
    """Map a Finlynq 4xx status to the rules-service envelope.

    Returns the mapped status, or ``None`` if it's not a recognized
    4xx bucket (in which case the caller falls through to verbatim).

    - upstream in ``DRIFT_SAFE_4XX_AUTH`` -> rules-service emits 502
      Bad Gateway (Phase F2 #2 fix — kills the "Session expired"
      flash on JWT_SECRET drift between rules-service and Finlynq).
    - upstream in ``DRIFT_SAFE_4XX_USER`` -> rules-service verbatim
      (user-fixable errors: duplicate row, bad column, rate limit).
    - Anything else (e.g. 418, 451) -> None (verbatim).
    """
    if upstream_status in DRIFT_SAFE_4XX_AUTH:
        return 502
    if upstream_status in DRIFT_SAFE_4XX_USER:
        return upstream_status
    return None


async def forward_to_finlynq(
    method: str, path: str,
    *,
    json: Optional[dict] = None,
    fc_session: Optional[str] = None,
    authorization: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> ForwardResult:
    """Thin httpx forwarder with the Phase F2 #2 drift-safe envelope.

    Every Finlynq forwarder in ``routes/{dashboard,imports,categories,
    analyst_ratings}.py`` calls this helper so the cross-service 4xx
    policy is enforced in ONE place. A future "Phase X" change that
    tweaks the envelope touches this single function instead of N
    parallel if/else chains in the route modules.

    Returns a :class:`ForwardResult` typed dict. Callers MUST raise
    ``HTTPException(status_code=result["status_code"], detail=
    result["detail"])`` directly when ``status_code >= 400``; on
    2xx the body is pre-decoded for the caller's Pydantic RO.

    The httpx-asyncio dependency matches the previous ad-hoc
    ``async with httpx.AsyncClient(...) as client: ...`` shape so
    this is a drop-in replacement for the older per-route helpers.
    """
    url = f"{settings.finlynq_base_url}{path}"
    # Resolve token from cookie OR Authorization header so Finlynq
    # always receives a valid JWT (the FE sends Bearer from localStorage;
    # the cookie may be absent on fresh tabs or CLI clients).
    token = resolve_fc_token(fc_session, authorization)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            r = await client.request(
                method, url, json=json,
                cookies={"fc_session": token} if token else None,
            )
    except httpx.TimeoutException as _exc:
        # Network-layer timeout — translate to OUR 502 so the FE shows
        # "downstream unavailable" (the Phase F2 #2 friendly banner)
        # rather than a generic "Internal server error: TimeoutException"
        # that the global Exception handler would otherwise surface.
        # Without this guard, a hung Finlynq leaks as a 5xx-shaped
        # failure that the FE classifier maps to ``category=server``
        # — defeating the F2 #2 drift-safe envelope.
        _logger.warning(
            "Finlynq upstream timed out (%ss) on %s %s -> 502",
            timeout_seconds, method, path,
        )
        return {
            "status_code": 502,
            "detail": (
                f"Finlynq upstream timed out after {timeout_seconds}s on "
                f"{method} {path}. Downstream service unreachable; your "
                f"local session is fine. ({type(_exc).__name__})"
            ),
            "body": None,
        }
    except httpx.ConnectError as _exc:
        # Same rationale as TimeoutException: an unreachable Finlynq
        # (port not open) is a downstream-class failure and must land
        # in the same envelope. Translating here keeps the FE's
        # downstream-unavailable bucket uniform.
        _logger.warning(
            "Finlynq upstream connect error on %s %s -> 502: %s",
            method, path, _exc,
        )
        return {
            "status_code": 502,
            "detail": (
                f"Finlynq upstream unreachable on {method} {path}. "
                f"Downstream service unavailable; your local session is "
                f"fine. ({type(_exc).__name__}: {_exc})"
            ),
            "body": None,
        }
    except httpx.RequestError as _exc:
        # Catch-all for the rest of the httpx exception family
        # (``RemoteProtocolError`` mid-response, ``ReadError`` on a
        # chunked-transfer glitch, ``HTTPStatusError`` if anyone in
        # the future calls ``client.get(..., raise_for_status=True)``).
        # Same envelope as the two specific cases above — the
        # downstream bucket is uniform on the FE.
        _logger.warning(
            "Finlynq upstream %s on %s %s -> 502: %s",
            type(_exc).__name__, method, path, _exc,
        )
        return {
            "status_code": 502,
            "detail": (
                f"Finlynq upstream {type(_exc).__name__} on {method} "
                f"{path}. Downstream service unavailable; your local "
                f"session is fine."
            ),
            "body": None,
        }

    if 200 <= r.status_code < 300:
        try:
            return {"status_code": r.status_code, "detail": "", "body": r.json()}
        except ValueError as _exc:
            # 2xx-non-JSON body (Finlynq cold-start ``pong`` text, or
            # a chunked-transfer glitch that delivered an empty 200).
            # Surface as 502 so a FE never sees the raw upstream body.
            return {
                "status_code": 502,
                "detail": (
                    f"Finlynq upstream returned HTTP {r.status_code} but body "
                    f"is not JSON. Upstream response: {forward_detail(r)}"
                ),
                "body": None,
            }

    # Non-2xx — apply the drift-safe envelope.
    if r.status_code >= 500:
        return {
            "status_code": 502,
            "detail": (
                f"Finlynq upstream returned HTTP {r.status_code} on "
                f"{method} {path}. Upstream response: {forward_detail(r)}"
            ),
            "body": None,
        }

    if 300 <= r.status_code < 400:
        # 3xx is unexpected on GET round-trips and is treated as 502
        # so a FE never sees a stack-traced redirect body.
        return {
            "status_code": 502,
            "detail": (
                f"Finlynq upstream returned HTTP {r.status_code} redirect on "
                f"{method} {path}. Upstream response: {forward_detail(r)}"
            ),
            "body": None,
        }

    # 4xx — apply the split. Logging the upstream status here so
    # operators grepping ``.run/backend.log`` for ``finlynq
    # upstream`` see the bucket the envelope mapped it to.
    mapped = _drift_safe_4xx_mapping(r.status_code)
    if mapped is not None:
        bucket = "drift" if mapped == 502 else "verbatim"
        _logger.warning(
            "Finlynq upstream %d on %s %s -> mapped to %d (%s)",
            r.status_code, method, path, mapped, bucket,
        )
        if mapped == 502:
            return {
                "status_code": 502,
                "detail": (
                    f"Finlynq upstream returned HTTP {r.status_code} on "
                    f"{method} {path}. This is a downstream config drift "
                    f"(commonly JWT_SECRET mismatch); your local session "
                    f"is fine. Upstream response: {forward_detail(r)}"
                ),
                "body": None,
            }
        # user-fixable 4xx — verbatim
        return {
            "status_code": mapped,
            "detail": forward_detail(r),
            "body": None,
        }

    # Unknown 4xx (e.g. 418/451) — verbatim with raw upstream detail.
    return {
        "status_code": r.status_code,
        "detail": forward_detail(r),
        "body": None,
    }


def recalculate_account_balance(db: Session, account_id: int) -> float:
    """Recalculate ``Account.current_balance`` from the split ``debit`` /
    ``credit`` Transaction columns using a TYPE-AWARE formula.

    This is the single source of truth for account balances. Every code path
    that mutates transactions (import, delete-batch, delete-all-data,
    the alembic ``d1e2f3a4b5c6`` backfill) MUST call this afterwards so
    the stored balance stays in sync with the ledger.

    Convention (Phase 52+):
      - depository accounts (checking / savings / debit_card / other):
            current_balance = SUM(credit) - SUM(debit)  (positive = owned)
      - credit accounts (credit_card / loan / mortgage):
            current_balance = SUM(debit)  - SUM(credit)  (positive = owed)

    The shared ``amount`` column is preserved as ``credit - debit``
    (universal accounting convention, sign=positive for income /
    payment, sign=negative for expense / purchase) so the
    historical ``SUM(amount)`` read path still works for
    SINGLE-ACCOUNT balance lookups. The type-aware formulas
    here are what the dashboard and the cross-account totals
    use because a purchase-and-payment on a credit card has
    an ABSOLUTE net debt that the SUM(amount) variant REVERSES
    (purchase = -50, payment = +25, SUM = -25 but the actual
    debt owed is +25, sign-flipped by the formula above).

    Returns the new balance (0.0 if no transactions remain or
    both sums are NULL on a dev-seed account with no rows).
    """
    from sqlalchemy import func

    from app.account_types import CREDIT_ACCOUNT_TYPES
    from app.models import Account, Transaction

    # Two-step lookup: resolve the account row first (we need
    # it anyway to write back ``current_balance``), then pick the
    # right SUM formula based on the account's type. Avoids the
    # subquery round-trip the previous implementation used (which
    # was a separate SELECT against the accounts table for every
    # balance recompute). The account lookup is O(1) (PK index)
    # so the combined cost is one PK fetch + one indexed SUM.
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        return 0.0
    is_credit = account.account_type in CREDIT_ACCOUNT_TYPES
    # Phase 52+ bug fix — was ``Transaction.credit - Transaction.debit``
    # directly. SQL NULL arithmetic propagates NULL per row: a row with
    # only ``debit`` populated (a purchase on a credit card, for example)
    # evaluates ``NULL - 50 = NULL`` and ``SUM(NULL...) = NULL``;
    # ``COALESCE(SUM(...), 0.0)`` then silently rounds to ``0.0`` even
    # though every transaction is well-populated. Wrapping each side
    # in ``COALESCE(col, 0.0)`` keeps the per-row arithmetic numerical
    # so the aggregate SUM resolves to the actual signed balance.
    expr = (
        func.coalesce(Transaction.debit, 0.0) - func.coalesce(Transaction.credit, 0.0)
        if is_credit
        else func.coalesce(Transaction.credit, 0.0) - func.coalesce(Transaction.debit, 0.0)
    )
    total = (
        db.query(func.coalesce(func.sum(expr), 0.0))
        .filter(Transaction.account_id == account_id)
        .scalar()
    )
    new_balance = float(total or 0.0)
    account = db.query(Account).filter(Account.id == account_id).first()
    if account:
        old = account.current_balance
        account.current_balance = new_balance
        db.add(account)
        if float(old or 0) != new_balance:
            _logger.info(
                "Recalculated balance for account %d (%s, type=%s): %.2f -> %.2f",
                account_id, account.account_name, account.account_type,
                float(old or 0), new_balance,
            )
    return new_balance


def recalculate_all_user_balances(db: Session, user_id: int) -> int:
    """Recalculate ``current_balance`` for every account owned by a user.

    Used by the delete-all-data endpoint and as a repair utility.
    Returns the number of accounts updated.
    """
    from app.models import Account

    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    for account in accounts:
        recalculate_account_balance(db, account.id)
    if accounts:
        db.flush()
    return len(accounts)


def get_or_create_local_user(db: Session, sub: str) -> User:
    """Look up the per-request local user by JWT ``sub``; create on first request.

    The returned ``User`` row is THE local user for the whole request
    lifecycle. JWT-auth-scoped, not request-scoped, so any FK the caller
    writes (``account.user_id``, ``import_batch.user_id``, ...) is
    stable across requests even if ``users.email`` changes.

    On create, the row's ``email`` mirrors ``sub`` (so the dev seed
    matches the historical ``email="alex"`` invariant older tests pin),
    and the row's ``full_name`` is derived from ``sub`` for the same
    reason. A future multi-user rework should swap both for proper
    self-service edit-on-creation as part of Phase 8+.
    """
    user = db.query(User).filter(User.local_user_sub == sub).first()
    if not user:
        user = User(
            local_user_sub=sub,
            email=sub,
            hashed_password="auth-via-jwt-cookie-no-password",
            full_name=sub.split("@", 1)[0].title() or sub,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# Defensive ceiling on the per-request bootstrap loop. A pathological
# state (e.g. an OwnershipPromise corruption) would otherwise spin
# forever; a non-zero bound surfaces the bug as a logged error.
FamilyMemberBootstrapIterationMax = 5


def get_or_create_family_member_self(db: Session, user: User) -> "FamilyMember":
    """Idempotently bootstrap the local user's Self family-member row.

    Called by every Phase 16 route that needs a Self member to exist
    (:func:`app.routes.family_members.list_family_members`,
    :func:`app.routes.accounts.create_account`) so a brand-new user
    has a Self row before the first Account POST lands. The Self row
    is the default ``family_member_id`` for any Account without an
    explicit member, so the Account.family_member_id FK is
    satisfiable without a race window.

    Lookup is via ``WHERE is_self=True`` (not WHERE name='Self') so a
    user who later renames their Self row to e.g. "Alex" via
    ``PUT /api/family-members/{self_id}`` does NOT spawn a duplicate
    Self row on the next ``get_or_create_local_user`` call.

    Idempotent: a second call returns the EXISTING Self row, no commit.
    A pathological race (two requests landing at the same instant
    before the first commits) is bounded by :data:`FamilyMemberBootstrapIterationMax`
    so the function can never spin forever.
    """
    # Imported here to break the import cycle: family_member.py
    # imports Base from app.database; routes/shared.py imports
    # FamilyMember indirectly via this function. Keeping the import
    # local avoids the cycle without sacrificing public availability.
    from app.models import FamilyMember

    for _ in range(FamilyMemberBootstrapIterationMax):
        self_row = (
            db.query(FamilyMember)
            .filter(
                FamilyMember.user_id == user.id,
                FamilyMember.is_self.is_(True),
            )
            .first()
        )
        if self_row is not None:
            return self_row
        # No Self row yet — insert one. Use the user's full_name
        # when present (welcome / rename semantics) but fall back to
        # the literal "Self" so a stock dev seed (sub="alex",
        # full_name="Alex") agrees with the historical convention
        # that pre-Phase-16 UI code expects.
        seed_name = (user.full_name or "").strip() or "Self"
        new_self = FamilyMember(
            user_id=user.id,
            name=seed_name,
            color="#10b981",  # canonical Self emerald chip
            # ``relationship='Self'`` is the locked value for the
            # bootstrap row. The route layer in ``family_members.py``
            # force-overrides any PUT attempt on this column so
            # clients can NEVER promote a Spouse to ``relationship==
            # 'Self'`` (defence-in-depth — the FE also disables the
            # dropdown, but if a user races a rename via a raw curl
            # the BE still won't let them through).
            relationship="Self",
            is_self=True,
            is_archived=False,
        )
        db.add(new_self)
        try:
            db.commit()
            db.refresh(new_self)
            return new_self
        except SQLAlchemyIntegrityError:
            # Raced: another request inserted a Self row in the
            # gap between our SELECT and INSERT. Roll back this
            # attempt and re-SELECT — the winner's row is what we
            # want to return.
            db.rollback()
            continue
    # Exhausted the iteration budget — surface so the test or the
    # operator sees a real exception instead of an infinite loop.
    raise RuntimeError(
        f"get_or_create_family_member_self failed after "
        f"{FamilyMemberBootstrapIterationMax} iterations for user "
        f"{user.id!r} — likely a state corruption, not a race."
    )


def get_or_create_institution(
    db: Session, institution_name: str, plaid_id: Optional[str] = None
) -> Institution:
    """Look up (or create) an institution by name; attach ``plaid_id`` if newly provided."""
    institution = db.query(Institution).filter(Institution.name == institution_name).first()
    if not institution:
        institution = Institution(name=institution_name, plaid_id=plaid_id)
        db.add(institution)
        db.commit()
        db.refresh(institution)
        return institution

    if plaid_id and not institution.plaid_id:
        institution.plaid_id = plaid_id
        db.add(institution)
        db.commit()
        db.refresh(institution)
    return institution
