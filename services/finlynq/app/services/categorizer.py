"""Phase-F4 lift — categorizer service for Finlynq's canonical store.

Verbatim lift of ``services/rules-service/app/services/categorizer.py``
WITHOUT the polymorphic ``Transaction`` import — Phase-F4 only needs
``Category`` for the ``MERCHANT_RULES`` lookup table. Phase-F5 lifts
the ``Transaction`` ORM model and the categorize-on-DB-rows path.

The F4 ``POST /categorize`` endpoint runs the heuristic against plain
dict rows from the FE payload (no DB writes). The DB-write path lives
on rules-service's ``POST /api/transactions/categorize`` forwarder,
which queries the local user's uncategorized transactions, projects
them to {merchant_name, description} dicts, and POSTs the bulk to
Finlynq. Categorization persists back on rules-service via the F4
return shape.

Two pieces here:

1. ``seed_default_categories(db)`` — idempotent INSERT-IF-NOT-EXISTS for
   the 12 categories every personal-finance app needs (Food, Groceries,
   Gas, Transit, Entertainment, Shopping, Bills, Health, Travel, Income,
   Transfer, Other). Runs on FastAPI startup so a fresh DB ends up with
   the seeds without an ADMIN-INIT migration.

2. ``count_categorize_matches(transactions, lookup)`` — pure-dict heuristic.
   For the F4 endpoint that accepts plain dict rows from the FE;
   returns ``(categorized_count, skipped_count)`` — honest counts,
   no DB writes (the FE sends already-categorized rows interleaved
   and we simply skip them).

Phase-F4 round-up rename (post code-reviewer):
- Pre-F4 had a polymorphic path that took EITHER ORM rows OR dicts
  and silently returned inflated counts for the dict branch. Today
  we split into two functions:
    * ``categorize_transactions(db, transactions)`` — ORM rows (Phase-F5+).
    * ``count_categorize_matches(transactions, lookup)`` — dict rows.
  Both are honest about their work; the F4 endpoint uses the latter.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Category

LOG = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------
# Default category seeds. Every key MUST exist as a Category row after
# seed_default_categories() runs; the categorizer substring-matches the
# merchant + description against each key's keyword list.
# ---------------------------------------------------------------------
DEFAULT_CATEGORIES: list[dict[str, Optional[str]]] = [
    # Subscriptions / recurring income / movement flows first so the
    # rule lookup short-circuits on "PAYROLL DEPOSIT" before falling
    # through to the Income keyword scan.
    {"name": "Income", "description": "Payroll, deposits, refunds", "icon": "💰", "color": "#16a34a"},
    {"name": "Transfer", "description": "Internal movements between accounts", "icon": "🔁", "color": "#64748b"},
    {"name": "Food & Dining", "description": "Restaurants, takeout, delivery", "icon": "🍽️", "color": "#f97316"},
    {"name": "Groceries", "description": "Supermarkets and grocery stores", "icon": "🛒", "color": "#10b981"},
    {"name": "Transportation", "description": "Gas, transit, rideshare, parking", "icon": "🚗", "color": "#0ea5e9"},
    {"name": "Shopping", "description": "General retail and online purchases", "icon": "🛍️", "color": "#a855f7"},
    {"name": "Entertainment", "description": "Movies, streaming, concerts, hobbies", "icon": "🎬", "color": "#ec4899"},
    {"name": "Bills & Utilities", "description": "Rent, electricity, internet, phone", "icon": "💡", "color": "#facc15"},
    {"name": "Health", "description": "Medical, pharmacy, fitness", "icon": "🏥", "color": "#ef4444"},
    {"name": "Travel", "description": "Airlines, hotels, car rental", "icon": "✈️", "color": "#3b82f6"},
    {"name": "Education", "description": "Tuition, books, courses", "icon": "📚", "color": "#6366f1"},
    {"name": "Other", "description": "Unmatched transactions", "icon": "❓", "color": "#94a3b8"},
]

# Order matters: longer / more specific keys first so "STARBUCKS COFFEE"
# matches "Starbucks" before the generic "Coffee" rule short-circuits it.
# Each list is matched case-insensitively as a substring against the
# concatenated ``(merchant_name + " " + description)`` text.
MERCHANT_RULES: dict[str, list[str]] = {
    "Income": [
        "PAYROLL", "DIRECT DEPOSIT", "SALARY", "DEPOSIT",
        "REFUND", "REIMBURSEMENT", "TAX REFUND",
    ],
    "Transfer": [
        "TRANSFER", "ZELLE", "VENMO", "CASHAPP", "WIRE",
        "ACH ", "ATM ", "MOBILE TRANSFER", "INTERNAL TRANSFER",
    ],
    "Food & Dining": [
        "STARBUCKS", "MCDONALD", "CHIPOTLE", "DOORDASH", "UBER EATS",
        "GRUBHUB", "RESTAURANT", "CAFE", "COFFEE", "BISTRO", "DINER",
        "PIZZA", "SUBWAY", "TACO", "SUSHI", "PANERA", "DUNKIN",
    ],
    "Groceries": [
        "WHOLE FOODS", "TRADER JOE", "SAFEWAY", "KROGER", "PUBLIX",
        "COSTCO", "WAL-MART", "WALMART", "ALDI", "GROCERY",
        "SUPERMARKET", "FOOD LION", "HEB", "SPROUTS", "ALBERTSONS",
    ],
    "Transportation": [
        "SHELL", "CHEVRON", "EXXON", "BP ", "MOBIL", "VALERO",
        "GAS STATION", "UBER", "LYFT", "TAXI", "PARKING",
        "METRO", "TRANSIT", "MTA", "BART", "CTA ", "AMTRAK",
    ],
    "Shopping": [
        "AMAZON", "AMZN", "TARGET", "EBAY", "ETSY", "BEST BUY",
        "IKEA", "MACY", "NORDSTROM", "NIKE", "ADIDAS", "APPLE STORE",
        "STORE", "RETAIL", "MALL", "TJ MAXX",
    ],
    "Entertainment": [
        "NETFLIX", "HULU", "DISNEY+", "SPOTIFY", "AMAZON PRIME",
        "HBO", "MOVIE", "CINEMA", "AMC", "REGAL", "CONCERT",
        "STEAM", "PLAYSTATION", "XBOX", "NINTENDO", "TWITCH",
    ],
    "Bills & Utilities": [
        "VERIZON", "AT&T", "T-MOBILE", "COMCAST", "XFINITY",
        "ELECTRIC", "GAS COMPANY", "WATER", "SEWER",
        "PG&E", "CON EDISON", "RENT", "LEASE PAYMENT",
        "INTERNET", "PHONE BILL",
    ],
    "Health": [
        "CVS", "WALGREENS", "RITE AID", "PHARMACY", "DOCTOR",
        "HOSPITAL", "MEDICAL", "DENTAL", "VISION", "EYE CARE",
        "FITNESS", "GYM", "PLANET FITNESS", "EQUINOX", "PELOTON",
    ],
    "Travel": [
        "UNITED AIRLINES", "DELTA", "AMERICAN AIRLINES", "SOUTHWEST",
        "AIRLINE", "AIRBNB", "HOTEL", "MARRIOTT", "HILTON", "HYATT",
        "CAR RENTAL", "HERTZ", "AVIS", "ENTERPRISE", "EXPEDIA",
        "BOOKING.COM",
    ],
    "Education": [
        "TUITION", "UNIVERSITY", "COLLEGE", "SCHOOL",
        "UDEMY", "COURSERA", "EDX", "TEXTBOOK", "BOOKSTORE",
    ],
    # No keywords for "Other" — it's the catch-all. Empty list is
    # intentional; users don't pay for a fallback to themselves.
    "Other": [],
}


def seed_default_categories(db: Session) -> int:
    """Idempotently insert the default categories if not present.

    Returns the number of NEW categories inserted (0 on a re-run).
    Used both by the FastAPI startup hook and the test fixtures so
    a hermetic DB ends up populated.
    """
    inserted = 0
    for c in DEFAULT_CATEGORIES:
        existing = db.query(Category).filter(Category.name == c["name"]).first()
        if existing is not None:
            continue
        db.add(
            Category(
                name=c["name"],
                description=c.get("description"),
                icon=c.get("icon"),
                color=c.get("color"),
            )
        )
        inserted += 1
    if inserted > 0:
        db.commit()
        LOG.info("Seeded %d default categories", inserted)
    return inserted


def _lookup_category(db: Session, name: str) -> Optional[Category]:
    """Cache-free, single-row get by name."""
    return db.query(Category).filter(Category.name == name).first()


def build_category_lookup(db: Session) -> dict[str, Category]:
    """Return ``{category_name: Category row}`` for names present in
    ``MERCHANT_RULES``."""
    wanted = set(MERCHANT_RULES.keys())
    rows = db.query(Category).filter(Category.name.in_(wanted)).all()
    return {row.name: row for row in rows}


def suggest_category_for(
    merchant_name: Optional[str],
    description: Optional[str],
    lookup: dict[str, Category],
) -> Optional[Category]:
    """Pick the best-fit category for a transaction's text, or ``None``.

    Pure function — used by both the F4 dict-counting path AND the
    future F5 ORM-write path. The lookup dict is built once per
    call-site via :func:`build_category_lookup`.
    """
    text = " ".join(filter(None, [merchant_name or "", description or ""])).upper()

    for category_name, keywords in MERCHANT_RULES.items():
        for keyword in keywords:
            if not keyword:
                continue
            if keyword in text:
                return lookup.get(category_name)
    return None


def count_categorize_matches(
    transactions: list[dict],
    lookup: dict[str, Category],
    *,
    allow_other: bool = True,
) -> tuple[int, int]:
    """Phase-F4 forwarder-friendly helper: returns
    ``(categorized_count, skipped_count)`` for a list of dict rows
    WITHOUT persisting anything.

    Use this from the F4 ``POST /categorize`` endpoint and the
    cross-service forwarder at rules-service's
    ``POST /api/transactions/categorize`` — both callers project
    their source rows to ``{merchant_name, description}`` dicts and
    defer the actual DB write to the rules-service side.

    ``allow_other``: when True, the matching ``"Other"`` rule falls
    under categorized. When False, rows that only match "Other" stay
    under skipped.
    """
    if not transactions:
        return (0, 0)
    categorized = 0
    skipped = 0
    for txn in transactions:
        merchant = txn.get("merchant_name")
        description = txn.get("description")
        match = suggest_category_for(merchant, description, lookup)
        if match is None:
            skipped += 1
            continue
        if not allow_other and match.name == "Other":
            skipped += 1
            continue
        categorized += 1
    return (categorized, skipped)
