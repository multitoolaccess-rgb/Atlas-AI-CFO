"""FastAPI router registry — re-exports every router so ``app/main.py``
can call ``include_router`` once per resource.

Phase 7 update: ``auth_router`` (Phase 7 ``POST /api/auth/devlogin`` +
``POST /api/auth/logout``) is wired into the registry so the UI's
cold-start flow can mint + clear the JWT cookie.

Phase 8 update: ``goals_router`` (``/api/goals/*``) joins the registry
so the multi-goal CRUD + dashboard-summary frontend reads work
end-to-end.

Phase 9 update: ``analyst_ratings_router`` (``/api/analyst-ratings/*``,
Finnhub-backed) joins so the recommendations page can render real-time
sell-side consensus + price targets without leaking the API key into
the browser bundle.

Phase 11 update: ``categories_router`` joins so the activity page can
render its filter dropdown from ``GET /api/categories/``.

Phase 16 update: ``family_members_router`` joins so the Settings Family
Members card can CRUD household rows.

Phase 17 update: ``data_router`` joins so the Settings Danger Zone can
call ``DELETE /api/data/`` to nuke all user data.

Phase 24 update: ``merchant_rules_router`` joins so the Settings
Merchant Rules card can CRUD the DB-backed substring rules without
a BE restart.

Routers are listed ALPHABETICALLY here so the order in main.py's
``include_router`` calls matches without surprise.

Lifting order (matches main.py include order):

1. accounts_router         — /api/accounts/*
2. analyst_ratings_router  — /api/analyst-ratings/*  (Phase 9)
3. auth_router             — /api/auth/*
4. categories_router       — /api/categories/*       (Phase 11)
5. dashboard_router        — /api/dashboard/*
6. data_router             — /api/data/*             (Phase 17)
7. family_members_router   — /api/family-members/*   (Phase 16)
8. goals_router            — /api/goals/*            (Phase 8)
9. imports_router          — /api/imports/*
10. merchant_rules_router  — /api/merchant-rules/*  (Phase 24)
11. plaid_router           — /api/plaid/*            (501 stub)
12. transactions_router    — /api/transactions/*
13. users_router           — /api/profile/*
"""
from app.routes.accounts import router as accounts_router
from app.routes.analyst_ratings import router as analyst_ratings_router
# Phase 30 — AI Finance Assistant chat endpoint.
from app.routes.assistant import router as assistant_router
# Phase 22 — Pass-4 LLM-backed categorizer (Ollama httpx + 7-day SHA-256
# prompt cache). Lives under ``/api/categorize/llm-batch`` so the existing
# ``POST /api/transactions/categorize`` heuristic forwarder keeps its
# contract for the Activity page's primary button. The two endpoints are
# independent — the FE's new "AI-categorize untagged" affordance hits
# this router while the existing "Auto-categorize" button still hits
# the heuristic forwarder.
from app.routes.categorize_llm import router as categorize_llm_router
from app.routes.auth import router as auth_router
from app.routes.categories import router as categories_router
from app.routes.dashboard import router as dashboard_router
from app.routes.data import router as data_router
from app.routes.family_members import router as family_members_router

# Phase 1 Slice D-post — authenticated POST /api/v1/goals/{goal_id}/forecasts
# generation route. Bounded scope: ownership-before-adapter, idempotency,
# conditional headers, default-off persistence-gated 503, sanitized
# 4xx/5xx envelopes, HATEOAS links. NO mutable forecast CRUD. route
# signature uses Annotated[X, Header(..., default=None)] (default INSIDE
# Header) to avoid the FastAPI 0.104.1 + pydantic 2.x FieldInfo.in_ leak.
from app.routes.forecasts_generation import router as forecasts_generation_router
# Phase 1 Slice D-post — authenticated POST /api/v1/goals/{goal_id}/forecasts
# generation route. Bounded scope: ownership-before-adapter, idempotency,
# conditional headers, default-off persistence-gated 503, sanitized
# 4xx/5xx envelopes, HATEOAS links. NO mutable forecast CRUD. NO
# request-path shadowing. Route signature uses ``Annotated[X, Header(...,
# default=None)]`` (default INSIDE Header) to avoid the FastAPI 0.104.1
# + pydantic 2.x ``FieldInfo.in_`` leak at TestClient(app) construction.
from app.routes.forecasts_generation import router as forecasts_generation_router
# Phase 2 Slice 1 commit-4 â bounded Phase 2 routes:
# GET  /api/v1/forecasts/{forecast_id}/recommendation
# POST /api/v1/recommendations/{recommendation_id}/decisions
# Reuses Settings.atlas_forecast_read_api_enabled (existing Phase 1
# gate; no NEW flag). Cross-user / missing return SAME envelope for
# indistinguishability. Append-only journal semantics. NO mutable
# Phase 2 CRUD. NO client financial-state fields.
from app.routes.recommendations_derived import router as recommendations_derived_router
from app.routes.decision_history import router as decision_history_router
from app.routes.goals import router as goals_router
# Phase 39 — portfolio holdings (positions import + live pricing).
from app.routes.holdings import router as holdings_router
from app.routes.imports import router as imports_router
# Phase 24 — DB-backed merchant substring rules CRUD. Allows the
# user to add / edit / remove / disable keywords via the Settings
# UI without a BE redeploy (the legacy categorical rule list was
# a Python module-level dict; this lift + the ``merchant_rules``
# table replacement unlock the same UX from a UI affordance).
from app.routes.merchant_rules import router as merchant_rules_router
from app.routes.plaid import router as plaid_router
from app.routes.transactions import router as transactions_router
from app.routes.users import router as users_router
# Atlas Phase 1 — budget CRUD + status endpoint
from app.routes.budgets import router as budgets_router
from app.routes.debts import router as debts_router
# Phase 4 — recommendation approval workflow CRUD.
from app.routes.recommendations import router as recommendations_router
# Phase 2 — policy-based rule evaluation.
from app.routes.evaluate import router as evaluate_router
from app.routes.market_briefs import router as market_briefs_router
# Phase 6 Slice 1 — authoritative Scenario Lab backend APIs.
from app.routes.scenarios import router as scenarios_router
from app.routes.readiness import router as readiness_router
from app.routes.investment_persistence import router as investment_persistence_router
from app.routes.investment_discovery import router as investment_discovery_router
from app.routes.investment_assistant import router as investment_assistant_router
from app.routes.investment_risk import router as investment_risk_router
from app.routes.investment_scout import router as investment_scout_router

__all__ = [
    "accounts_router",
    "analyst_ratings_router",
    "assistant_router",
    "auth_router",
    "budgets_router",
    "categorize_llm_router",
    "categories_router",
    "dashboard_router",
    "data_router",
    "family_members_router",
    "goals_router",
    "holdings_router",
    "imports_router",
    "merchant_rules_router",
    "plaid_router",
    "transactions_router",
    "users_router",
    "recommendations_router",
    "evaluate_router",
    "forecasts_generation_router",
    "market_briefs_router",
    "scenarios_router",
    "readiness_router",
    "investment_persistence_router",
    "investment_discovery_router",
    "investment_assistant_router",
    "investment_risk_router",
    "investment_scout_router",
]
