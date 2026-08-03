"""Finance Copilot rules-service FastAPI app.

Phase 7 update: mounts the new ``/api/auth/*`` router (devlogin + logout)
on top of the existing /api/* surface. Auth router is included FIRST so
that the ``/api/auth/devlogin`` route is available before the
``Depends(require_user)`` guards on the other routers (otherwise
the UI could not bootstrap its session on cold-start).

Phase 7+ exception handlers: registers a JSON+CORS-aware handler for
``sqlalchemy.exc.IntegrityError`` (returns HTTP 409 with a stable
contract) AND a generic handler that wraps any unhandled ``Exception``
(returns HTTP 500 with a stable ``{"detail": ...}`` shape). Both
handlers manually attach the CORS headers that ``CORSMiddleware``
would normally inject. Starlette runs exception handlers BEHIND the
CORS middleware, so without this manual attachment the browser strips
the response and the client sees a generic ``Network Error`` instead
of the real cause (the same failure mode that caused the original
Settings-page "Network Error" report).

Phase 2-+: ``create_all`` was replaced by alembic migrations (Phase 3)
+ a startup health probe + a SMART CORS policy (excludes :5173).

Schema migrations are an explicit operator action. The development lifecycle
must not advance a database merely because a service is started; this prevents
an unmerged migration from being applied accidentally.

Phase 11 (reviewer #1 hardening): multi-worker uvicorn runs the
startup hook once per worker. To avoid the same migration running
N times (and n_workers × race-window ``alembic_version`` row writes),
the hook acquires a ``fcntl.flock`` on a single file under the
project ``.run/`` directory. The lock is held for the duration of
the upgrade and released by context-manager exit so a sibling
worker waits instead of duplicating the migration. POSIX-only
(macOS + Linux); Windows fallback is a no-op (the boot path still
works, the race window is just slightly larger on Win32).
"""
import fcntl
import logging
import os
import subprocess
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routes import (
    accounts_router,
    analyst_ratings_router,
    assistant_router,
    auth_router,
    budgets_router,
    categories_router,
    debts_router,
    # Phase 22 — ``/api/categorize/llm-batch`` join the registry so the
    # Activity page's AI-categorize untagged affordance can post Ollama
    # Pass-4 requests without spinning a new FastAPI app instance.
    categorize_llm_router,
    dashboard_router,
    data_router,
    # Phase 2 — policy-based rule evaluation.
    evaluate_router,
    family_members_router,
    goals_router,
    holdings_router,
    imports_router,
    # Phase 24 — DB-backed merchant substring rules CRUD. Re-exports
    # the same router from ``app.routes.merchant_rules``. Mirrors the
    # category gesture (categories_router carries the canonical
    # category taxonomy; merchant_rules_router carries the user-
    # editable keyword list that maps merchants to those categories,
    # Phase 1 Slice D-post — bounded authenticated POST /api/v1/goals/{goal_id}/forecasts.
    forecasts_generation_router,
    merchant_rules_router,
    plaid_router,
    transactions_router,
    users_router,
    recommendations_router,
    # Phase 2 Slice 1 commit-4 — deterministic recommendation GET +
    # append-only decision-journal POST routes. Re-uses the existing
    # ``Settings.atlas_forecast_read_api_enabled`` Phase 1 gate. NO new
    # flag introduced. NO mutable Phase 2 CRUD. NO autonomous execution.
    recommendations_derived_router,
)

LOG = logging.getLogger("uvicorn.error")

# Phase 19 — process diagnostics captured at import time so /health
# can answer "is the running process stale?" with one curl. Mirrors
# the alembic boot hook's repo-root ascent (two dirname() calls from
# app/main.py -> services/rules-service -> finance-copilot-full) so
# a future reorg only updates one place.
_APP_STARTED_AT = datetime.now(timezone.utc).isoformat()
_APP_PID = os.getpid()


def _detect_git_sha(repo_root: str) -> str | None:
    """Run ``git rev-parse --short HEAD`` against the project repo root.
    Returns the lowercase hex short SHA or ``None`` on any failure
    (no git binary / not a checkout / subprocess timeout / OSError).
    The 2-second timeout bounds startup — a hanging git invocation
    cannot block FastAPI from serving.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    return None


_SERVICES_APP_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_SERVICES_APP_ROOT))
_APP_GIT_SHA = _detect_git_sha(_REPO_ROOT)

# IMPORTANT -- no `Base.metadata.create_all(engine)` here. The schema
# source of truth is the alembic migration tree at
# services/rules-service/alembic/versions/ . app/schemas/__init__.py's
# Pydantic shapes stay in lockstep with the SQLAlchemy models via the
# conftest.py migration fixture (Phase 3's test_alembic_migration.py).

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Local-first finance copilot rules service. Provides JWT-cookie "
        "auth (single-user section 10 decision 4), CSV/PDF/OFX statement "
        "ingest (Phase 5+ Plaid alternatives), and a typed dashboard "
        "aggregate endpoint. Schema is alembic-managed; do not "
        "create_all from this module."
    ),
)

# CORS -- explicitly allow the Atlas Next.js dev server (3333) + the
# rules-service itself (8000) + the wealthiq dev server (3001 for
# legacy baseline). The :5173 from the Phase 3 lift was a Vite dev
# port that the wealthiq project no longer uses (Phase 4 dropped it).
ALLOWED_CORS_ORIGINS = {
    "http://localhost:3333",
    "http://127.0.0.1:3333",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3001",
}

# A developer may override the Atlas UI port through the lifecycle scripts.
# Keep this bounded to explicit local origins; an arbitrary environment value
# must never turn into a remote CORS origin.
_atlas_ui_port = os.environ.get("ATLAS_UI_PORT", "3333")
if _atlas_ui_port.isdecimal() and 0 < int(_atlas_ui_port) <= 65535:
    ALLOWED_CORS_ORIGINS.update(
        {
            f"http://localhost:{_atlas_ui_port}",
            f"http://127.0.0.1:{_atlas_ui_port}",
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cors_json(request: Request, status_code: int, detail: str) -> JSONResponse:
    """Build a JSON response that ALSO carries the CORS headers Starlette's
    exception handlers skip.

    Starlette's middleware chain runs CORSMiddleware AROUND the
    ServerErrorMiddleware, so a handler that builds a JSON response
    without explicit CORS headers produces a response the browser
    refuses to expose to JS (``err.response = undefined`` -> axios's
    "Network Error"). We echo ``Access-Control-Allow-Origin`` back
    whenever the request's Origin is on our allow-list.
    """
    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if origin in ALLOWED_CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=headers,
    )


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Map a SQLAlchemy UNIQUE/FK violation to HTTP 409 with a stable client
    contract. We do not surface ``str(exc.orig)`` to clients (it can
    include column names that we might not want to advertise); the full
    traceback stays in the server log for operators.

    This is the same failure mode that caused the original "Network
    Error" report: the Settings-page PUT raised an IntegrityError that
    bubbled past the default FastAPI 500 handler, whose response bypassed
    CORSMiddleware and was stripped by the browser.
    """
    LOG.warning("IntegrityError on %s %s: %s", request.method, request.url.path, exc)
    return _cors_json(
        request,
        status_code=409,
        detail="A record with that value already exists.",
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler. FastAPI's default 500 returns a bare
    ``Internal Server Error`` body WITHOUT CORS headers, which the
    browser strips so the UI sees "Network Error". We replace that
    with a JSON ``{"detail": ...}`` that carries CORS headers so the
    UI's ``classifyError`` mapping sees the real 500 status + detail
    string instead of the misleading "Network Error" label.
    """
    LOG.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _cors_json(
        request,
        status_code=500,
        detail=f"Internal server error: {type(exc).__name__}",
    )


@app.get("/health", tags=["health"])
async def health():
    """Liveness probe.

    Phase 19: extended with ``started_at`` + ``pid`` + ``git_sha`` so
    an operator can confirm the running process carries FRESH code
    (the same git SHA as their working tree) instead of a stale
    pre-fix interpreter. The original ``status`` field stays
    unchanged so every existing client that keys on it keeps
    working — adding fields is backward-compat, no client breaks.

    ⚠ Do NOT enable ``uvicorn --reload`` in dev if you intend to
    rely on ``started_at`` as 'process started'. With ``--reload``,
    every saved file re-evaluates this module, so ``_APP_STARTED_AT``
    resets to the last import timestamp and the field degenerates
    into 'module last imported' — wildly misleading when you wanted
    'process started'. Either keep ``--reload`` off (current
    start.sh does) or compare ``started_at`` against ``git_sha`` for
    a meaningful freshness answer instead of trusting it in isolation.
    """
    return {
        "status": "healthy",
        "started_at": _APP_STARTED_AT,
        "pid": _APP_PID,
        "git_sha": _APP_GIT_SHA,
    }


@app.on_event("startup")
def _run_alembic_upgrade_on_boot() -> None:
    """Phase 11 (self-healing) — apply any pending alembic revisions on
    boot. The original ``OperationalError: no such column: import_batches.
    preview_lines`` was caused by a developer committing the model +
    migration but forgetting to run ``alembic upgrade head`` locally.
    This hook makes that class of mistake self-healing: the next
    ``uvicorn`` cold-start applies the pending migrations before
    serving a single request.

    Idempotent — alembic's ``upgrade head`` against an already-at-head
    DB is a fast no-op (~1ms; just a SELECT against ``alembic_version``).
    Wrapped in try/except so a transient failure (lock contention on
    the ``alembic_version`` row, missing alembic.ini from a strange
    working dir) is LOGGED at WARNING level rather than crashing the
    whole API — the legacy ``create_all`` path would still apply TABLE
    definitions for a brand-new DB and the explicit OperationalError
    guard in ``routes/imports.py`` keeps an upload from 500-ing.

    Phase 11 (reviewer #1): guarded with ``fcntl.flock`` on a single
    file in the project ``.run/`` dir so a multi-worker uvicorn cannot
    race the alembic_version row writer. The second worker waits on
    the lock (bounded by the first worker's upgrade elapsed) and then
    re-enters at head — a no-op as confirmed by
    ``test_alembic_alembic_version_at_head_after_upgrade``.
    """
    if os.environ.get("ATLAS_AUTO_MIGRATE") != "1":
        LOG.info("Automatic migrations are disabled; run Alembic explicitly when approved.")
        return

    try:
        from alembic import command as _alembic_cmd
        from alembic.config import Config as _AlembicConfig

        _services_root = os.path.dirname(os.path.abspath(__file__))
        _alembic_ini = os.path.join(_services_root, "alembic.ini")
        if not os.path.exists(_alembic_ini):
            LOG.warning(
                "alembic.ini not found at %s — skipping boot-time upgrade",
                _alembic_ini,
            )
            return
        _cfg = _AlembicConfig(_alembic_ini)

        # POSIX fcntl.flock — works on this project's dev platforms
        # (macOS + Linux). Windows would need ``msvcrt.locking``; since
        # the project ships with ``start.sh`` + ``bash scripts/`` and
        # the dev shell prompt is bash on every supported host, we
        # treat ``fcntl`` as the universal path and silently skip the
        # lock if it is unavailable (the boot path still runs but the
        # race window is bigger — acceptable for Windows-only CI).
        _lock_path = os.path.join(
            # Reviewer #1: ascend one more directory level so the
            # lock lives at the project-root ``.run/`` (matches where
            # ``start.sh`` writes pid files). Two dirname() calls
            # get us from ``app/main.py`` -> ``services/rules-service``
            # -> ``finance-copilot-full`` (project root).
            os.path.dirname(os.path.dirname(_services_root)),
            ".run", "alembic-boot.lock",
        )
        os.makedirs(os.path.dirname(_lock_path), exist_ok=True)
        _lock_fd = open(_lock_path, "w")
        try:
            try:
                fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError):
                # Non-POSIX platform (e.g. Windows). Continue without
                # the lock — the boot-time self-healing still runs.
                LOG.info(
                    "fcntl.flock unavailable on this platform; running "
                    "boot-time alembic upgrade without a multi-worker guard."
                )
            _alembic_cmd.upgrade(_cfg, "head")
            LOG.info("Alembic schema at head (Phase 11 self-healing migration).")
        finally:
            try:
                fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_UN)
            except (AttributeError, OSError):
                pass
            _lock_fd.close()
    except Exception as _exc:  # broad on purpose — alembic surfaces in many forms
        LOG.warning("Alembic upgrade-on-boot skipped: %s", _exc)


@app.on_event("startup")
def _seed_default_categories() -> None:
    """Phase 11 startup hook — seed the categorizer's default
    categories so the activity-page filter dropdown + the
    Auto-categorize button have rows to operate on from a fresh DB.

    Idempotent: a re-run against an already-seeded DB no-ops (returns
    0 inserted) so repeated uvicorn reloads stay clean. The seed is
    also called from the test conftest so a hermetic test DB ends up
    with the same 12 rows as production.

    Why a startup hook instead of an alembic data migration: alembic
    owns TABLE shape; this hook owns REFERENCE DATA. Future categories
    added through ``POST /api/categories/`` are user data and skip
    this loop entirely (the existence check filters them out).

    Ordering: runs AFTER ``_run_alembic_upgrade_on_boot`` so the
    ``categories`` table exists with the constraints the seed code
    relies on (UNIQUE ``name`` for the existence check).
    """
    from app.services.categorizer import seed_default_categories
    db = SessionLocal()
    try:
        inserted = seed_default_categories(db)
        if inserted > 0:
            LOG.info("Seeded %d default categories on startup", inserted)
    finally:
        db.close()


@app.on_event("startup")
def _seed_default_merchant_rules() -> None:
    """Phase 24 startup hook — seed the categorizer's default
    merchant-substring rules into the ``merchant_rules`` table so a
    freshly-migrated DB has full coverage on first uvicorn cold start.

    Idempotent + soft-delete-aware:
    - Re-run against an already-seeded DB returns 0 inserted.
    - A row that exists with ``is_archived=True`` is preserved (the
      seed helper SKIPS archived rows so a user-deleted system rule
      stays deleted across restarts — a hard DELETE would let the
      seed re-INSERT, silently undoing the user's delete).

    Ordering: runs AFTER ``_seed_default_categories`` so the FK
    targets exist when the seed helper JOINs on
    ``Category.id = MerchantRule.category_id``. Without this
    ordering the FK constraint would surface as a 500 on first
    cold-start against a freshly-migrated DB.

    ``seed_default_merchant_rules`` is owned by
    ``app.services.categorizer`` (same module as the runtime
    categoriser) so the bootstrap dict and the runtime DB rules
    live in one file. A future Phase 24.1+ that lifts the seed
    list into a separate ``seed_data/`` directory would move
    BOTH pieces together.
    """
    from app.services.categorizer import seed_default_merchant_rules
    db = SessionLocal()
    try:
        inserted = seed_default_merchant_rules(db)
        if inserted > 0:
            LOG.info(
                "Seeded %d default merchant rules on startup", inserted
            )
    finally:
        db.close()


# Routers in mount order. Auth FIRST (UI bootstrap), then alphabetically.
# Phase 8 update: goals_router is added so /api/goals/* lands on the app
# (otherwise FastAPI never registers the routes — every POST/GET/PUT/DELETE
# returns 404 even though the module imports cleanly).
# Phase 11 update: categories_router joins the registry so the activity
# page can render its filter dropdown from ``GET /api/categories/`` and
# the categorize button can call ``POST /api/transactions/categorize``
# against a populated category list.
app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(budgets_router)
app.include_router(debts_router)
app.include_router(analyst_ratings_router)
app.include_router(assistant_router)
# Phase 22 — Pass 4 LLM-backed fallback categorizer. Registered next
# to ``categories_router`` because the FE groups the two behind a single
# ``rulesService.categorize*`` API surface.
app.include_router(categorize_llm_router)
app.include_router(categories_router)
app.include_router(dashboard_router)
app.include_router(data_router)
app.include_router(family_members_router)
app.include_router(goals_router)
app.include_router(holdings_router)
app.include_router(imports_router)
# Phase 24 — DB-backed merchant substring rules CRUD. Mirrors the
# categories_router gesture: the canonical record of which keywords
# tag a transaction lives in the DB; the rules table reference data
# is owned by the rules-service so the FE does not need a separate
# service hop.
app.include_router(merchant_rules_router)
app.include_router(plaid_router)
app.include_router(transactions_router)
app.include_router(users_router)
# Phase 4 — recommendation approval workflow CRUD.
app.include_router(recommendations_router)
# Phase 2 — policy-based rule evaluation.
app.include_router(evaluate_router)
app.include_router(forecasts_generation_router)
# Phase 2 Slice 1 commit-4 — deterministic recommendation GET +
# append-only decision-journal POST routes. Re-uses the existing
# ``Settings.atlas_forecast_read_api_enabled`` Phase 1 gate. NO new
# flag introduced. NO mutable Phase 2 CRUD. NO autonomous execution.
app.include_router(recommendations_derived_router)


@app.on_event("startup")
def _seed_default_recommendations() -> None:
    """Phase 4 startup hook — seed demo recommendations so the
    ApprovalQueue dashboard component renders meaningful data on
    first load.

    Idempotent: skips insertion when the user already has any
    recommendations (any status). Only fires for user_id=1 (the
    default local user).

    Ordering: runs AFTER ``_seed_default_merchant_rules`` so the
    ``users`` table exists and the local user has been created by
    the auth/devlogin flow.
    """
    from app.routes.recommendations import seed_default_recommendations
    db = SessionLocal()
    try:
        inserted = seed_default_recommendations(db)
        if inserted > 0:
            LOG.info("Seeded %d demo recommendations on startup", inserted)
    finally:
        db.close()


@app.on_event("startup")
def _generate_smart_recommendations_on_boot() -> None:
    """Phase 5 startup hook — generate AI Copilot smart recommendations
    from real finance data (anomalies, bills, trends, savings rate).

    Runs AFTER ``_seed_default_recommendations`` so the demo data is
    already in place. Uses a metadata_json check to avoid re-generating
    on every restart — only fires when zero auto-generated
    recommendations exist for user_id=1.
    """
    from app.models import RecommendationLog
    from app.routes.recommendations import generate_smart_recommendations
    db = SessionLocal()
    try:
        existing_smart = (
            db.query(RecommendationLog)
            .filter(
                RecommendationLog.user_id == 1,
                RecommendationLog.metadata_json.like('%"source": "auto-generated"%'),
            )
            .first()
        )
        if existing_smart:
            return
        inserted = generate_smart_recommendations(db, 1)
        if inserted > 0:
            LOG.info("Generated %d smart recommendations on startup", inserted)
    except Exception as exc:
        LOG.warning("Smart recommendation generation skipped: %s", exc)
    finally:
        db.close()
