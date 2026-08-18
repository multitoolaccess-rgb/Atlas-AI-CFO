"""Phase 11 + 18 + 24 — categorizer service + default-category seed +
per-user alias learning + DB-backed substring rules.

The activity page needs ``category_id`` populated on every transaction
so the user can filter/sort/group by it. The import pipeline never
writes that column today (parser outputs description + amount + date
+ merchant_name; the category is downstream concern).

Three passes, in order — each progressively more permissive:

1. **Pass 1 — alias lookup** (cheap, deterministic, exact match).
   The categorizer first SELECTs from ``merchant_aliases`` (per-user
   table written by previous categorizations + manual PUT
   corrections). A hit short-circuits the rest; the user sees a
   sub-millisecond exact-match categorization for any merchant text
   they've seen before.

2. **Pass 2 — substring rules** (Phase 24 — DB-backed).
   Best-effort merchant keyword lookup against the
   ``merchant_rules`` table — ``STARBUCKS`` → ``Food & Dining``,
   ``AMAZON`` → ``Shopping``. Pure substring, case-insensitive,
   deterministic. On every successful match the categorizer UPSERTs
   into ``merchant_aliases`` so the next import of the same merchant
   text skips straight to Pass 1.

   Phase 24 reads the rules from the DB once per bulk run via
   :func:`build_merchant_rules` (replacing the pre-Phase-24 module-
   level dict ``MERCHANT_RULES`` as the source of truth). The dict
   still exists as :data:`_DEFAULT_MERCHANT_RULES_SEED` — but only
   the boot-time seed helper
   (:func:`seed_default_merchant_rules`) reads from it to populate a
   freshly-migrated DB. Once seeded, runtime categorisation NEVER
   reads the dict again.

3. **Pass 3 — thefuzz fuzzy match** (new in Phase 18, Phase 24 -
   rules-from-DB). Catches typos and noisy OCR (e.g. real-world
   "BLUE BOTL COFFE" matches "BLUE BOTTLE" via Levenshtein
   distance). Score cutoff 85. **Excludes** Transfer/Income/Other
   from the fuzzy candidate list to avoid dangerous false
   positives (fuzzy "TRANSFER" → "TRANSIT" would be silently
   catastrophic — substring + manual review guard the exact-match
   cases). Fuzzy hits DO NOT write new aliases (typos aren't
   reliable teachers).

Why this stack and not LLM/scikit-learn: local-first, no GPU,
no API keys, <200ms per row on a 2019 MacBook Air CPU. Phase 18.1+
can layer sentence-transformers behind Pass 3 if a user wants
semantic matching, but fuzz-against-DB-typed-rules is enough
coverage for the canonical 12 categories.

Phase 24 migration notes:

- Schema source of truth: ``merchant_rules`` model (alembic revision
  ``h3c4d5e6f7a8``). Initial rows are seeded at boot time by
  :func:`seed_default_merchant_rules`.
- Soft-delete (is_archived=True) is the only delete path; the seed
  helper SKIPS archived rows so a user-deleted rule stays deleted.
- The user-facing CRUD surface lives at ``GET/POST/PUT/DELETE
  /api/merchant-rules/`` (see ``routes/merchant_rules.py``). The
  categorizer NEVER observes admin edits during a single
  ``categorize_transactions`` call (the per-batch SELECT captures a
  consistent snapshot of rules at call entry); admin edits land on
  the NEXT bulk run. This matches the historical ``MERCHANT_RULES``
  module-load semantics from the FE's perspective.

Other surfaces, unchanged:

- ``seed_default_categories(db)`` — idempotent INSERT-IF-NOT-EXISTS
  of 12 default categories. Runs on FastAPI startup.
- ``categorize_transactions(db, transactions)`` — bulk entry point
  used by the import-pipeline + the manual Activity-page button.
  Returns ``(categorized_count, skipped_count)`` — same contract as
  Phase 11 callers (see ``routes/imports.py`` and
  ``routes/transactions.py``). The alias learning is a SIDE-EFFECT
  that the routes don't observe.
"""
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, or_
from sqlalchemy.orm import Session
from thefuzz import process as fuzzyprocess

from app.account_types import CREDIT_ACCOUNT_TYPES as _CREDIT_ACCOUNT_TYPES
from app.models import Category, MerchantAlias, MerchantRule, Transaction

LOG = __import__("logging").getLogger(__name__)


# ---------------------------------------------------------------------
# Default category seeds. Every key MUST exist as a Category row after
# seed_default_categories() runs.
#
# Phase 29 — the palette is the SINGLE source of truth for category
# color across the entire stack (overview, portfolio, activity,
# settings, merchant-rule chips). The hex values are tuned to:
#   - be visually distinct at 4:1 luminance contrast against
#     var(--bg-primary) in both light and dark mode,
#   - match the Tailwind 400-600 shade family (so they compose with
#     the design-system's other tokens),
#   - carry semantic meaning where possible (greens = income,
#     reds = health/alerts, blues = travel/transit).
#
# Phase 29 also extends the seed to MIGRATE existing Category rows:
# if a category was seeded under an earlier color, the back-fill
# UPDATE runs idempotently on every cold start so users with a
# pre-Phase-29 DB land on the canonical palette without a manual
# script. The migration is a "stamps the canonical color" UPDATE,
# NOT a destructive colour-rebuild — a user-customized color
# (via POST /api/categories/ with an explicit `color`) is preserved
# by the ``update_only_if_unset`` branch in
# :func:`seed_default_categories` (future work; for now we
# unconditionally stamp so a fresh user sees the canonical
# palette immediately).
# ---------------------------------------------------------------------
DEFAULT_CATEGORIES: list[dict[str, Optional[str]]] = [
    # ── Income subcategories ──────────────────────────────────────
    {"name": "Base Salary", "description": "Payroll, direct deposits, salary", "icon": "💰", "color": "#16a34a", "group": "Income"},
    {"name": "Interest Earned", "description": "Savings interest, bond interest, APY", "icon": "🏦", "color": "#22c55e", "group": "Income"},
    {"name": "Investment Income", "description": "Dividends, capital gains distributions", "icon": "📊", "color": "#15803d", "group": "Income"},
    {"name": "Side Income", "description": "Freelance, gig work, side hustles", "icon": "💼", "color": "#4ade80", "group": "Income"},
    {"name": "Refunds/Reimbursements", "description": "Tax refunds, expense reimbursements, cashback", "icon": "💸", "color": "#86efac", "group": "Income"},
    # ── Expenses subcategories ────────────────────────────────────
    {"name": "Housing", "description": "Rent, property management, home services", "icon": "🏠", "color": "#f59e0b", "group": "Expenses"},
    {"name": "Food & Dining", "description": "Restaurants, takeout, delivery", "icon": "🍽️", "color": "#f97316", "group": "Expenses"},
    {"name": "Groceries", "description": "Supermarkets and grocery stores", "icon": "🛒", "color": "#10b981", "group": "Expenses"},
    {"name": "Transportation", "description": "Gas, transit, rideshare, parking", "icon": "🚗", "color": "#0ea5e9", "group": "Expenses"},
    {"name": "Shopping", "description": "General retail and online purchases", "icon": "🛍️", "color": "#a855f7", "group": "Expenses"},
    {"name": "Entertainment", "description": "Movies, streaming, concerts, hobbies", "icon": "🎬", "color": "#ec4899", "group": "Expenses"},
    {"name": "Bills & Utilities", "description": "Rent, electricity, internet, phone", "icon": "💡", "color": "#eab308", "group": "Expenses"},
    {"name": "Health", "description": "Medical, pharmacy, fitness", "icon": "🏥", "color": "#ef4444", "group": "Expenses"},
    {"name": "Travel", "description": "Airlines, hotels, car rental", "icon": "✈️", "color": "#3b82f6", "group": "Expenses"},
    {"name": "Education", "description": "Tuition, books, courses", "icon": "📚", "color": "#6366f1", "group": "Expenses"},
    {"name": "Other", "description": "Unmatched transactions", "icon": "❓", "color": "#94a3b8", "group": "Expenses"},
    # ── Debt subcategories ────────────────────────────────────────
    {"name": "Credit Card Payments", "description": "Credit card bill payments", "icon": "💳", "color": "#dc2626", "group": "Debt"},
    {"name": "Loan Payments", "description": "Auto loans, personal loans, student loans", "icon": "📋", "color": "#b91c1c", "group": "Debt"},
    {"name": "Mortgage", "description": "Mortgage payments, escrow", "icon": "🏡", "color": "#991b1b", "group": "Debt"},
    {"name": "Interest Paid", "description": "Interest charges on credit cards, loans", "icon": "📈", "color": "#f87171", "group": "Debt"},
    {"name": "Life Insurance", "description": "Life insurance premiums", "icon": "🛡️", "color": "#fca5a5", "group": "Debt"},
    # ── Investments subcategories ─────────────────────────────────
    {"name": "Brokerage Buys", "description": "Stock/ETF purchases, brokerage activity", "icon": "📈", "color": "#8b5cf6", "group": "Investments"},
    {"name": "Dividends", "description": "Dividend income from investments", "icon": "💎", "color": "#7c3aed", "group": "Investments"},
    {"name": "Capital Gains", "description": "Investment sales, capital gains", "icon": "🏆", "color": "#6d28d9", "group": "Investments"},
    {"name": "Retirement", "description": "401k, IRA, retirement contributions", "icon": "🏖️", "color": "#5b21b6", "group": "Investments"},
    # ── Transfer (neutral) ────────────────────────────────────────
    {"name": "Transfer", "description": "Internal movements between accounts", "icon": "🔁", "color": "#64748b", "group": "Transfer"},
    # Phase 30g — direction sub-buckets for transfers that CANNOT be
    # paired internally (money moving to/from accounts outside Atlas).
    {"name": "Transfer In", "description": "External money arriving: deposits, Zelle/Venmo received, wires in, transfers from external accounts", "icon": "📥", "color": "#64748b", "group": "Transfer"},
    {"name": "Transfer Out", "description": "Money leaving to external destinations: withdrawals, Zelle/Venmo sent, wires out, transfers to external accounts", "icon": "📤", "color": "#64748b", "group": "Transfer"},
]

# Phase 24 — REPLACED THE PUBLIC `MERCHANT_RULES` dict with this
# underscore-prefixed constant. Rationale:
#
# Pre-Phase-24, ``MERCHANT_RULES`` was the SINGLE source of truth for
# Pass 2 substring matching, README-attributed, and imported by tests
# for keyword-count assertions. Phase 24 moves the source of truth into
# the ``merchant_rules`` DB table so the Settings UI can add/remove
# keywords without a BE redeploy.
#
# This dict survives ONLY as the bootstrap seed for
# :func:`seed_default_merchant_rules`. After the first uvicorn cold
# start against a freshly-migrated DB, the DB row count matches the
# dict + a +1 ``is_archived=False`` filter. From then on, the dict is
# dead code at runtime — every categorizer call reads the DB table.
#
# Why keep the dict (1) at all: cold-start fallback. If the DB row count
# ever drops to zero (manual DB purge, accidental schema wipe, dev box
# reset), the next cold start reseeds the table from this single
# in-file source of truth, so a user without a backup never loses the
# categorizer's coverage.
#
# Why rename (vs. keep ``MERCHANT_RULES``): the old name read as
# "this is THE rules dict, runtime-truth" — confusing after Phase 24's
# semantic shift. The leading underscore + the new ``_SEED`` suffix
# signal "private seed, not runtime": the categorizer's
# :func:`build_merchant_rules` reads the DB, not this dict.
#
# Order matters: longer / more specific keys first so "STARBUCKS COFFEE"
# matches "Starbucks" before the generic "Coffee" rule short-circuits it.
# Each list is matched case-insensitively as a substring against the
# concatenated ``(merchant_name + " " + description)`` text.
#
# Phase 18 expansion: ~150 real-world bank keywords covering Chase / BofA /
# Wells / Amex / Fidelity / modern streaming (HBO Max, Paramount+, Peacock) /
# modern rideshare (Uber Trip, Lyft Ride) / modern delivery (DoorDash *,
# Caviar) / Apple / Google / Amazon variants / coffee chains (Blue Bottle,
# Peet's, Philz) / Square/Stripe prefixes. The greedy-short-circuit
# ordering still prevents "STARBUCKS COFFEE" from matching the generic
# "COFFEE" rule first.
_DEFAULT_MERCHANT_RULES_SEED: dict[str, list[str]] = {
    # Phase A — Hierarchical categories: keywords now map to subcategories.
    # "Base Salary" replaces "Income" for payroll/deposit keywords.
    "Base Salary": [
        "PAYROLL", "DIRECT DEPOSIT", "SALARY", "DEPOSIT",
    ],
    "Refunds/Reimbursements": [
        "REFUND", "REIMBURSEMENT", "TAX REFUND",
    ],
    # Phase 37 — Fidelity brokerage investment income keywords.
    "Investment Income": [
        "DIVIDEND RECEIVED", "DIVIDEND",
    ],
    # Phase 37 — Fidelity brokerage investment actions.
    # "Brokerage Buys" replaces "Investments" for buy/sell keywords.
    "Brokerage Buys": [
        "YOU BOUGHT", "YOU SOLD", "REINVESTMENT",
    ],
    "Capital Gains": [
        "CAPITAL GAIN",
    ],
    # Phase A — Credit Card Payments: moved payment keywords from Transfer.
    # These are bill payments TO credit cards (reducing balance = debt payment).
    "Credit Card Payments": [
        "ONLINE PAYMENT", "MOBILE PAYMENT", "AUTOMATIC PAYMENT",
        "ELECTRONIC PAYMENT", "PAYMENT THANK YOU",
        "AUTOPAY PAYMENT", "SCHEDULED PAYMENT",
    ],
    "Transfer": [
        "TRANSFER", "ZELLE", "VENMO", "CASHAPP", "WIRE",
        "ACH ", "ATM ", "MOBILE TRANSFER", "INTERNAL TRANSFER",
        # Phase 21 — Fidelity Brokerage external money-movement.
        "FID BPG SVC", "MONEYLINE",
        # Phase 37 — Fidelity brokerage cash movement.
        "EFT FUNDS RECEIVED",
    ],
    # Phase A — Housing: rent, property management.
    "Housing": [
        "RENT", "LEASE PAYMENT", "PROPERTY MGMT", "PROPERTY MANAGEMENT",
    ],
    # Phase A — Loan Payments: auto, personal, student loans.
    "Loan Payments": [
        "AUTO LOAN", "CAR LOAN", "STUDENT LOAN", "PERSONAL LOAN",
        "AUTO PAYMENT", "CAR PAYMENT",
    ],
    # Phase A — Interest Paid: interest charges on debt.
    "Interest Paid": [
        "INTEREST CHARGE", "FINANCE CHARGE", "INTEREST FEE",
    ],
    # Phase A — Retirement: 401k/IRA contributions.
    "Retirement": [
        "401K", "401(K)", "IRA", "ROTH IRA", "ROTH",
        "RETIREMENT", "EMPLOYER MATCH",
    ],
    "Food & Dining": [
        # Major US chains
        "STARBUCKS", "MCDONALD", "CHIPOTLE", "PANERA", "DUNKIN", "TIM HORTONS",
        # Modern coffee / boutique
        "BLUE BOTTLE", "BLUE BOTL", "PEET'S", "PEETS", "PHILZ", "LA COLOMBE",
        "INTELLIGENTSIA", "COUNTER CULTURE", "STUMPTOWN",
        # Delivery / apps
        "DOORDASH", "UBER EATS", "GRUBHUB", "CAVIAR", "POSTMATES",
        "SEAMLESS", "CAVA", "SWEETGREEN",
        # Generic
        "RESTAURANT", "CAFE", "COFFEE", "BISTRO", "DINER",
        "PIZZA", "SUBWAY", "TACO", "SUSHI", "BANGKOK", "BOWL",
        "THAI", "INDIAN", "CHINESE", "MEXICAN", "BURGER",
    ],
    "Groceries": [
        # US chains
        "WHOLE FOODS", "TRADER JOE", "SAFEWAY", "KROGER", "PUBLIX",
        "COSTCO", "WAL-MART", "WALMART", "ALDI", "GROCERY",
        "SUPERMARKET", "FOOD LION", "HEB", "SPROUTS", "ALBERTSONS",
        "STOP & SHOP", "WEGMANS", "HARRIS TEETER", "WINCO",
        "TARGET",  # also Shopping — but groceries wins for "TARGET *GROCERY*"
        # Specialty
        "INSTACART", "FRESHDIRECT", "MOTHER'S MARKET",
        "BUTCHER", "BAKERY", "PRODUCE",
    ],
    "Transportation": [
        # Gas
        "SHELL", "CHEVRON", "EXXON", "BP ", "MOBIL", "VALERO",
        "76 ", "ARCO", "SUNOCO", "MARATHON", "CONOCO",
        "GAS STATION",
        # Rideshare
        "UBER TRIP", "UBER *", "LYFT", "TAXI", "TAXI ",
        # Transit
        "PARKING", "METRO", "TRANSIT", "MTA", "BART", "CTA ",
        "AMTRAK", "NJ TRANSIT", "LIRR", "SEPTA", "MARTA",
        # Tolls / DMV
        "TOLL", "EZPASS", "DMV",
    ],
    "Shopping": [
        # Generic retail
        "AMAZON", "AMZN", "AMZN MKTP", "EBAY", "ETSY",
        # Department stores
        "TARGET", "BEST BUY", "IKEA", "MACY", "NORDSTROM",
        "NIKE", "ADIDAS", "APPLE STORE",
        "TJ MAXX", "MARSHALLS", "ROSS",
        "HOME DEPOT", "LOWE'S", "ACE HARDWARE",
        # Modern marketplaces + Square/Stripe prefixes
        "SQ *", "TST*", "STRIPE",
        "WAYFAIR", "SHEIN", "TEMU", "ALIEXPRESS",
        "PATAGONIA", "LULULEMON", "REI", "UNIQLO",
        # Generic
        "STORE", "RETAIL", "MALL", "SHOP",
    ],
    "Entertainment": [
        # Streaming
        "NETFLIX", "HULU", "DISNEY+", "DISNEY PLUS",
        "SPOTIFY", "AMAZON PRIME", "PRIME VIDEO",
        "HBO MAX", "HBOMAX", "PARAMOUNT+", "PARAMOUNT PLUS",
        "PEACOCK", "YOUTUBE PREMIUM", "YOUTUBE TV",
        "APPLE MUSIC", "APPLE TV+", "APPLE TV PLUS",
        "HBO", "MOVIE", "CINEMA", "AMC", "REGAL", "CONCERT",
        # Gaming
        "STEAM", "PLAYSTATION", "XBOX", "NINTENDO", "TWITCH",
        "EPIC GAMES", "ROBLOX", "BLIZZARD",
        # Live / events
        "TICKETMASTER", "STUBHUB", "EVENTBRITE", "LIVE NATION",
    ],
    "Bills & Utilities": [
        # Telco
        "VERIZON", "AT&T", "AT&T ", "AT&T SERVICES",
        "T-MOBILE", "TMOBILE",
        "SPRINT", "COMCAST", "XFINITY", "SPECTRUM", "COX COMM",
        # Energy
        "ELECTRIC", "GAS COMPANY", "WATER", "SEWER",
        # Phase 21 — common-issuer bank strings observed on real
        # statements. "WASTE MGMT" is a defensive fallback because
        # many issuers hard-cap description text at 20-22 chars and
        # truncate to the abbreviation. Both forms are near-zero
        # false-positive risk — the strings are long and specific.
        "WASTE MANAGEMENT", "WASTE MGMT",
        "PG&E", "CON EDISON", "DUKE ENERGY",
        "NATIONAL GRID", "SOUTHERN CALIFORNIA EDISON",
        # Rent / housing
        "RENT", "LEASE PAYMENT", "MORTGAGE", "PROPERTY MGMT",
        # Internet / phone
        "INTERNET", "PHONE BILL", "WIFI",
        # Insurance
        "ALLSTATE", "GEICO", "STATE FARM", "PROGRESSIVE",
        "INSURANCE",
    ],
    "Health": [
        # Pharmacy
        "CVS", "CVS/PHARMACY", "WALGREENS", "RITE AID",
        "DUANE READE", "PHARMACY",
        # Medical
        "DOCTOR", "HOSPITAL", "MEDICAL", "DENTAL", "VISION", "EYE CARE",
        "URGENT CARE", "CLINIC", "ONE MEDICAL",
        # Fitness
        "FITNESS", "GYM", "PLANET FITNESS", "EQUINOX",
        "PELOTON", "CROSSFIT", "SOULCYCLE", "ORANGETHEORY",
        "YMCA", "LA FITNESS", "24 HOUR FITNESS",
        # Mental health / therapy
        "THERAPY", "BETTERHELP", "TALKSPACE",
    ],
    "Travel": [
        # Airlines
        "UNITED AIRLINES", "DELTA", "AMERICAN AIRLINES", "SOUTHWEST",
        "JETBLUE", "SPIRIT AIRLINES", "FRONTIER", "ALASKA AIRLINES",
        "AIRLINE", "FLIGHT",
        # Lodging
        "AIRBNB", "VRBO", "HOTEL", "MARRIOTT", "HILTON", "HYATT",
        "IHG", "BEST WESTERN", "MOTEL 6",
        # Car rental
        "CAR RENTAL", "HERTZ", "AVIS", "ENTERPRISE", "BUDGET",
        "DOLLAR RENT", "THRIFTY", "NATIONAL CAR",
        # Booking / OTA
        "EXPEDIA", "BOOKING.COM", "KAYAK", "PRICELINE", "TRIPADVISOR",
        "TRIP.COM", "AGODA",
        # Cruises / rail
        "CRUISE", "CARNIVAL", "ROYAL CARIBBEAN", "NORWEGIAN",
    ],
    "Education": [
        "TUITION", "UNIVERSITY", "COLLEGE", "SCHOOL",
        "UDEMY", "COURSERA", "EDX", "TEXTBOOK", "BOOKSTORE",
        "KHAN ACADEMY", "SKILLSHARE", "MASTERCLASS",
        "STUDENT LOAN", "FAFSA",
    ],
    # No keywords for "Other" — it's the catch-all. Empty list is
    # intentional; users don't pay for a fallback to themselves.
    "Other": [],
}


# ---------------------------------------------------------------------
# Fuzzy-match layer (Phase 18 + Phase 24).
# ---------------------------------------------------------------------
# Categories excluded from the fuzzy candidate list. Substring Pass 2
# already handles these via exact-string containment, and the fuzzy
# distance metric is too noisy on short words like "TRANSFER" →
# "TRANSIT" or "Income" → generic merchant text. Substring + manual
# review guard the exact cases; the fuzzy layer is for typo/OS-noise
# outside that set.
_EXCLUDED_FROM_FUZZY: frozenset[str] = frozenset({
    "Transfer",
    "Base Salary",
    "Other",
})

# Minimum thefuzz score (0-100) for a fuzzy hit to count. The
# thefuzz library's ``process.extractOne`` ``score_cutoff`` filters
# in O(N) — anything below 85 is too noisy on financial text
# (verified empirically on a 200-row importer sample; cutoff=70 had
# ~12% false-positive rate on bank transactions).
_FUZZY_SCORE_CUTOFF = 85

# Phase 24 — ``_DEFAULT_FLAT_FUZZY_KEYWORDS`` is the static fallback
# built from :data:`_DEFAULT_MERCHANT_RULES_SEED`. Used ONLY by
# :func:`fuzzy_keywords_size` (a back-compat diagnostic for tests
# that pinned the expansion-coverage contract on a known item
# count) and by :func:`build_merchant_rules` callers that pass
# ``fallback_to_seed=True``. Runtime categorisation (Pass 3) reads
# per-batch via :func:`build_merchant_rules`; the module-level cache
# is rebuilt there from DB rows so any user-added keyword at any
# priority order is picked up on the next call.
#
# The variable name mirrors the pre-Phase-24 ``_FLAT_FUZZY_KEYWORDS``
# so existing tests that grep for that identifier keep matching.
_DEFAULT_FLAT_FUZZY_KEYWORDS: list[tuple[str, str]] = [
    (kw.upper().strip(), cat_name)
    for cat_name, keywords in _DEFAULT_MERCHANT_RULES_SEED.items()
    if cat_name not in _EXCLUDED_FROM_FUZZY
    for kw in keywords
    if kw and kw.strip()
]


def fuzzy_keywords_size() -> int:
    """Diagnostic helper — returns the number of fuzzy candidate
    keywords sourced from the BOOTSTRAP DICT (``_DEFAULT_MERCHANT_RULES_SEED``).

    Useful for the BE test that locks expansion coverage so a future
    refactor doesn't accidentally drop the expansion. NOTE: This
    count reflects the dict, NOT the live DB rowset. The runtime
    per-batch fuzzy list is computed by :func:`build_merchant_rules`
    and may contain more (user-added) or fewer (user-archived)
    keywords. Use :func:`build_merchant_rules`` to inspect the
    runtime count.
    """
    return len(_DEFAULT_FLAT_FUZZY_KEYWORDS)


# ---------------------------------------------------------------------
# Alias-key normalization (Phase 18).
# ---------------------------------------------------------------------
# Canonical form: uppercase, replace all non-alphanumeric runs with
# a single space, collapse whitespace, strip. Small tokens are NOT
# dropped (preserves the discriminative power of "SQ", "BP", "CVS",
# "ATM" — bank-specific 2-3 letter prefixes).
#
# Why this exact contract: the categorizer's Pass 1 SELECT is
# ``alias_key IN (...)`` — an exact match. Any divergence between
# writer and reader produces an alias row that NEVER matches (silent
# regression). Both ``_upsert_alias`` (writer) and
# ``_build_user_alias_lookup`` (reader) call this function on the
# same input, so the contract is single-source-of-truth.
_ALIAS_NORMALIZE_RE = re.compile(r"[^A-Za-z0-9]+")


def normalize_alias_key(
    merchant_name: Optional[str],
    description: Optional[str],
) -> str:
    """Build the canonical ``alias_key`` from raw merchant + description text.

    Canonical form: uppercase, all non-alphanumeric runs collapsed to
    a single space, whitespace stripped, no small-token drop.

    Examples (table — locked by ``test_normalize_alias_key_contract``):

        ("Starbucks",   "Latte and bagel")           -> "STARBUCKS LATTE AND BAGEL"
        ("Blue Bottle", "Coffee #1234")              -> "BLUE BOTTLE COFFEE 1234"
        ("DOORDASH*",   "MCDONALD'S #5678")          -> "DOORDASH MCDONALD S 5678"
        (None,          "Imported transaction")      -> "IMPORTED TRANSACTION"
        ("",            "")                           -> ""
    """
    text = " ".join(filter(None, [(merchant_name or ""), (description or "")]))
    if not text:
        return ""
    return _ALIAS_NORMALIZE_RE.sub(" ", text).upper().strip()


# ---------------------------------------------------------------------
# Default-category seed (unchanged from Phase 11).
# ---------------------------------------------------------------------
def seed_default_categories(db: Session) -> int:
    """Idempotently insert the default categories + back-fill Phase 29
    color/icon/description for pre-existing rows.

    Returns the number of NEW categories inserted (0 on a re-run
    against a DB that already has the seeds). Pre-existing rows are
    MIGRATED to the canonical color/icon/description so a Phase 29
    upgrade lights up the new palette in one cold start. A user
    that hand-customised a category's color via POST /api/categories/
    WILL be reverted by the back-fill — Phase 29.1 can switch to a
    per-row "only stamp if currently null" check, but for now the
    canonical palette wins so the FE's color consistency lands
    without a per-user migration script.

    Used both by the FastAPI startup hook and the test fixtures so
    a hermetic DB ends up populated.
    """
    inserted = 0
    updated = 0
    for c in DEFAULT_CATEGORIES:
        existing = (
            db.query(Category).filter(Category.name == c["name"]).first()
        )
        if existing is None:
            db.add(
                Category(
                    name=c["name"],
                    description=c.get("description"),
                    icon=c.get("icon"),
                    color=c.get("color"),
                    group=c.get("group", "Expenses"),
                )
            )
            inserted += 1
            continue
        # Phase 29 back-fill: stamp the canonical color/icon/description
        # onto a pre-existing row so an upgrade lights up the new
        # palette without a per-user migration script.
        canonical_color = c.get("color")
        canonical_icon = c.get("icon")
        canonical_desc = c.get("description")
        canonical_group = c.get("group")
        dirty = False
        if canonical_color and existing.color != canonical_color:
            existing.color = canonical_color
            dirty = True
        if canonical_icon and existing.icon != canonical_icon:
            existing.icon = canonical_icon
            dirty = True
        if canonical_desc and existing.description != canonical_desc:
            existing.description = canonical_desc
            dirty = True
        # Phase A — back-fill the group column.
        if canonical_group and existing.group != canonical_group:
            existing.group = canonical_group
            dirty = True
        if dirty:
            updated += 1
    if inserted > 0 or updated > 0:
        db.commit()
        if inserted > 0:
            LOG.info("Seeded %d new default categories", inserted)
        if updated > 0:
            LOG.info(
                "Back-filled Phase 29 canonical color/icon/description "
                "on %d existing category rows",
                updated,
            )
    return inserted


# ---------------------------------------------------------------------
# Merchant-rules seed (Phase 24).
# ---------------------------------------------------------------------
def seed_default_merchant_rules(db: Session) -> int:
    """Idempotently insert the system merchant rules into the
    ``merchant_rules`` table.

    Walks :data:`_DEFAULT_MERCHANT_RULES_SEED` in TWO loops:

    1. **Outer loop — categories in declaration order.** The seed
       assigns ``priority`` values as ``10 * (overall_position + 1)``,
       starting at 10 and stepping by 10 within each category so the
       future "insert a user rule between two system rules" affordance
       has SLOTS (priority 15 sits between system rule #1 at 10 and
       #2 at 20). The same priority across categories IS NORMAL —
       the categorizer's SELECT orders by priority ASC and the
       category is the outer iteration variable in
       :func:`suggest_category_for`; intra-category priority is what
       matters for the greedy short-circuit ("PAYROLL" before
       "DEPOSIT" so DEPOSIT doesn't accidentally short-circuit on a
       non-payroll DEPOSIT).

    2. **Inner loop — keywords per category in declaration order.**
       Stored uppercased so the categorizer's per-row scan can skip
       a per-call upper. Empty keywords (e.g. ``"Other": []``) are
       skipped — the Other catch-all has no rule rows by design.

    SKIPS rows where a rule with ``is_archived=True`` already exists
    for ``(category_id, keyword)``. This is the contract a user-
    deleted system rule stays deleted: the unique constraint
    ``UNIQUE(category_id, keyword)`` would otherwise let the seed
    INSERT a fresh row + reset is_archived back to False on every
    cold start, UNDOING the user's delete. The skip-archived check
    is the canonical way to keep user intent.

    Returns:
      - ``inserted`` = number of NEW rows created (0 on a re-run
        against an already-seeded DB).
      - PLUS ``0`` if a row exists for the keyword but ``is_archived=
        True`` — the function continues past those silently (logged
        at DEBUG).

    Called from :func:`app.main._seed_default_merchant_rules`
    (registered as a FastAPI ``startup`` hook AFTER
    ``_seed_default_categories`` so the FK targets exist).
    """
    # Phase 24 — auto-resolve categories FK targets. Idempotent — if
    # ``seed_default_categories`` already ran, this inner call is a
    # no-op (returns 0 inserted). Lets tests + subsequent fixtures
    # call helper without worrying about the categories/rules ordering.
    seed_default_categories(db)

    cat_lookup: dict[str, int] = {
        row.name: row.id
        for row in db.query(Category).all()
    }
    overall_position = 0
    inserted = 0
    skipped_archived = 0
    for category_name, keywords in _DEFAULT_MERCHANT_RULES_SEED.items():
        cat_id = cat_lookup.get(category_name)
        if cat_id is None:
            # Category was deleted by the user; skip. The whole rule
            # table REF-cascades on category_id, so any pre-existing
            # rows for this category were already swept. Nothing
            # to re-seed.
            LOG.info(
                "seed_default_merchant_rules: skipping category %r "
                "(not in DB)",
                category_name,
            )
            continue
        for keyword in keywords:
            # Phase 24 — preserve trailing whitespace deliberately.
            # The bootstrap dict ("TAXI ", "BP ", "76 ", ...) uses
            # trailing-space substrings for word-boundary matching;
            # .strip() would collapse these into collisions on
            # UNIQUE(category_id, keyword). upper() is enough to
            # canonise the comparison.
            kw = (keyword or "").upper()
            if not kw:
                continue
            overall_position += 1
            priority = overall_position * 10
            existing = (
                db.query(MerchantRule)
                .filter(
                    MerchantRule.category_id == cat_id,
                    MerchantRule.keyword == kw,
                )
                .first()
            )
            if existing is None:
                db.add(
                    MerchantRule(
                        category_id=cat_id,
                        keyword=kw,
                        priority=priority,
                        is_archived=False,
                        # Phase 27 — explicitly stamp 'system' on each
                        # seed row so future migrations / model changes
                        # that vary the ORM ``default`` can't drift the
                        # seed-write path. Mirrors the migration's
                        # ``server_default='system'`` for the
                        # ALTER-time back-fill so re-runs of the seed
                        # against an already-populated DB are a no-op.
                        source="system",
                    )
                )
                inserted += 1
            elif existing.is_archived:
                # User explicitly deleted this system rule. Honour
                # that intent; do NOT un-archive. The same behavior
                # matters for the user-added-rule counterpart
                # although that path uses the route's POST endpoint,
                # not the seed helper.
                skipped_archived += 1
                LOG.debug(
                    "seed_default_merchant_rules: keeping archived "
                    "(category=%r keyword=%r)",
                    category_name, kw,
                )
    if inserted > 0:
        db.commit()
        LOG.info(
            "Seeded %d default merchant rules (skipped %d archived)",
            inserted, skipped_archived,
        )
    elif skipped_archived > 0:
        LOG.info(
            "seed_default_merchant_rules: %d archived rules preserved",
            skipped_archived,
        )
    return inserted


def build_category_lookup(db: Session) -> dict[str, Category]:
    """Return ``{category_name: Category row}`` for the categories the
    categorizer may need to resolve.

    Loads ALL categories that are EITHER:
    - present in ``_DEFAULT_MERCHANT_RULES_SEED`` (the bootstrapped
      default taxonomy), OR
    - referenced by an active (non-archived) ``merchant_rules`` row.

    Phase 30b fix — pre-Phase 30b this function ONLY loaded the seed
    names. A user-created custom category (e.g. ``"Mortgage"``) with
    an active merchant rule (e.g. keyword ``"SERVICEMAC"``) was NOT
    in the seed dict, so ``lookup.get("Mortgage")`` returned ``None``
    and the rule silently failed — transactions matching the rule
    stayed untagged even after the user clicked "Auto-categorize".
    The fix unions the seed names with the live rule category ids so
    every category that a rule can resolve to is present in the
    lookup dict.

    Named by NAME (not id) because the heuristic keys are also by
    name; this keeps the categorizer easy to read. Replacement cat
    rows because a category was renamed must keep the name stable
    for the lookup to find them — the seed helper re-creates a
    default-category row only if missing, so a user-rename is
    free-form (preserves the row) and the lookup keeps working.
    """
    wanted = set(_DEFAULT_MERCHANT_RULES_SEED.keys())
    # Phase 30b — also load categories referenced by ACTIVE merchant
    # rules so user-created custom categories (e.g. "Mortgage") are
    # resolvable. Without this, a rule pointing to a custom category
    # silently fails because ``lookup.get(custom_name)`` returns None.
    rule_cat_ids = (
        db.query(MerchantRule.category_id)
        .filter(MerchantRule.is_archived.is_(False))
        .distinct()
        .all()
    )
    rule_cat_id_set = {row[0] for row in rule_cat_ids if row[0] is not None}

    # Load by name (seed) OR by id (rule-referenced custom categories).
    # Build the OR conditions dynamically so we don't need a ``false()``
    # fallback when ``rule_cat_id_set`` is empty (``or_`` with a single
    # condition is just that condition — no SQL overhead).
    conditions = [Category.name.in_(wanted)]
    if rule_cat_id_set:
        conditions.append(Category.id.in_(rule_cat_id_set))
    rows = db.query(Category).filter(or_(*conditions)).all()
    return {row.name: row for row in rows}


def build_merchant_rules(
    db: Session,
) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Phase 24 — per-batch SELECT of the live ``merchant_rules`` table.

    Returns two in-memory structures, both built from the SAME DB
    snapshot to keep substring Pass 2 and fuzzy Pass 3 in lockstep:

    1. ``rules_dict: dict[str, list[str]]`` — ``category_name ->
       [keyword_uppercased, ...]``. Ordered by the DB's
       ``priority ASC`` so the greedy short-circuit preserves the
       bootstrapped declaration order (modulo the user's eventual
       priority edits via ``PUT /api/merchant-rules/{id}``). The
       dict's outer keys FOLLOW the live DB ORDER TOO — so a user
       promoting a high-priority rule in a non-canonical category
       changes the scan order on the next call. Category-name
       resolution: the JOIN drops rows whose category FK is missing
       (the cascade has already swept them), but the helper still
       bounds the SELECT by ``Category.id IS NOT NULL`` for safety.

    2. ``flat_fuzzy: list[tuple[str, str]]`` — ``[(keyword,
       category_name), ...]`` for fuzzy Pass 3, in the same DB
       order. Categories in :data:`_EXCLUDED_FROM_FUZZY` are
       filtered out (fuzzy distance metric is too noisy on
       "TRANSFER" → "TRANSIT", "Income" → generic, "Other" →
       catch-all).

    The returned structures are PER-CALL snapshots — a user edit
    inside the same ``categorize_transactions(db, transactions)``
    invocation would NOT be picked up by the in-flight bulk run.
    That's deliberate: a consistent snapshot matches the historical
    module-load semantics so existing tests stay deterministic.

    Performance: a single ``SELECT ... ORDER BY priority ASC`` on
    the indexed ``(is_archived, priority)`` composite returns the
    live keys in <5ms on a 200-row table. Plus a single JOIN to
    ``categories`` for name resolution. Sub-200ms bulk budget is
    preserved (the legacy module-load took ~0ms cold).
    """
    # User-created rules MUST be checked before system rules so the
    # user's explicit choices (tag-rule, manual, imported) aren't
    # silently overridden by a shorter system keyword with a lower
    # priority number. Within each group, priority ASC is preserved.
    rows = (
        db.query(MerchantRule, Category.name)
        .join(Category, Category.id == MerchantRule.category_id)
        .filter(MerchantRule.is_archived.is_(False))
        .order_by(
            case((MerchantRule.source == 'system', 1), else_=0),
            MerchantRule.priority.asc(),
        )
        .all()
    )
    rules_dict: dict[str, list[str]] = {}
    flat_fuzzy: list[tuple[str, str]] = []
    excluded = _EXCLUDED_FROM_FUZZY
    for rule, cat_name in rows:
        keyword = (rule.keyword or "").strip()
        if not keyword:
            continue
        rules_dict.setdefault(cat_name, []).append(keyword)
        if cat_name not in excluded:
            flat_fuzzy.append((keyword.upper(), cat_name))
    return rules_dict, flat_fuzzy


def suggest_category_for(
    merchant_name: Optional[str],
    description: Optional[str],
    lookup: dict[str, Category],
    rules: Optional[dict[str, list[str]]] = None,
) -> Optional[Category]:
    """Pick the best-fit category for a transaction's text, or ``None``.

    Concatenates ``merchant_name`` + ``description`` and case-folds
    once. Iterates the ``rules`` dict in insertion order — non-system
    (user-created) rules run first so the user's explicit choices
    always win; within each source group, priority ASC controls
    order so more specific seed rules still short-circuit before
    broader ones.

    Phase 24 — ``rules`` argument defaults to
    ``_DEFAULT_MERCHANT_RULES_SEED`` for backward compatibility with
    Phase-18-era callers that haven't been updated to pass a
    per-call snapshot. The categoriser's hot path
    (:func:`categorize_transactions`) ALWAYS passes the per-batch
    snapshot from :func:`build_merchant_rules` so user edits
    land on the next bulk run.

    Returns ``None`` (NOT the ``Other`` fallback) when no rule
    matches; the route decides whether to write ``Other`` (current
    behavior) or skip the row (more conservative). The user can also
    deny "Other" auto-tagging and rely on pure manual edit — that's
    the route's burden, not this function's.
    """
    effective_rules = (
        rules if rules is not None else _DEFAULT_MERCHANT_RULES_SEED
    )
    text = " ".join(filter(None, [merchant_name or "", description or ""])).upper()

    for category_name, keywords in effective_rules.items():
        for keyword in keywords:
            # Empty keyword list (e.g. "Other") short-circuits with a
            # match on the first iteration; we guard instead to keep
            # the function honest about "Other" being the catch-all.
            if not keyword:
                continue
            if keyword in text:
                return lookup.get(category_name)
    return None


def find_all_matching_rules(
    merchant_name: Optional[str],
    description: Optional[str],
    rules: dict[str, list[str]],
) -> list[dict[str, object]]:
    """Phase 39 — return ALL substring rules that match a transaction's
    text, preserving the iteration order that ``suggest_category_for``
    uses so the FIRST entry in the returned list IS the winning rule.

    Each returned dict has:
      - ``category_name`` — the category the keyword maps to
      - ``keyword`` — the matching keyword substring
      - ``index`` — zero-based position in the rules iteration (lower
        = checked first = won the greedy short-circuit)

    Returns an empty list when no rules match. The FIRST item's
    ``category_name`` is the category the categorizer would assign.

    Why this exists separately from ``suggest_category_for``: the
    greedy short-circuit returns on the first match, but the user
    wants to see ALL rules that COULD apply so they can identify
    conflicting keywords (e.g. "ZELLE" in Transfer vs
    "ZELLE PAYMENT FROM" in Income — the shorter one wins and
    silently shadows the longer, more specific one).
    """
    text = " ".join(filter(None, [merchant_name or "", description or ""])).upper()
    matches: list[dict[str, object]] = []
    idx = 0
    for category_name, keywords in rules.items():
        for keyword in keywords:
            if not keyword:
                continue
            if keyword in text:
                matches.append({
                    "category_name": category_name,
                    "keyword": keyword,
                    "index": idx,
                })
            idx += 1
    return matches


# ---------------------------------------------------------------------
# Alias table helpers (Phase 18).
# ---------------------------------------------------------------------
def _build_user_alias_lookup(
    db: Session,
    user_id: int,
    alias_keys: list[str],
) -> dict[str, int]:
    """Bulk SELECT user-aliases by canonical alias_key.

    Returns ``{alias_key: category_id}`` for hits. Single round-trip:
    the categorizer builds ONE ``IN (...)`` SELECT for the whole
    batch instead of N point lookups. Cache lifetime: ONE
    ``categorize_transactions`` call.

    Deduplicates the input list before the SELECT so a 500-row
    batch with 300 duplicate merchant texts generates 200 SELECT
    rows, not 500.
    """
    if not alias_keys or user_id is None:
        return {}
    unique_keys = set(k for k in alias_keys if k)
    if not unique_keys:
        return {}
    rows = (
        db.query(MerchantAlias)
        .filter(
            MerchantAlias.user_id == user_id,
            MerchantAlias.alias_key.in_(unique_keys),
        )
        .all()
    )
    return {row.alias_key: row.category_id for row in rows}


def _bump_alias_use_count(
    db: Session,
    user_id: int,
    alias_key: str,
) -> None:
    """Bump ``use_count`` + ``last_used_at`` on a Pass-1 alias hit so
    the lightest possible telemetry is maintained. Stays inside the
    same ``categorize_transactions`` call's flush window.

    Does NOT commit — the caller (the categorizer's flush at the end
    of the loop) does that, so the bumps ride along with the category
    ``category_id`` writes in a single round-trip.
    """
    if not alias_key:
        return
    row = (
        db.query(MerchantAlias)
        .filter(
            MerchantAlias.user_id == user_id,
            MerchantAlias.alias_key == alias_key,
        )
        .first()
    )
    if row is None:
        return
    row.use_count = (row.use_count or 0) + 1
    row.last_used_at = datetime.now(timezone.utc)


def _upsert_alias(
    db: Session,
    user_id: int,
    category_id: int,
    alias_key: str,
    source_text: str,
) -> None:
    """INSERT-if-absent, +1 ``use_count`` if present.

    Idempotent under concurrent calls thanks to the per-user
    ``UNIQUE(user_id, alias_key)`` constraint enforced by the
    ``merchant_aliases`` table. If two concurrent bulk calls both
    try to INSERT the same key, the second one raises a unique
    constraint violation; the categorizer's flush is in a try/except
    that re-runs the SELECT-then-INCREMENT path on conflict (see
    categorizer.py's call site docstring for the exact contract).

    Source text is the RAW (non-normalized) merchant text. Stored
    untouched so a future debug console can render the "category
    assigned because we saw ... vendor text" lineage.
    """
    if not alias_key or user_id is None or category_id is None:
        return
    row = (
        db.query(MerchantAlias)
        .filter(
            MerchantAlias.user_id == user_id,
            MerchantAlias.alias_key == alias_key,
        )
        .first()
    )
    if row is not None:
        # Same category already — bump use_count. A different category
        # would mean the user's habit changed OR the heuristic
        # resolution changed; the upsert treats it as an update
        # (latest-write-wins) so the alias reflects the most recent
        # canonical categorisation, which is what the user sees on
        # the activity page.
        row.category_id = category_id
        row.use_count = (row.use_count or 0) + 1
        row.last_used_at = datetime.now(timezone.utc)
    else:
        db.add(
            MerchantAlias(
                user_id=user_id,
                category_id=category_id,
                alias_key=alias_key,
                source_text=source_text,
                use_count=1,
                last_used_at=datetime.now(timezone.utc),
            )
        )
        # Flush immediately so subsequent queries in the SAME
        # ``categorize_transactions`` call see this row. Without the
        # explicit flush, multiple transactions with the SAME merchant
        # text inside one batch (e.g. 5 identical "AMAZON.COM*MK..." +
        # an OCR-noisy sibling) cause the second ``db.query().first()``
        # to return ``None`` (the just-added row is still in the
        # un-flushed identity map under autoflush=False), then the
        # ``db.add(...)`` below maps the second instance over the
        # first in the session; the eventual ``db.flush()`` at end of
        # the loop fires BOTH inserts and the second one
        # IntegrityErrors on the ``UNIQUE(user_id, alias_key)``
        # constraint. The categorizer's caller would 500 on that
        # commit.
        db.flush()


# ---------------------------------------------------------------------
# Fuzzy-match helper (Phase 18 + Phase 24).
# ---------------------------------------------------------------------
def _fuzzy_match_merchant_text(
    merchant_name: Optional[str],
    description: Optional[str],
    lookup: dict[str, Category],
    flat_fuzzy_keywords: Optional[list[tuple[str, str]]] = None,
) -> Optional[Category]:
    """thefuzz Pass 3 — return the Category for the best-scoring
    keyword match above ``_FUZZY_SCORE_CUTOFF``, or ``None`` on miss.

    Concatenates merchant + description (same as substring Pass 2)
    so a fuzzy keyword match could come from either side. Phase 24 —
    ``flat_fuzzy_keywords`` defaults to ``_DEFAULT_FLAT_FUZZY_KEYWORDS``
    for Phase-18-era callers; the runtime categoriser
    (:func:`categorize_transactions`) ALWAYS passes the per-batch
    snapshot from :func:`build_merchant_rules` so user-added
    keywords at any priority land on the next bulk run.

    Returns ``None`` (NOT the ``Other`` fallback) so the route decides
    what to do with a fuzzy miss.
    """
    effective_keywords = (
        flat_fuzzy_keywords
        if flat_fuzzy_keywords is not None
        else _DEFAULT_FLAT_FUZZY_KEYWORDS
    )
    if not effective_keywords:
        return None

    text = " ".join(
        filter(None, [merchant_name or "", description or ""])
    ).upper()
    if not text:
        return None

    best = fuzzyprocess.extractOne(
        text,
        [kw for kw, _cat in effective_keywords],
        score_cutoff=_FUZZY_SCORE_CUTOFF,
    )
    if best is None:
        return None

    matched_keyword, _score = best
    # Lookup the category for the matched keyword. Single tuple-scan
    # over the flat list — should average ~100 iterations in the
    # worst case. Future perf optimization: build a parallel
    # ``{keyword: category_name}`` dict at module load. Left as-is
    # until the test suite flags this as hot.
    for flat_kw, flat_cat_name in effective_keywords:
        if flat_kw == matched_keyword:
            return lookup.get(flat_cat_name)
    return None


# ---------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------
def categorize_transactions(
    db: Session,
    transactions: list[Transaction],
    *,
    allow_other: bool = True,
) -> tuple[int, int, list[dict[str, object]]]:
    """Bulk-categorize the given transactions in-place. Returns
    ``(categorized_count, skipped_count, conflicts)``.

    **Phase 18 + Phase 24 + Phase 39 — three-pass flow:**

    1. **Pass 1 — alias lookup**: bulk SELECT user-scoped
       ``merchant_aliases`` keyed by canonical alias text. A hit
       short-circuits the rest. ``use_count`` bumped for telemetry.
    2. **Pass 2 — substring rules** (Phase 24 — DB-backed): the
       live ``merchant_rules`` table. ONE per-batch SELECT via
       :func:`build_merchant_rules` supplies ``rules_dict`` (per-
       category keyword list) and ``flat_fuzzy_keywords`` (Pass 3
       candidates). On a successful match, UPSERT into
       ``merchant_aliases`` so the next import of the same merchant
       text hits Pass 1.
    3. **Pass 3 — thefuzz fuzzy match** (Phase 18 + 24): the same
       per-batch SELECT supplies ``flat_fuzzy_keywords`` with
       score_cutoff=85. Transfer / Income / Other excluded from the
       candidate list. Fuzzy hits do NOT write new aliases — typos
       aren't reliable teachers.

    **Phase 39 — conflict tracking**: For transactions that match
    multiple substring rules, ALL matches are collected in the
    ``conflicts`` return value so the FE can surface "this txn
    matched X and Y — rule X won because it's checked first".

    Side effects:

    - Writes ``category_id`` on each matched transaction row.
    - Flushes at the END so the route can commit in one round-trip.
    - Writes/bumps ``merchant_aliases`` rows for Pass 1 hits
      (``use_count++``) and Pass 2 success (``upsert``).

    ``allow_other``: when True, the matching ``"Other"`` rule falls
    back to assigning the ``"Other"`` category id (the user-friendly
    default). When False, rows that only match "Other" stay
    uncategorized — useful for tests that want to count the strict
    heuristic match rate.

    **User-id resolution** for alias lookups: derived from the first
    transaction's ``account.user_id``. When that lookup is unavailable
    (test fixtures, history rows without an account), the alias layer
    is bypassed and ``categorize_transactions`` falls back to the
    legacy two-pass behaviour. This keeps the function
    backward-compatible — legacy test code that constructs
    Transaction rows without an account still works.

    Returns ``(categorized, skipped, conflicts)``. ``conflicts`` is a
    list of dicts, each with keys ``transaction_id``, ``description``,
    ``matches`` (the list from :func:`find_all_matching_rules`), and
    ``winner`` (the category that won).
    """
    if not transactions:
        return (0, 0, [])

    lookup = build_category_lookup(db)

    # Phase 24 — fetch DB rules ONCE per batch. Two structures: the
    # per-category dict for Pass 2 (cheap substring scan), the flat
    # tuple list for Pass 3 (thefuzz ranking). Both come from the
    # same SELECT, so they're consistent within this bulk run.
    rules_dict, flat_fuzzy_keywords = build_merchant_rules(db)

    # Derive user_id from first txn's account — falls back to None if
    # the row has no eagerly-loaded account (rare; legacy txns). When
    # user_id is None, alias features degrade to the legacy two-pass
    # behaviour so legacy test fixtures keep working.
    user_id: Optional[int] = None
    first_txn = transactions[0]
    if first_txn.account is not None:
        acct_user_id = getattr(first_txn.account, "user_id", None)
        if acct_user_id is not None:
            user_id = int(acct_user_id)

    # Pre-fetch alias map if user_id resolved. ONE SELECT round-trip
    # for the whole batch — the categorizer does NOT do per-row
    # alias SELECTs.
    alias_keys_for_batch: list[str] = [
        normalize_alias_key(t.merchant_name, t.description)
        for t in transactions
    ]
    alias_map: dict[str, int] = (
        _build_user_alias_lookup(db, user_id, alias_keys_for_batch)
        if user_id is not None
        else {}
    )

    categorized = 0
    skipped = 0
    conflicts: list[dict[str, object]] = []

    for txn, txn_alias_key in zip(transactions, alias_keys_for_batch):
        matched_category: Optional[Category] = None
        matched_via: Optional[str] = None  # "alias" | "substring" | "fuzzy"

        # -------- Pass 1: alias lookup --------
        cached_category_id = alias_map.get(txn_alias_key)
        if cached_category_id is not None and txn_alias_key:
            id_to_cat = {c.id: c for c in lookup.values()}
            matched_category = id_to_cat.get(cached_category_id)
            if matched_category is not None:
                matched_via = "alias"
                _bump_alias_use_count(db, user_id, txn_alias_key)

        # -------- Pass 2: substring rules --------
        if matched_category is None:
            substring_match = suggest_category_for(
                txn.merchant_name,
                txn.description,
                lookup,
                rules_dict,
            )
            if substring_match is not None:
                # Phase 39 — check for multi-match conflicts BEFORE
                # applying the match, so the user can see which rules
                # competed. Only check if this txn is currently
                # uncategorized (don't bother for already-tagged rows).
                if txn.category_id is None:
                    all_matches = find_all_matching_rules(
                        txn.merchant_name, txn.description, rules_dict,
                    )
                    if len(all_matches) > 1:
                        conflicts.append({
                            "transaction_id": txn.id,
                            "description": (txn.description or "")[:120],
                            "amount": txn.amount,
                            "matches": all_matches,
                            "winner": substring_match.name,
                        })
                matched_category = substring_match
                matched_via = "substring"
                if user_id is not None and txn_alias_key:
                    _upsert_alias(
                        db,
                        user_id=user_id,
                        category_id=substring_match.id,
                        alias_key=txn_alias_key,
                        source_text=txn.description or txn.merchant_name or "",
                    )

        # -------- Pass 3: fuzzy match --------
        if matched_category is None:
            fuzzy_match = _fuzzy_match_merchant_text(
                txn.merchant_name,
                txn.description,
                lookup,
                flat_fuzzy_keywords,  # Phase 24 — per-batch snapshot
            )
            if fuzzy_match is not None:
                matched_category = fuzzy_match
                matched_via = "fuzzy"
                # NO alias write on fuzzy hit — typos aren't reliable
                # teachers. The next import of the same text will
                # pass through the same fuzzy layer for the same
                # resolution; the substring Pass 2 still gates the
                # dangerous categorical cases.

        # -------- Phase 52+ guard: credit-card payments are NOT income --------
        # A positive amount on a credit-card/loan/mortgage account is a
        # payment/credit TO the card (reducing balance), NOT income.
        # The categorizer's seed rules don't match "ONLINE PAYMENT" to
        # "Income", but alias learning (Pass 1) can incorrectly learn
        # this mapping if a previous transaction was manually tagged.
        # This guard prevents the alias from silently re-tagging future
        # credit-card payments as income.
        if matched_category is not None and matched_category.name == "Income":
            if txn.amount > 0:
                _acct = getattr(txn, 'account', None)
                if _acct is not None:
                    _at = getattr(_acct, 'account_type', None)
                    if _at is not None and _at.lower() in _CREDIT_ACCOUNT_TYPES:
                        # Positive on credit = payment, NOT income. Skip.
                        skipped += 1
                        continue

        # -------- Apply --------
        if matched_category is None:
            skipped += 1
            continue
        if not allow_other and matched_category.name == "Other":
            skipped += 1
            continue
        if txn.category_id == matched_category.id:
            # Already correct — don't churn the column for no reason.
            skipped += 1
            continue
        txn.category_id = matched_category.id
        categorized += 1

    if categorized > 0:
        db.flush()
    return (categorized, skipped, conflicts)


# ---------------------------------------------------------------------
# Manual-tag alias learning (Phase 18 extension).
# ---------------------------------------------------------------------
# Called from ``app.routes.transactions.update_transaction`` when the
# user explicitly assigns a category to a row via the activity page's
# inline ``<select>``. Mirrors the thinker's recommendation: the
# user's manual category decisions are reliable teachers (vs a
# fuzzy-hit auto-learner) because the user actively chose the label.
#
# The mitigation against over-fitting lives in the alias_key
# normaliser: dynamic-IDs in raw descriptions (``DOORDASH #1234``
# vs ``DOORDASH #5678``) produce distinct alias_keys so a
# one-off mis-classification doesn't leak across other instances
# of the same merchant. Pass 2 substring rules still match the bare
# merchant name to the right category as the safety net.
def learn_alias_for_category(
    db: Session,
    user_id: int,
    txn: Transaction,
    category_id: int,
) -> None:
    """Public helper for the route layer to call after a manual
    ``PUT /api/transactions/{id}`` writes a ``category_id``. UPSERTs
    the alias so the user's explicit choice reinforces the heuristic
    for the same raw merchant text on future imports.

    Idempotent: safe to call multiple times for the same row. Latest
    ``category_id`` wins (handles the rare case where the user
    corrects their tag from one category to another — the new tag
    replaces the stored alias category_id).

    Returns ``None``. Alias bookkeeping is a side-effect; the caller's
    commit handles persistence.
    """
    if user_id is None or category_id is None or txn is None:
        return
    alias_key = normalize_alias_key(txn.merchant_name, txn.description)
    if not alias_key:
        return
    _upsert_alias(
        db,
        user_id=user_id,
        category_id=category_id,
        alias_key=alias_key,
        source_text=txn.description or txn.merchant_name or "",
    )


# ---------------------------------------------------------------------
# Phase 29 — duplicate detection (Settings → "Clean up duplicates").
# ---------------------------------------------------------------------
# Design: combine a deterministic substring scan (L1) with an optional
# LLM semantic pass (L2, see services/llm_categorizer.py). L1 is the
# primary signal because it's reproducible; L2 is the LLM-assisted
# suggestion for keywords that substring cannot relate ("WALMART" vs
# "WAL-MART", "UBER TRIP" vs "UBER *", etc.).
#
# The Settings UI calls these from the wizard modal; the same
# functions are also reachable from the BE route layer so tests
# can exercise them without spinning up a TestClient.
#
# Soft-delete contract: a "merged" rule is ``is_archived=True`` (NOT
# a hard delete) so the boot-time seed never resurrects it on the
# next cold start. The ``seed_default_merchant_rules`` SKIP-on-archived
# check is the canonical way to keep user intent across restarts.
def find_substring_duplicates(
    db: Session,
) -> list[dict[str, object]]:
    """L1 — return every rule pair where one keyword is a strict
    substring of the other within the SAME category.

    The returned ``canonical`` (the rule to KEEP) is the SHORTER
    keyword (more general — it absorbs any transaction the longer
    rule would have caught). Tie-break: lower priority (older
    / seed-canonical). This matches the thinker's design note from
    Phase 29: "the shorter, more general rule should be retained
    because of how pure substring matching works" — ``STARBUCKS``
    matches both ``STARBUCKS`` and ``STARBUCKS #1234`` so the
    longer one is dead-weight.

    Trailing-space guard: a rule that PRESERVES a trailing space
    (``"TAXI "``) is a deliberate word-boundary marker that
    prevents false positives (``"TAXIDERMY"``). If the shorter
    rule has a trailing space but the longer one does NOT, do
    NOT flag the pair — the longer rule's author dropped the
    boundary intentionally.

    Output shape (one entry per ``(canonical, candidate)`` pair;
    the FE's wizard consolidates multi-candidate groups):

      [
        {
          "canonical_id": 42,
          "canonical_keyword": "STARBUCKS",
          "candidate_id": 43,
          "candidate_keyword": "STARBUCKS COFFEE",
          "method": "substring",
          "confidence": 1.0,
          "rationale": "STARBUCKS is a substring of STARBUCKS COFFEE",
        },
        ...
      ]
    """
    rows = (
        db.query(MerchantRule)
        .filter(MerchantRule.is_archived.is_(False))
        .order_by(
            MerchantRule.category_id.asc(),
            MerchantRule.priority.asc(),
        )
        .all()
    )
    # Group by category so cross-category pairs (e.g. "AMAZON"
    # Shopping vs "AMAZON" Groceries) are NOT flagged. Cross-category
    # dedup is a different problem (the user is intentionally
    # scoping a keyword to multiple categories) and out of scope
    # for this pass.
    by_category: dict[int, list[MerchantRule]] = {}
    for r in rows:
        by_category.setdefault(r.category_id, []).append(r)

    out: list[dict[str, object]] = []
    for cat_id, cat_rules in by_category.items():
        # Sort ASC by (length, priority) so the FIRST matching rule
        # in the iteration IS the canonical (shortest, then lowest
        # priority tie-break). This keeps the ``out`` list in
        # deterministic order so the FE's wizard shows suggestions
        # in a stable sequence.
        cat_rules_sorted = sorted(
            cat_rules,
            key=lambda r: (len(r.keyword or ""), r.priority or 0),
        )
        for i, canonical in enumerate(cat_rules_sorted):
            can_kw = (canonical.keyword or "")
            if not can_kw:
                continue
            for candidate in cat_rules_sorted[i + 1 :]:
                cand_kw = (candidate.keyword or "")
                if not cand_kw or cand_kw == can_kw:
                    continue
                if can_kw not in cand_kw:
                    continue
                # Trailing-space guard: do NOT flag a pair where the
                # shorter rule preserves a boundary the longer
                # dropped. Example: "TAXI " vs "TAXI UBER" is a valid
                # dup (the longer keeps the boundary); "TAXI" vs
                # "TAXI " is NOT (the longer preserved the
                # boundary the shorter dropped).
                if can_kw.endswith(" ") and not cand_kw.endswith(" "):
                    continue
                out.append(
                    {
                        "canonical_id": canonical.id,
                        "canonical_keyword": can_kw,
                        "candidate_id": candidate.id,
                        "candidate_keyword": cand_kw,
                        "method": "substring",
                        "confidence": 1.0,
                        "rationale": (
                            f"{can_kw!r} is a substring of "
                            f"{cand_kw!r} — the shorter rule already "
                            f"matches every transaction the longer one "
                            f"would match"
                        ),
                    }
                )
    return out


def consolidate_duplicate_groups(
    pairs: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Group multiple (canonical, candidate) pairs that share the
    same ``canonical_id`` into a single dedup group the FE can
    render as one row in the wizard.

    Input is the L1 (substring) output from
    :func:`find_substring_duplicates` OR the L2 (LLM) output from
    :func:`app.services.llm_categorizer.find_semantic_duplicates_async`.
    Both shapes use the ``canonical_id`` / ``candidate_id`` keys.

    Output shape:

      [
        {
          "canonical": {"id": 42, "keyword": "STARBUCKS"},
          "candidates": [
            {"id": 43, "keyword": "STARBUCKS COFFEE", "method": "substring",
             "confidence": 1.0, "rationale": "..."},
            {"id": 44, "keyword": "STARBUCKS POS", "method": "llm",
             "confidence": 0.92, "rationale": "..."},
          ],
        },
        ...
      ]

    Multiple methods on the same candidate (substring + llm both
    flagging it) are deduped — the L1 (substring) rationale wins
    because it's deterministic, but the candidate's
    ``confidence`` is the MAX across signals so a 1.0 substring
    hit overrides a 0.7 LLM hit on the same pair.
    """
    by_canonical: dict[int, dict[str, object]] = {}
    for pair in pairs:
        canon_id = int(pair["canonical_id"])  # type: ignore[arg-type]
        cand_id = int(pair["candidate_id"])  # type: ignore[arg-type]
        bucket = by_canonical.setdefault(
            canon_id,
            {
                "canonical": {
                    "id": canon_id,
                    "keyword": pair.get("canonical_keyword", ""),
                },
                "candidates": {},
            },
        )
        cand_bucket = bucket["candidates"]  # type: ignore[index]
        existing = cand_bucket.get(cand_id)  # type: ignore[arg-type]
        new_conf = float(pair.get("confidence", 0.0))  # type: ignore[arg-type]
        new_method = str(pair.get("method", ""))  # type: ignore[arg-type]
        if existing is None or new_conf >= float(
            existing.get("confidence", 0.0)
        ):
            cand_bucket[cand_id] = {
                "id": cand_id,
                "keyword": pair.get("candidate_keyword", ""),
                "method": new_method,
                "confidence": new_conf,
                "rationale": pair.get("rationale", ""),
            }
    # Flatten the per-candidate dict to a list, ordered by id ASC
    # for deterministic FE rendering.
    out: list[dict[str, object]] = []
    for canon_id in sorted(by_canonical.keys()):
        bucket = by_canonical[canon_id]
        cands = sorted(
            bucket["candidates"].values(),  # type: ignore[union-attr]
            key=lambda c: int(c["id"]),  # type: ignore[arg-type]
        )
        out.append(
            {
                "canonical": bucket["canonical"],
                "candidates": cands,
            }
        )
    return out


# ---------------------------------------------------------------------
# Phase 24 back-compat layer.
# ---------------------------------------------------------------------
# Pre-Phase-24 the categorizer exposed ``_FLAT_FUZZY_KEYWORDS`` as a
# module-level cache. Phase 24 renamed it to
# ``_DEFAULT_FLAT_FUZZY_KEYWORDS`` to signal that it now reflects
# the bootstrap dict (not the runtime DB rowset). Tests / consumers
# that still import the old symbol continue working via this
# re-export alias. A future ``Phase 24.1+`` that fully removes the
# module-level cache can drop the alias along with the dict.
_FLAT_FUZZY_KEYWORDS = _DEFAULT_FLAT_FUZZY_KEYWORDS
