"""Finlynq FastAPI app — Phase F4 ship target.

Phase-F4 round-up changes (after code-reviewer feedback):

1. **CORS-aware exception handlers**: registers a JSON+CORS-aware
   handler for ``sqlalchemy.exc.IntegrityError`` (HTTP 409, stable
   contract) AND a generic handler for unhandled ``Exception``
   (HTTP 500, stable ``{"detail": ...}`` shape). Mirrors
   rules-service's contract verbatim so the cross-service forwarder
   at rules-service's /api/categories/ sees a uniform
   ``r.json()["detail"]`` shape regardless of which service's
   surface raised.

2. **fcntl.flock multi-worker guard on the seed loop**: uvicorn's
   multi-worker deployment would race on the
   INSERT-IF-NOT-EXISTS path in ``seed_default_categories``. The
   lock matches the pattern rules-service uses for its alembic
   upgrade-on-boot hook — POSIX-portable, idempotent on Windows
   fallback.

3. **stress-import cleanup**: app.models no longer carries the
   ORM models Phase-F5 lifts (User/Account/Goal/Transaction) — keep
   the F4 surface minimal so conftest loads cleanly. F5 imports
   the rest from rules-service via ``sys.path`` injection OR copies
   them verbatim (decision deferred to F5 work).
"""
import fcntl
import logging
import os
from typing import List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import Base, SessionLocal, engine  # noqa: F401 — registers models
from app.routes.categorize import categories_router, router as categorize_router
from app.routes.health import router as health_router
from app.routes.parse import router as parse_router
from app.routes.projection_state import router as projection_state_router
from app.routes.state import router as state_router
from app.services.categorizer import seed_default_categories

LOG = logging.getLogger("uvicorn.error")

_ALLOWED_CORS_ORIGINS = {
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
    "http://127.0.0.1:3001",
}


def _cors_json(request: Request, status_code: int, detail: str) -> JSONResponse:
    """Build a JSON response with CORS headers manually attached — same
    rationale as rules-service's _cors_json: Starlette runs exception
    handlers BEHIND CORSMiddleware so a bare handler response would
    bypass the CORS layer and the browser would strip the response.

    This is the cross-service forwarder's primary error-evelope
    contract — see rules-service/app/main.py for the loader.
    """
    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if origin in _ALLOWED_CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=headers,
    )


app = FastAPI(
    title="Finlynq",
    version=settings.app_version,
    description=(
        "Canonical source of truth for portfolio + transactions per "
        "docs/master-plan.md end-state vision. Phase-F4 ship target "
        "lifts /categorize + /categories against the canonical "
        "``categories`` table. Phase-F5 lifts /state aggregates."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_ALLOWED_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Phase-F4 round-up hardening: a global IntegrityError envelope
    for F5+ tables the route handlers don't explicitly map (User,
    Account, Goal). Same shape as rules-service: HTTP 409 + stable
    detail; full traceback stays in server log."""
    LOG.warning("IntegrityError on %s %s: %s", request.method, request.url.path, exc)
    return _cors_json(
        request,
        status_code=409,
        detail="A record with that value already exists.",
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Phase-F4 round-up hardening: last-resort 500 envelope. The
    forwarder at rules-service's /api/categories/ propagates
    `r.json()["detail"]` verbatim — without this handler Finlynq
    would emit FastAPI's bare "Internal Server Error" body which the
    cross-service forwarder would treat as a parse error.
    """
    LOG.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _cors_json(
        request,
        status_code=500,
        detail=f"Internal server error: {type(exc).__name__}",
    )


def _recalculate_account_balances(db) -> int:
    """One-shot startup balance recalculation.

    Accounts created before the upload-persistence fix have
    ``current_balance=0.0`` even though transactions exist. This
    sums ``transaction.amount`` per account and writes the result
    back to ``Account.current_balance``. Returns the number of
    accounts updated.

    Safe to run on every startup — idempotent (a second run with no
    new transactions is a no-op UPDATE setting the same value).
    """
    from sqlalchemy import text

    result = db.execute(
        text("""
            UPDATE accounts
            SET current_balance = COALESCE(
                (SELECT SUM(amount) FROM transactions
                 WHERE transactions.account_id = accounts.id
                   AND (transactions.is_pending = 0 OR transactions.is_pending IS NULL)),
                0.0
            )
            WHERE id IN (SELECT DISTINCT account_id FROM transactions)
        """)
    )
    db.commit()
    updated = result.rowcount
    if updated > 0:
        LOG.info(
            "Startup balance recalculation: updated %d account(s)",
            updated,
        )
    return updated


@app.on_event("startup")
def _bootstrap_schema() -> None:
    """Phase-F4 hermetic bootstrap: ``Base.metadata.create_all`` +
    ``seed_default_categories`` so Finlynq's canonical ``categories``
    table is populated on every fresh DB.

    Multi-worker guard: ``fcntl.flock`` on a single file under the
    project ``.run/`` dir so two uvicorn workers cannot race the
    INSERT-IF-NOT-EXISTS loop in ``seed_default_categories`` on the
    first cold-start. POSIX-portable (macOS + Linux); Windows
    fallback is a no-op (the boot path still runs but the race
    window is slightly larger — acceptable for Windows-only CI).
    """
    try:
        _lock_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "..", ".run", "finlynq-boot.lock",
        )
        _lock_path = os.path.abspath(_lock_path)
        os.makedirs(os.path.dirname(_lock_path), exist_ok=True)
        _lock_fd = open(_lock_path, "w")
        try:
            try:
                fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError):
                LOG.info(
                    "fcntl.flock unavailable on this platform; "
                    "running Finlynq's boot-time seed without a multi-worker guard."
                )
            Base.metadata.create_all(engine)
            db = SessionLocal()
            try:
                inserted = seed_default_categories(db)
                if inserted > 0:
                    LOG.info("Seeded %d default categories on Finlynq startup", inserted)
                _recalculate_account_balances(db)
            finally:
                db.close()
        finally:
            try:
                fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_UN)
            except (AttributeError, OSError):
                pass
            _lock_fd.close()
    except Exception as exc:
        LOG.warning("Finlynq boot-time seed skipped: %s", exc)


# Routers in mount order: health FIRST (the public route), then the
# canonical-store endpoints (auth-gated via ``Depends(require_user)``
# on the route handler — NOT at router mount time).
app.include_router(health_router)
app.include_router(parse_router)
app.include_router(projection_state_router)
app.include_router(categorize_router)
app.include_router(categories_router)
app.include_router(state_router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "finlynq",
        "message": "see /health, /openapi.json, and the docs/ hierarchy.",
    }


# Phase-F5 stub: list every auth-gated endpoint so a future F5
# implementer doesn't have to grep routes/ — the canonical router
# names + paths are the wire-level contract.
_F4_AUTH_GATED_ENDPOINTS: List[str] = [
    "POST /categorize",
    "GET /categories",
    "POST /categories",
    "PUT /categories/{id}",
]
