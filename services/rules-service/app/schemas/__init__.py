"""Pydantic schemas — request + response shapes for API routes.

Phase 6 lifts new request schemas from wealthiq ``backend/app/schemas/__init__.py``
(``docs/wealthiq-merge-plan.md`` §4 item 12). Two edits applied inline:

1. ``from pydantic import BaseModel, EmailStr`` → also imports ``ConfigDict``.
2. Each of the 8 ``class Config:`` blocks is rewritten to ``model_config =
   ConfigDict(...)``. The replacement: 7× ``from_attributes=True`` and
   1× ``arbitrary_types_allowed=True``.

Phase 6 adds 3 new request schemas (``TransactionCreate``, ``ImportUploadRequest``,
``PlaidExchangeRequest``) that are referenced by the auth-tightened routes
but not yet used as FastAPI request bodies — they're contract shapes that
keep the API surface coherent even where the route today reads multipart
form-data via raw ``Form(...)`` parameters. Replace ``Form(...)`` ingest
with these schemas in a Phase 6 follow-up if a client asks for typed
multipart ingest.

NOTE \u2014 Phase 4 sets ``email: str`` (NOT ``EmailStr``) so the local-user
contract (settings.local_user, default "alex") can be stored in the
``email`` DB column without failing validation. Phase 6 may re-add EmailStr
validation alongside a redesigned user-identity + auth model.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.account_types import ACCOUNT_TYPE_VALUES

# Phase 40 — Account provenance enum. Declared at the top of the
# module so the Pydantic class-body annotations on
# ``AccountCreate`` / ``AccountResponse`` can reference it
# directly (no string forward-ref dance). Adding a fourth value
# (e.g. ``"brokerage-api"``) requires both schema + UI changes —
# the one-source-change-touch-everywhere discipline prevents the
# "everything is imported" future-tense drift.
AccountSource = Literal["manual", "imported", "plaid"]


class UserBase(BaseModel):
    # See NOTE above about why ``str`` (not ``EmailStr``).
    email: str
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountCreate(BaseModel):
    account_name: str
    account_type: str
    institution_name: str

    @field_validator("account_type")
    @classmethod
    def _validate_account_type(cls, v: str) -> str:
        """Phase 52 — reject non-canonical account types at the schema layer."""
        v_lower = v.strip().lower()
        if v_lower == "credit":
            return "credit_card"
        if v_lower not in ACCOUNT_TYPE_VALUES:
            raise ValueError(
                f"Unknown account type '{v}'. Must be one of: "
                f"{', '.join(sorted(ACCOUNT_TYPE_VALUES))}"
            )
        return v_lower
    current_balance: float = 0.0
    account_subtype: Optional[str] = None
    account_number: Optional[str] = None
    source: Optional[AccountSource] = "manual"
    description: Optional[str] = None
    family_member_id: Optional[int] = None
    # Debt fields — populated for liability accounts (credit_card, loan, mortgage)
    interest_rate: Optional[float] = None
    credit_limit: Optional[float] = None
    minimum_payment: Optional[float] = None
    term_months: Optional[int] = None


class AccountUpdate(BaseModel):
    """Partial-update schema for PUT ``/api/accounts/{account_id}``.

    Every field optional — clients send only what they're changing.
    """
    account_name: Optional[str] = None
    account_type: Optional[str] = None
    institution_name: Optional[str] = None

    @field_validator("account_type")
    @classmethod
    def _validate_account_type(cls, v: Optional[str]) -> Optional[str]:
        """Phase 52 — reject non-canonical account types on update too."""
        if v is None:
            return None
        v_lower = v.strip().lower()
        if v_lower == "credit":
            return "credit_card"
        if v_lower not in ACCOUNT_TYPE_VALUES:
            raise ValueError(
                f"Unknown account type '{v}'. Must be one of: "
                f"{', '.join(sorted(ACCOUNT_TYPE_VALUES))}"
            )
        return v_lower
    account_subtype: Optional[str] = None
    account_number: Optional[str] = None
    current_balance: Optional[float] = None
    is_active: Optional[bool] = None
    family_member_id: Optional[int] = None
    description: Optional[str] = None
    # Debt fields
    interest_rate: Optional[float] = None
    credit_limit: Optional[float] = None
    minimum_payment: Optional[float] = None
    term_months: Optional[int] = None


class AccountResponse(BaseModel):
    id: int
    account_name: str
    account_type: str
    account_subtype: Optional[str] = None
    account_number: Optional[str] = None
    current_balance: float
    is_active: bool
    last_sync: Optional[datetime] = None
    family_member_id: int
    source: AccountSource
    description: Optional[str] = None
    # Debt fields
    interest_rate: Optional[float] = None
    credit_limit: Optional[float] = None
    minimum_payment: Optional[float] = None
    term_months: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionCreate(BaseModel):
    """Phase 6: typed request schema for POST /api/transactions/.

    Note \u2014 Phase 4 lifted transactions as a read-only resource (no POST
    route was wired up because transactions are the OUTPUT of the
    import-parser pipeline, not separate user input). Phase 6 adds the
    shape for any future Phase 7+ integration that lets the user
    manually key a transaction (e.g. ``POST /api/transactions/`` for a
    cash payment that wasn't on a statement).
    """
    account_id: int
    description: str
    amount: float
    transaction_date: datetime
    merchant_name: Optional[str] = None
    category_id: Optional[int] = None
    is_pending: bool = False


class TransactionUpdate(BaseModel):
    """Partial-update schema for PUT ``/api/transactions/{transaction_id}``.

    Every field optional — clients send only what they're changing.
    Identity columns (``id``, ``account_id``, ``import_batch_id``,
    ``user_id``, ``created_at``, ``updated_at``) are intentionally NOT
    declared so clients cannot escalate ownership or rewrite history
    via PUT. Description/amount/date are immutable load-side facts
    PK'd into the schema for the same reason.

    The user has authority over how those rows group + report, so
    only ``category_id`` + ``merchant_name`` are mutable today.

    **Phase 28 — explicit-null detach contract**: a client can send
    ``{"category_id": null}`` to clear the column (the Activity page's
    per-row chip detach affordance depends on this) or
    ``{"merchant_name": null}`` to clear the parsed-merchant string.
    The route uses ``model_dump(exclude_unset=True)`` so an explicit
    ``null`` is distinguished from "field absent in the payload" —
    a request that omits ``category_id`` entirely (e.g. a FE
    correcting only ``merchant_name``) leaves the existing category
    intact. The detach button in the Activity page sends explicit
    ``null``; a parser-correction form sends a new value for
    ``merchant_name`` and omits ``category_id`` so the category
    stays in lockstep with the user's prior tagging.
    """

    category_id: Optional[int] = None
    merchant_name: Optional[str] = None


class TransactionResponse(BaseModel):
    id: int
    description: str
    amount: float
    # Phase 52+ — split-bookkeeping columns. Either ``debit`` or
    # ``credit`` is populated (never both) for every transaction
    # with a non-zero amount; both are ``null`` for an
    # FX-neutral zero-amount row. Convention: both columns store
    # UNSIGNED positive magnitudes (no negative debit column,
    # no negative credit column) so a glance at the values tells
    # the user direction (left or right) without a sign check.
    debit: Optional[float] = None
    credit: Optional[float] = None
    transaction_date: datetime
    merchant_name: Optional[str] = None
    is_pending: bool
    # Phase 11 — flatten account + category so the FE can filter,
    # sort, and render without N+1 follow-up calls. Names are
    # denormalised at read-time on the BE; if the user renames an
    # account or category the next refetch shows the new label.
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    account_type: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    # Phase 54+ — duplicate tracking fields. Populated when the
    # transaction was flagged as a duplicate during import.
    # ``is_duplicate=True`` + ``duplicate_of_id`` pointing to the
    # original. The Activity page renders these with a badge.
    is_duplicate: bool = False
    duplicate_of_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ImportBatchResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    record_count: int
    account_id: int
    saved_transactions: int
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    # Phase 11 — first N text lines the import-parser saw, persisted
    # so the FE's "View" affordance on a historical PDF/OCR batch
    # renders a preview panel even when ``saved_transactions == 0``
    # (the user's "nothing loads" complaint). Capped at 50 lines by
    # the route to prevent 200-page statements from filling the DB.
    preview_lines: Optional[List[Any]] = None
    # Phase 39 — when a multi-account import split transactions across
    # several accounts (e.g. Fidelity Investment Report → brokerage + HSA),
    # the FE's import history table renders "2 accounts" instead of just
    # one account name. ``None`` for single-account batches.
    multi_account_ids: Optional[List[int]] = None

    model_config = ConfigDict(from_attributes=True)


class ImportUploadRequest(BaseModel):
    """Phase 6: typed shape for POST /api/imports/upload.

    Multipart form-data fields the route reads via ``Form(...)`` today;
    this Pydantic model is the SOURCE OF TRUTH for the field NAMES a
    client should send. Phase 7+ can replace ``Form(...)`` with this
    model + a Pydantic-aware multipart parser.
    """
    file: bytes = Field(..., description="CSV or PDF bank-statement payload")
    account_id: Optional[int] = Field(
        default=None,
        description="Target account id; defaults to first active account or lazily creates 'Imported Statements'.",
    )


class CategoryCreate(BaseModel):
    """Request shape for POST ``/api/categories/``.

    The activity-page filter + the categorizer both read from this table,
    so an authenticated user can grow their taxonomy without bespoke admin
    tooling. ``name`` is REQUIRED and must be unique (the model declares
    ``name`` as such); ``description``, ``icon``, ``color`` are display
    metadata. ``budget_group`` classifies spending for budget tracking.
    ``group`` is the hierarchical taxonomy group (Income/Expenses/Debt/
    Investments/Transfer).
    """

    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    budget_group: Optional[str] = "flexible"
    group: Optional[str] = "Expenses"


class CategoryUpdate(BaseModel):
    """Partial-update schema for PUT ``/api/categories/{id}``.

    Every field optional. Identity column (``id``) is intentionally NOT
    declared so clients cannot rename-by-id via PUT + DELETE.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    budget_group: Optional[str] = None
    group: Optional[str] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    budget_group: Optional[str] = "flexible"
    group: Optional[str] = "Expenses"

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    """Request shape for POST /api/budgets/."""
    category_id: Optional[int] = None
    amount: float
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM format")


class BudgetUpdate(BaseModel):
    """Partial-update schema for PUT /api/budgets/{id}."""
    amount: Optional[float] = None


class BudgetCategoryStatus(BaseModel):
    category_id: int
    category_name: str
    budget_group: str
    planned: float
    actual: float
    remaining: float
    percent_used: float


class BudgetStatusResponse(BaseModel):
    period: str
    categories: List[BudgetCategoryStatus]
    totals: dict


class BudgetResponse(BaseModel):
    id: int
    user_id: int
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    amount: float
    period: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# Atlas Phase 2 — Income/Expense/Debt breakdown schemas
# ----------------------------------------------------------------------

class BreakdownByGroup(BaseModel):
    group: str
    amount: float
    percentage: float


class BreakdownByCategory(BaseModel):
    category_id: int
    category_name: str
    budget_group: str
    amount: float


class BreakdownTrendPoint(BaseModel):
    month: str
    amount: float


class IncomeBreakdownResponse(BaseModel):
    period_start: str
    period_end: str
    total_income: float
    by_group: List[BreakdownByGroup]
    by_category: List[BreakdownByCategory]
    trend: List[BreakdownTrendPoint]


class ExpenseBreakdownResponse(BaseModel):
    period_start: str
    period_end: str
    total_expenses: float
    by_group: List[BreakdownByGroup]
    by_category: List[BreakdownByCategory]
    trend: List[BreakdownTrendPoint]


class DebtItem(BaseModel):
    account_id: int
    account_name: str
    account_type: str
    balance: float
    interest_rate: Optional[float] = None
    minimum_payment: Optional[float] = None
    credit_limit: Optional[float] = None
    term_months: Optional[int] = None
    utilization: Optional[float] = None


class DebtsSummaryResponse(BaseModel):
    total_debt: float
    blended_apr: float
    total_monthly_minimum: float
    debts: List[DebtItem]


class InsightItem(BaseModel):
    type: str  # "warning" | "info" | "success"
    category: str
    message: str
    current: float
    previous: float
    change_pct: float


class InsightsResponse(BaseModel):
    insights: List[InsightItem]


class AnomalyItem(BaseModel):
    """A single anomalous transaction flagged by the anomaly detector."""
    transaction_id: int
    merchant: str
    amount: float
    median: float
    multiplier: float
    date: Optional[str] = None


class AnomaliesResponse(BaseModel):
    anomalies: List[AnomalyItem]
    count: int


class UpcomingBillItem(BaseModel):
    """A predicted recurring bill."""
    merchant: str
    median_amount: float
    median_interval_days: int
    last_date: Optional[str] = None
    predicted_next_date: Optional[str] = None
    confidence: float
    hit_count: int


class UpcomingBillsResponse(BaseModel):
    bills: List[UpcomingBillItem]
    count: int


class DashboardSummary(BaseModel):
    """Aggregate state for the dashboard hero panel.

    Read-only \u2014 never accepted as input. Anti-corruption from
    ``routes/dashboard.py`` (Phase 4 lift, Phase 6 auth-enforced,
    Phase 8: includes ``user_goals`` for multi-goal projections).
    """

    total_balance: float
    total_income_month: float
    total_expenses_month: float
    accounts_count: int
    transactions_count: int
    last_sync: Optional[datetime] = None
    import_batches_count: int
    last_import_at: Optional[datetime] = None
    # Phase 8 \u2014 the local user's non-archived goals. The FE's
    # ``FinancialPlans`` component replaces the hardcoded $15M
    # constant with this list, rendering one card per goal.
    user_goals: List["GoalResponse"] = []


class UserProfileCreate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    phone_number: Optional[str] = None
    profile_picture_url: Optional[str] = None
    currency_preference: Optional[str] = "USD"
    goals: Optional[str] = None
    risk_profile: Optional[str] = None
    target_net_worth: Optional[str] = None
    time_horizon_years: Optional[int] = None
    annual_income: Optional[str] = None
    total_liabilities: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: int
    email: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    phone_number: Optional[str] = None
    profile_picture_url: Optional[str] = None
    currency_preference: Optional[str] = "USD"
    goals: Optional[str] = None
    risk_profile: Optional[str] = None
    target_net_worth: Optional[str] = None
    time_horizon_years: Optional[int] = None
    annual_income: Optional[str] = None
    total_liabilities: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PlaidExchangeRequest(BaseModel):
    """Phase 6: typed shape for POST /api/plaid/exchange_public_token.

    Phase 4 added an inline ``ExchangePublicTokenRequest`` in
    ``routes/plaid.py`` for the same purpose. Phase 6 lifts it here so
    a Phase 7+ client SDK can import the schema without depending on the
    route module.
    """
    public_token: str


class PlaidLinkTokenResponse(BaseModel):
    link_token: str


class ImportResponse(BaseModel):
    filename: str
    file_type: str
    record_count: int
    preview: List[Any]
    batch_id: Optional[int] = None
    account_id: Optional[int] = None
    saved_transactions: Optional[int] = None
    # Phase 12 — import hardening. ``expected_row_count`` is the raw
    # number of data rows the parser found (before filtering malformed
    # rows). ``saved_transactions`` is what actually persisted. When
    # ``expected_row_count > saved_transactions``, the FE renders a
    # warning banner so the user is never confused about missing rows.
    expected_row_count: Optional[int] = None
    warnings: List[str] = []
    # Phase 17 — auto-categorize summary. After every successful
    # upload, the BE runs :func:`app.services.categorizer.
    # categorize_transactions` on the just-imported transactions
    # (``WHERE import_batch_id == batch.id AND category_id IS NULL``)
    # so the user never has to click the Activity page's
    # "Auto-categorize" button. Three numbers on the wire:
    #
    # - ``auto_categorized``: count of rows that received a category
    #   id via the heuristic (the substring match caught a known
    #   merchant keyword).
    # - ``auto_categorize_total``: count of NOT-YET-categorized rows
    #   at import time (= ``saved_transactions`` if every row was
    #   uncategorized; < ``saved_transactions`` if some rows had manual
    #   pre-tags, e.g. an OCR re-import that didn't wipe
    #   ``category_id``).
    # - ``auto_categorize_no_match``: count of rows where the
    #   heuristic ran but didn't match any keyword (merchant text
    #   unrecognised). Surfaces the gap between
    #   ``auto_categorize_total`` and ``auto_categorized`` so the FE
    #   can render "Auto-tagged N of M — K need a manual pick" rather
    #   than hiding the third bucket.
    #
    # All three are ``null`` for legacy callers / Finlynq-forwarded
    # envelopes that don't run the local categorizer; the FE falls
    # back to "Imported N transaction(s)" when both are null.
    auto_categorized: Optional[int] = None
    auto_categorize_total: Optional[int] = None
    auto_categorize_no_match: Optional[int] = None
    # Phase 39 — multi-account import summary. When a single statement
    # is split across multiple accounts (e.g. a Fidelity Investment
    # Report with a brokerage + HSA), the FE can render "Imported
    # into 2 accounts" rather than showing only ``account_id``.
    multi_account_ids: Optional[List[int]] = None
    # Phase 52 — account-type auto-detection. When the parser scanned the
    # statement and guessed an account type (credit_card / checking /
    # investment etc.), the FE renders a confirmation prompt before
    # completing the import. ``None`` when detection was uncertain
    # or when the user explicitly selected a target account.
    suggested_account_type: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ----------------------------------------------------------------------
# Phase 8 — multi-goal financial planning
# ----------------------------------------------------------------------


class GoalCreate(BaseModel):
    """Request shape for POST ``/api/goals/``.

    Why ``target_amount`` is required but ``target_date`` is optional:
    the user may express a deadline as either a date (``target_date``)
    or a horizon (``horizon_years``). The FE's projection engine uses
    whichever is set; if both are missing the engine falls back to
    the user's default retirement horizon (≤20 yrs).

    ``notes`` is a free-text string the FE renders as a tooltip. The
    BE does NOT inspect or sanitize it — Pydantic str passes through.
    """

    name: str
    target_amount: float
    target_date: Optional[date] = None
    horizon_years: Optional[int] = Field(default=None, ge=0, le=120)
    priority: int = 0
    notes: Optional[str] = None


class GoalUpdate(BaseModel):
    """Partial-update schema for PUT ``/api/goals/{goal_id}``.

    Every field optional — clients send only what they're changing.

    Identical whitelist contract to ``AccountUpdate`` / ``UserProfileCreate``:
    identity columns (``id``, ``user_id``, ``created_at``, ``updated_at``)
    are NOT declared — clients cannot escalate / re-tie ownership via PUT.

    ``is_archived`` is included so admin tools can archive / unarchive
    a goal without a separate endpoint. Archiving is the ONLY delete
    path (see Goal ORM model docstring).
    """

    name: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[date] = None
    horizon_years: Optional[int] = Field(default=None, ge=0, le=120)
    priority: Optional[int] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class GoalResponse(BaseModel):
    id: int
    name: str
    target_amount: float
    target_date: Optional[date] = None
    horizon_years: Optional[int] = None
    priority: int
    is_archived: bool
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Phase 8 \u2014 forward-reference resolution. ``DashboardSummary`` declares
# ``user_goals: List[GoalResponse]`` BUT ``GoalResponse`` was defined
# later in this file (above). Pydantic 2.x resolves string forward-refs
# via ``model_rebuild()`` after ``GoalResponse`` is bound in this
# module's namespace; without this call every FastAPI route that
# returns ``DashboardSummary`` would 500 with
# ``pydantic.errors.PydanticUndefinedAnnotation`` on first request.
# Called at the END of the module so ``GoalResponse`` is already bound.
DashboardSummary.model_rebuild()


# ----------------------------------------------------------------------
# Phase 16 — Family Members (per-user grouping of accounts)
# ----------------------------------------------------------------------


# Hex color validator on the COLOR field — the BE is the single source
# of truth so the Accounts page dropdown can't ship a render-time
# invalid color string into the DB. ``pattern=...`` is the Pydantic V2
# idiom (``regex=`` is deprecated; see Pydantic V2 migration guide).
_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"

# Phase 16+ — household profile layered enums. ``Literal[...]`` produces
# a strict Pydantic V2 enum: OpenAPI serializes it as a JSON enum so the
# FE's Settings Family Members card can render an exact-options
# <select> (no free-text fallback). The Self row's relationship is
# locked to ``'Self'`` on the BE regardless of what the client sends;
# every other relationship value is freely POSTable / PUTable.
Relationship = Literal["Self", "Spouse", "Child", "Parent", "Sibling", "Other"]

# Working-status enum — the 6 canonical buckets a household financial
# profile needs to answer "who brings in income?". Free-text storage
# would defeat the FE's auto-aggregation column ("N earners" / "M
# dependents"), so this is a locked enum at the BE.
WorkingStatus = Literal[
    "Employed",
    "Unemployed",
    "Student",
    "Retired",
    "Homemaker",
    "Other",
]

# Phase 16+ — sanity cap on age. 0 (newborn) to 120 (long-tail
# longevity) covers every realistic household profile; values
# outside the range 422 at the schema layer so a typo (#-1 from
# "minus 1", #200 from a fat-finger) doesn't pollute the DB.
# Loosenable in a Phase 18+ refactor if a user needs >120.
_MIN_AGE = 0
_MAX_AGE = 120


class FamilyMemberCreate(BaseModel):
    """Request shape for POST ``/api/family-members/``.

    ``color`` is a hex string ``#RRGGBB`` enforced by the
    :data:`_HEX_COLOR_PATTERN` regex via Pydantic ``Field(pattern=...)``.
    A non-hex value 422s at the schema layer — no business logic
    in the route. ``name`` is required and the route layer adds an
    empty-string guard so a FE that submits ``"   "`` 400s rather
    than writing an empty chip into the DB.

    Household profile fields (``relationship``, ``working_status``,
    ``age``) are all optional on POST so a user can draft a row
    in two clicks (name + color) and fill out the rest later
    via ``PUT /api/family-members/{id}``. A non-Self user sending
    ``relationship=None`` is treated as "not yet filled in"
    (column stays NULL); a self-row POST is rejected by the route
    layer (only :func:`get_or_create_family_member_self` may
    create the Self row).
    """

    name: str
    color: str = Field(pattern=_HEX_COLOR_PATTERN)
    relationship: Optional[Relationship] = None
    working_status: Optional[WorkingStatus] = None
    age: Optional[int] = Field(default=None, ge=_MIN_AGE, le=_MAX_AGE)


class FamilyMemberUpdate(BaseModel):
    """Partial-update schema for PUT ``/api/family-members/{member_id}``.

    Every field optional — clients send only what they're changing.

    Identical whitelist contract to ``AccountUpdate`` / ``GoalUpdate``:
    identity columns / the ``is_self`` flag are intentionally NOT
    declared so clients can NEVER promote an arbitrary member to
    ``is_self=True`` (a client sending ``{"is_self": true}`` is
    silently dropped by ``model_dump()``).

    Household profile fields are mutable so the FE can revise a
    member's working_status (``Retired`` → ``Employed``) or age
    (a birthday celebration) directly. ``relationship`` is locked
    on the BE for the Self row (see ``routes/family_members.py``)
    but is freely mutable for every other row.
    """

    name: Optional[str] = None
    color: Optional[str] = Field(default=None, pattern=_HEX_COLOR_PATTERN)
    relationship: Optional[Relationship] = None
    working_status: Optional[WorkingStatus] = None
    age: Optional[int] = Field(default=None, ge=_MIN_AGE, le=_MAX_AGE)


# ----------------------------------------------------------------------
# Phase 24 — Merchant Rules (DB-backed substring categorizer keywords)
# ----------------------------------------------------------------------

# Phase 27 — source provenance enum. Locks the FE's allowed values
# via Pydantic ``Literal[...]`` so a client sending ``source="icup"``
# 422s at the schema layer (Pydantic V2 Literal mapping in
# OpenAPI). Values map to the write paths documented on
# ``MerchantRule.source`` in :mod:`app.models.merchant_rule`.
MerchantRuleSource = Literal["system", "manual", "tag-rule", "llm", "imported"]


class MerchantRuleCreate(BaseModel):
    """Request shape for POST ``/api/merchant-rules/``.

    ``category_id`` is the FK target — the route resolves the
    Category row id from ``categories.id`` so a renamed category
    keeps the FK valid.

    ``keyword`` is uppercased server-side on insert so the categorizer's
    per-row scan can skip a per-call upper.

    ``priority`` is OPTIONAL on POST. When omitted (the common
    "Add rule" flow on the Settings page) the BE auto-assigns
    ``MAX(existing.priority) + 10`` for the target category, falling
    back to ``100`` when the category is empty. This auto-increment
    keeps the new rule sorted AT THE BOTTOM of its category without
    colliding with the last existing row's priority (a 100-default
    collision was the original user complaint: "when I add a new
    rule it uses the same priority as the rule in the category I
    have"). A client that needs a SPECIFIC priority (e.g. the
    CSV import path which preserves ``priority`` verbatim) sends
    the value explicitly and the BE honours it verbatim.

    ``keyword`` is required; duplicates inside a category land 409
    (the ``UNIQUE(category_id, keyword)`` table constraint).

    Phase 27 — ``source`` is OPTIONAL on POST. The route layer
    defaults to ``'manual'`` when omitted so a FE that hasn't loaded
    the Phase 27 chips yet still works. ``'system'`` is not accepted
    on POST (only the boot-time seed uses that value); a stray
    attempt 422s via the merged ``MerchantRuleSource`` enum above.
    """

    category_id: int
    keyword: str = Field(..., min_length=1, max_length=200)
    # Phase 28 — Optional so the route can distinguish "client
    # omitted priority" (auto-increment) from "client sent a
    # specific priority" (honour verbatim). The previous int=100
    # default silently collided with existing 100-priority rows in
    # the same category; the ``Optional[int] = None`` schema lets
    # ``model_fields_set`` / ``model_dump(exclude_unset=True)``
    # report the omission cleanly.
    priority: Optional[int] = None
    source: Optional[MerchantRuleSource] = None


class MerchantRuleUpdate(BaseModel):
    """Partial-update schema for PUT ``/api/merchant-rules/{id}``.

    Every field optional — clients send only what they're changing.
    Identity column (``id``) is intentionally NOT declared so
    clients cannot escalate or rewrite history via PUT.

    ``is_archived=true`` is the canonical DELETE path (soft-delete);
    a future PUT ``is_archived=false`` un-archives the row. The
    archive/unarchive direction is the ONLY delete/restore contract
    today (no hard-delete endpoint — Phase 24 keeps the table
    immutable for audit purposes; a future Phase 24.1+ admin tool
    could add an irreversible purge).
    """

    category_id: Optional[int] = None
    keyword: Optional[str] = Field(default=None, min_length=1, max_length=200)
    priority: Optional[int] = None
    is_archived: Optional[bool] = None


class MerchantRuleResponse(BaseModel):
    """GET / PUT / POST response shape for ``/api/merchant-rules/*``.

    ``category_name`` is denormalised on the read path so the FE
    never needs an N+1 follow-up to render the rule's pill badge.
    If a category is renamed, the next refetch shows the new label
    on every rule row.

    Phase 27 — ``source`` is always returned so the FE can render the
    provenance chip without a follow-up lookup. Immutable past
    creation (the PUT schema does NOT declare ``source``).
    """

    id: int
    category_id: int
    category_name: Optional[str] = None
    keyword: str
    priority: int
    is_archived: bool
    source: MerchantRuleSource
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FamilyMemberResponse(BaseModel):
    id: int
    name: str
    color: str
    is_self: bool
    is_archived: bool
    # Phase 16+ household profile. All three are nullable so a
    # freshly-created or never-edited row surfaces ``null`` to the
    # FE rather than a synthetically-derived default. The FE
    # renders missing values as "—" or omits the sub-line per
    # chip-row layout (see ``ui/app/settings/page.tsx``).
    relationship: Optional[Relationship] = None
    working_status: Optional[WorkingStatus] = None
    age: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# Phase 27 — Merchant Rules CSV import
# ----------------------------------------------------------------------


class MerchantRuleImportError(BaseModel):
    """Single per-row failure surfaced by ``POST /api/merchant-rules/import``.

    Row numbers are 1-indexed BY FILE LINE, NOT by header row — so
    row 2 = first data row (line 1 is the header). Lets the FE render
    the user-facing error "row 5 (file line 6): category 'Foo' not
    found" without ambiguity.

    ``reason`` is a short, human-facing message; full traceback
    stays in the server log.
    """

    row: int
    reason: str


class MerchantRuleImportResult(BaseModel):
    """Summary payload for ``POST /api/merchant-rules/import``.

    Three counters + a structured errors array so a FE can render
    ``"Imported 47 rules — 3 skipped (already exist), 2 had errors"``
    in one banner without follow-up calls.

    ``inserted`` = NEW rows created (with ``source='imported'``).
    ``skipped_existing`` = rows that matched an existing
    ``(category_id, keyword)`` UNIQUE constraint and were
    intentionally NOT updated (preserves the user's current edit).
    ``errors`` = structured per-row data failures that were DROPPED
    from the batch.
    """

    inserted: int
    skipped_existing: int
    errors: List[MerchantRuleImportError] = []


# ----------------------------------------------------------------------
# Phase 29 — duplicate detection (Settings → "Clean up duplicates").
# ----------------------------------------------------------------------


class MerchantDuplicateCandidate(BaseModel):
    """A single rule the FE should consider merging into the
    canonical. ``method`` is either ``"substring"`` (L1, deterministic)
    or ``"llm"`` (L2, semantic). The FE renders the rationale
    inline in the wizard modal so the user understands WHY the
    candidate was flagged before clicking Apply.
    """

    id: int
    keyword: str
    method: str
    confidence: float
    rationale: str


class MerchantDuplicateGroup(BaseModel):
    """One dedup group. The canonical is the rule to KEEP (never
    archived by Apply); the candidates are the rules the Apply
    action will soft-delete (is_archived=True).

    A group can have 1+ candidates — substring + LLM consolidation
    on the BE side dedupes multiple signals on the same candidate
    and keeps the strongest confidence.
    """

    canonical: dict
    candidates: List[MerchantDuplicateCandidate] = []


class MerchantDuplicateGroupList(BaseModel):
    """Top-level payload for ``GET /api/merchant-rules/duplicates``.

    ``groups`` is the list of dedup candidates the FE's wizard
    iterates. ``l1_count`` / ``l2_count`` are diagnostic counters
    so the FE can render "12 substring duplicates found, 0 LLM
    duplicates" without re-walking the payload.

    ``l2_status`` (Phase 29 follow-up) tells the FE the OUTCOME of
    the L2 pass so it can render an honest partial-success banner
    when the AI-assisted check didn't run (vs ran-but-found-zero).
    Without this field the FE can't distinguish "L2 returned no
    pairs" from "L2 never ran" — both surface as ``l2_count=0``,
    which is why the user previously saw a misleading "AI-assisted
    check found zero pairs" message while Ollama was actually
    offline. The four possible values:

    - ``"ok"`` — L2 ran; ``l2_count`` is the number of pairs
      flagged by the LLM. A 0 count is honest "L2 found nothing".
    - ``"offline"`` — Ollama was unreachable (ConnectError /
      TimeoutException). The FE should render a "semantic service
      offline" banner so the user understands why the AI check
      didn't contribute.
    - ``"malformed"`` — Ollama responded 200 but the body wasn't
      valid JSON (the JSON-mode grammar was ignored). A retry
      banner is the right FE response.
    - ``"skipped"`` — The user didn't opt in (``includeLlm=false``
      on the request). L2 was never attempted; the FE should NOT
      mention L2 in the banner at all.

    The L1 pass is always "ok" (deterministic + offline) so we
    don't carry a parallel ``l1_status`` field.
    """

    groups: List[MerchantDuplicateGroup] = []
    l1_count: int = 0
    l2_count: int = 0
    # REQUIRED (no default). A future route that forgets to set the
    # field would silently render as ``"skipped"`` instead of
    # erroring — a footgun we close by forcing every writer to
    # declare an explicit status. The L1-only route sets
    # ``"skipped"`` (L2 never attempted); the L1+L2 route sets one
    # of ``"ok"`` / ``"offline"`` / ``"malformed"`` (always
    # attempts L2).
    l2_status: Literal["ok", "offline", "malformed", "skipped"]


class MerchantDuplicateApplyRequest(BaseModel):
    """Body for ``POST /api/merchant-rules/duplicates/apply``.

    ``candidate_ids`` is the explicit list of rule ids the user
    agreed to merge. The route flips ``is_archived=True`` for each
    (soft-delete; the seed never resurrects archived rows on
    subsequent cold starts). The canonical is NEVER touched.
    """

    candidate_ids: List[int] = Field(default_factory=list)


class MerchantDuplicateApplyResult(BaseModel):
    """Summary payload for the apply endpoint.

    ``archived`` = number of rows the route soft-deleted. ``skipped``
    = rows the route did NOT archive because the user sent an id
    that didn't exist OR the row was already archived by an earlier
    Apply click (idempotent — the wizard can re-fire).
    """

    archived: int
    skipped: int


# ----------------------------------------------------------------------
# Phase 35 — Dashboard Redesign: Money Flow (Sankey + Trends)
# ----------------------------------------------------------------------


class SankeyNode(BaseModel):
    """A single node in the Sankey flow chart."""

    name: str
    node_type: str  # "income" | "expense" | "allocation" | "outcome"
    color: Optional[str] = None  # Hex override; falls back to node_type default
    # Phase 52+ — cashflow role tag so the FE's SankeyHero legend renders
    # role-based pills (earn / spend / save / invest / debt / transfer)
    # without guessing from node_type. Set by the /flows endpoint from
    # classify_cashflow() aggregation. None for empty-state nodes.
    role: Optional[str] = None
    # Phase C — hierarchical group tag for group-aware coloring.
    # One of: 'Income', 'Expenses', 'Debt', 'Investments', 'Transfer', None.
    # The FE uses this to propagate group colors to subcategory nodes.
    group: Optional[str] = None
    # Phase C — Sankey depth level (0=income sources, 1=total income pool,
    # 2=group nodes, 3=subcategory leaves, 4=outcomes).
    # The FE uses this for column positioning labels.
    level: Optional[int] = None


class SankeyLink(BaseModel):
    """A weighted edge from one Sankey node to another."""

    source: int  # Index into nodes array
    target: int  # Index into nodes array
    value: float  # Dollar amount flowing source → target


class DashboardFlowsResponse(BaseModel):
    """Sankey data model: nodes + links for the hero flow chart."""

    nodes: List[SankeyNode]
    links: List[SankeyLink]
    period_start: str  # "2026-06-01"
    period_end: str  # "2026-06-30"
    total_income: float


class TrendDataPoint(BaseModel):
    """A single month of income/spend/retained for the trend chart."""

    month: str  # "2026-06"
    income: float
    spend: float
    retained: float  # income - spend for that month


class DashboardTrendsResponse(BaseModel):
    """12 months of trend data for the line chart."""

    trends: List[TrendDataPoint]


# ----------------------------------------------------------------------
# Phase 35 (Phase 2) — Dashboard Breakdown (stacked bar)
# ----------------------------------------------------------------------


class BreakdownBucket(BaseModel):
    """A single spending bucket for the breakdown stacked bar."""

    label: str  # "Essential", "Flexible", "Debt", "Savings"
    amount: float
    color: str  # Hex color from the dashboard palette
    percentage: float  # 0-100; share of total spending


class DashboardBreakdownResponse(BaseModel):
    """Current-month spending broken into the four canonical buckets."""

    buckets: List[BreakdownBucket]
    total_spend: float
    period: str  # "2026-07"


# ----------------------------------------------------------------------
# Phase 30 — AI Finance Assistant
# ----------------------------------------------------------------------


class AssistantChatRequest(BaseModel):
    """Request body for ``POST /api/assistant/chat``.

    ``message`` is the user's natural-language question. The
    orchestrator loads SOUL.md + STYLE.md into the system prompt,
    asks the local Ollama LLM to pick a tool, dispatches, then
    generates a natural-language reply.

    Phase 30c — ``conversation_id`` is optional. When omitted (or
    ``None``), the orchestrator creates a NEW conversation and
    returns its id in the response. When provided, the message is
    appended to the existing conversation's history so multi-turn
    context is available to the LLM.
    """

    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[int] = None
    # Optional explicit Ollama model name. When omitted, the
    # orchestrator falls back to ``DEFAULT_MODEL``. The Scout UI
    # sends this when the user picks a model from the local picker.
    model: Optional[str] = None


class AssistantModelsResponse(BaseModel):
    """Response shape for ``GET /api/assistant/models``.

    - ``models``: every model installed in the local Ollama (sorted),
      so the Scout UI can render a picker instead of silently
      defaulting to ``DEFAULT_MODEL``.
    - ``default``: the service's current default model name.
    - ``loaded``: the subset of ``models`` currently warm in Ollama
      memory (empty when Ollama is offline — the FE renders a hint).
    """

    models: List[str] = Field(default_factory=list)
    default: Optional[str] = None
    loaded: List[str] = Field(default_factory=list)


class AssistantResponse(BaseModel):
    """Response shape for ``POST /api/assistant/chat``.

    - ``reply``: the natural-language answer (from the LLM's second
      call, or a graceful fallback if Ollama is offline).
    - ``tool_used``: the name of the tool that was dispatched, or
      ``None`` if no tool was called.
    - ``tool_result``: the raw tool output dict, or ``None``.
    - ``follow_ups``: a list of suggested next questions the user
      can click. Static in 30a; LLM-generated in 30c.
    - ``status``: ``"ok"`` (happy path), ``"offline"`` (Ollama
      unreachable — graceful fallback), or ``"error"`` (LLM parse
      failure — graceful fallback).
    - ``conversation_id``: Phase 30c — the id of the conversation
      this exchange belongs to. The FE stores this and sends it
      back on the next message to maintain multi-turn context.
    - ``conversation_title``: Phase 30c — the conversation's title
      (auto-generated from the first user message) so the FE's
      sidebar can render a meaningful label.
    """

    reply: str
    tool_used: Optional[str] = None
    tool_result: Optional[dict] = None
    follow_ups: List[str] = []
    status: Literal["ok", "offline", "error"]
    conversation_id: Optional[int] = None
    conversation_title: Optional[str] = None


class AssistantMessageResponse(BaseModel):
    """A single persisted chat message (user or assistant)."""

    id: int
    role: str
    content: str
    tool_used: Optional[str] = None
    tool_result: Optional[dict] = None
    follow_ups: List[str] = []
    status: str = "ok"
    created_at: datetime


class AssistantConversationResponse(BaseModel):
    """A conversation with its messages, returned by GET endpoints."""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[AssistantMessageResponse] = []


# ----------------------------------------------------------------------
# Phase 39 — Portfolio Holdings (positions import + live pricing)
# ----------------------------------------------------------------------


class HoldingCreate(BaseModel):
    """A single holding from a portfolio-positions CSV.
    Not exposed as a direct POST endpoint — created server-side
    during portfolio import."""

    symbol: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    last_price: Optional[float] = None
    current_value: float = 0.0
    cost_basis_total: Optional[float] = None
    type: Optional[str] = None


class HoldingResponse(BaseModel):
    """A single position returned to the Portfolio page."""

    id: int
    account_id: int
    account_name: Optional[str] = None
    symbol: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    last_price: Optional[float] = None
    current_value: float
    cost_basis_total: Optional[float] = None
    type: Optional[str] = None
    # Live-price fields (populated by refresh-prices endpoint)
    live_price: Optional[float] = None
    live_value: Optional[float] = None
    day_change_pct: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class PortfolioImportResponse(BaseModel):
    """Summary returned by ``POST /api/holdings/import``."""

    holdings_count: int
    accounts_created: int
    accounts_updated: int
    total_value: float
    warnings: List[str] = []
    account_ids: List[int] = []


class HoldingManualCreate(BaseModel):
    """Phase 41 — Request body for `POST /api/holdings/`.

    Accepts EITHER an existing `account_id` (resolved via Account.id)
    OR a new `account_name` (auto-created under a generic 'Portfolio'
    institution with `source='manual'` + `type='investment'`). Either
    must be non-null; the route 400s with a clear message when both
    are missing.

    Cost basis is RECOMPUTED server-side as `current_value` when
    omitted so a brand-new manual row doesn't silently land with
    `cost_basis_total=0` and the FE's "Gain/Loss" column shows a
    misleading +Infinity. Either current_value OR last_price is
    sufficient — if both omitted, the route 400s.
    """
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    symbol: str = Field(..., min_length=1, max_length=20)
    description: Optional[str] = None
    quantity: float = Field(..., ge=0)
    last_price: Optional[float] = Field(default=None, ge=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    cost_basis_total: Optional[float] = Field(default=None, ge=0)
    type: Optional[str] = None


class HoldingUpdate(BaseModel):
    """Phase 47 — partial-update schema for ``PUT /api/holdings/{id}``.

    The /portfolio page already exposes Add; user reported that
    editing a position afterward (especially the share count when a
    user buys more / sells some / corrects a parser-led typo) had
    no UI affordance — a complete ``.delete()`` + re-import was
    the workaround, which lost every other position on the same
    account. This schema enables an Edit path that mutates ONE
    row in place and recomputes the parent account's
    ``current_balance`` post-mutation.

    Every field optional — PATCH-style partial update. The route
    uses ``model_dump(exclude_unset=True)`` so a payload that
    omits ``quantity`` leaves the existing share count alone
    (mirrors the same patch contract on
    ``TransactionUpdate`` / ``AccountUpdate``).

    Whitelist contract — mirrors the same discipline used on
    AccountUpdate / TransactionUpdate:

    - ``account_id`` is intentionally NOT declared here so a
      client cannot ``PUT`` a holding onto a different account
      via the edit path. A cross-account transfer requires
      recomputing TWO different account balances atomically; a
      future "Transfer" affordance (Phase 48+) will own that
      contract. Without this exclusion, an inattentive FE bug
      would silently desync two account balances.
    - ``import_batch_id`` / ``id`` / ``created_at`` / ``updated_at``
      are NOT declared — same reason (identity + provenance
      immutability).

    Auto-derive: when the payload updates ``quantity`` AND
    ``last_price`` (and either ``current_value`` is omitted or
    also updated), the route DERIVES ``current_value =
    last_price * quantity`` server-side so the FE doesn't have to
    do manual arithmetic when the user just edits a quantity.
    This matches the same auto-derive rule on
    ``HoldingManualCreate`` so the edit-form feels identical.

    Quantity exact-zero semantics: ``quantity=0`` is rejected by
    the route's defence-in-depth ``<= 0`` 400 (Pydantic accepts
    ``ge=0`` so the schema-vs-route bound is consistent).
    """
    symbol: Optional[str] = Field(default=None, min_length=1, max_length=20)
    description: Optional[str] = None
    # Phase 47 -- ``quantity`` is intentionally NOT pinned with
    # ``ge=0`` (no Pydantic lower-bound) so the route's
    # defence-in-depth ``<= 0`` 400 fires on the boundary value
    # 0 with the human-friendly message ``"quantity must be > 0."``
    # instead of Pydantic's auto 422. Mirrors the same shape on
    # HoldingManualCreate's create_holding route (Phase 41).
    quantity: Optional[float] = None
    last_price: Optional[float] = Field(default=None, ge=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    cost_basis_total: Optional[float] = Field(default=None, ge=0)
    type: Optional[str] = None


# ----------------------------------------------------------------------
# Phase 42 — Batch analyst-ratings fetch
# ----------------------------------------------------------------------


class BatchRatingsRequest(BaseModel):
    """Phase 42 — request body for ``POST /api/analyst-ratings/batch``.

    The FE fires this on /portfolio mount so the top-10-by-weight
    holdings render an "Analyst Coverage" card + per-row chip in one
    round-trip. ``min_length=1`` rejects an empty payload (the FE
    always sends at least 1 ticker; an empty list is a code smell
    and the Pydantic 422 surfaces it loudly rather than silently
    no-op'ing). ``max_length=50`` is a hard ceiling -- above that a
    50-ticker batch would translate to ``asyncio.Semaphore(5)`` +
    100 simultaneous upstream calls which would 429 on Finnhub's
    free tier even with the rate-limit cap; the FE pages in chunks
    of <= 50 if a real portfolio ever exceeds that.

    Dedup + uppercase happen server-side (the route handler) so a
    FE that doesn't bother doing either doesn't pay the cost of
    duplicate upstream calls. Invalid ticker shape rejections are
    surfaced per-ticker (NOT as a whole-batch 400) so the FE renders
    the bad row as an "Uncovered" chip instead of failing the
    whole batch.
    """

    tickers: List[str] = Field(..., min_length=1, max_length=50)


class BatchRatingsResultItem(BaseModel):
    """Phase 42 — single entry in a batch response.

    ``status="ok"`` + ``data={...}`` makes the joined Finnhub
    payload (same shape as the GET route's response body) available
    to the FE without re-fetching. ``status="error"`` + ``error="..."``
    carries a user-readable detail string the FE renders in the
    per-row chip tooltip.

    Sharing the same payload shape between the GET and POST paths
    is the point: the FE's existing ``getAnalystRatings(symbol)``
    result type can be passed straight into the cache and the
    per-row chip without an extra shape-coercion layer.

    ``symbol`` is always populated, dedup'd + uppercased server-side
    -- so the FE can correlate returned entries to its request
    ticker list without an index lookup.
    """

    symbol: str
    status: Literal["ok", "error"]
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BatchRatingsResponse(BaseModel):
    """Phase 42 — response shape for ``POST /api/analyst-ratings/batch``.

    ``results`` preserves the dedup'd + uppercased server-side order
    of the input (not the FE's original ``tickers`` list order --
    duplicates were dropped), so the FE's response[i] aligns with
    its top-N weight-sorted ticker list rendered in screen order.

    Whole-batch errors (missing API key, oversized request) are
    surfaced via HTTP status codes (500 / 422) NOT as entries in
    ``results`` -- the FE distinguishes "server misconfig" from
    "this ticker is uncovered" by the contrast between an HTTP
    error banner and a per-row chip.
    """

    results: List[BatchRatingsResultItem] = []  # default allows `BatchRatingsResponse()` in tests


# ----------------------------------------------------------------------
# Phase 4 — Recommendation Approval Workflow
# ----------------------------------------------------------------------


class RecommendationLogCreate(BaseModel):
    """Request body for POST /api/recommendations/.

    Creates a new recommendation in ``pending`` status.
    ``metadata_json`` is an optional JSON string with extra context
    (category breakdown, related transaction ids, etc.).
    """

    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    priority: Literal["high", "medium", "low"] = "medium"
    category: str = "general"
    impact: Optional[str] = None
    metadata_json: Optional[str] = None


class RecommendationLogResponse(BaseModel):
    """A single recommendation log entry returned by GET endpoints."""

    id: int
    user_id: int
    title: str
    description: str
    priority: str
    status: str
    category: str
    impact: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RecommendationLogListResponse(BaseModel):
    """Paginated list of recommendation logs."""

    items: List[RecommendationLogResponse]
    total: int
    pending_count: int


class RecommendationActionRequest(BaseModel):
    """Request body for POST /api/recommendations/{id}/action.

    Transitions a recommendation from ``pending`` to the target status.
    ``action`` is one of: approve, deny, dismiss.
    """

    action: Literal["approve", "deny", "dismiss"]


# ----------------------------------------------------------------------
# Phase 2 — Policy-based rule evaluation
# ----------------------------------------------------------------------

class EvaluationItem(BaseModel):
    """A single evaluation result from the rule engine."""

    rule: str  # e.g. "portfolio_drift", "idle_cash", "goal_progress"
    status: Literal["ok", "warning", "critical"]
    message: str
    details: Optional[Dict[str, Any]] = None


class EvaluateResponse(BaseModel):
    """Response shape for GET /api/evaluate."""

    evaluations: List[EvaluationItem]
    policy_path: str
    evaluated_at: datetime

