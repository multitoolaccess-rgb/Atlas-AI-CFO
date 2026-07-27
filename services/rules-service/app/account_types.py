"""Phase 52 — canonical account types and per-type financial classification rules.

This module is the single source of truth for account types. Every route,
schema, parser, and the FE dropdown must reference these values — never
hard-code a string like ``"credit_card"`` or ``"checking"`` inline.

Phase 52+ — ``classify_cashflow()`` is the PURE function that determines
financial effect + cashflow role from (amount, account_type, description).
It mirrors the TypeScript ``classifyCashflow()`` in ``ui/lib/api.ts`` so
the backend dashboard aggregation and frontend Activity page use the same
keyword patterns and classification rules.

== Usage ==

::

   from app.account_types import classify_cashflow

   result = classify_cashflow(amount=-450.0, account_type="credit_card",
                              description="ONLINE PAYMENT, THANK YOU")
   # result.effect = "transfer"
   # result.role = "transfer"
   # result.income_effect = 0.0
   # result.expense_effect = 0.0
"""

from typing import FrozenSet


# ------------------------------------------------------------------
# Canonical types (ordered for <select> dropdown rendering)
# ------------------------------------------------------------------
ACCOUNT_TYPES: list[tuple[str, str]] = [
    ("checking", "Checking"),
    ("savings", "Savings"),
    ("credit_card", "Credit Card"),
    ("debit_card", "Debit Card"),
    ("investment", "Investment"),
    ("loan", "Loan"),
    ("mortgage", "Mortgage"),
    ("hsa", "Health Savings Account"),
    ("529", "529 Education Plan"),
    ("401k", "401(k)"),
    ("ira", "IRA"),
    ("crypto", "Crypto"),
    ("other", "Other"),
]

# Set of all valid database values (for Pydantic validation + set lookups)
ACCOUNT_TYPE_VALUES: FrozenSet[str] = frozenset(v for v, _ in ACCOUNT_TYPES)

# Label lookup: db_value → human label
ACCOUNT_TYPE_LABELS: dict[str, str] = dict(ACCOUNT_TYPES)

# ------------------------------------------------------------------
# Legacy classification sets — KEPT for backward compat with callers
# that haven't migrated to ``classify_cashflow()`` yet.
# ------------------------------------------------------------------

INCOME_ACCOUNT_TYPES: FrozenSet[str] = frozenset(
    {"checking", "savings", "debit_card"}
)

EXPENSE_ACCOUNT_TYPES: FrozenSet[str] = frozenset(
    {"checking", "savings", "debit_card"}
)

CREDIT_ACCOUNT_TYPES: FrozenSet[str] = frozenset(
    {"credit_card", "loan", "mortgage"}
)

INVESTMENT_ACCOUNT_TYPES: FrozenSet[str] = frozenset(
    {"investment", "hsa", "529", "401k", "ira", "crypto"}
)


# ===================================================================
# Phase 52+ — classify_cashflow() and supporting types/patterns
# ===================================================================

class CashflowResult:
    """Immutable result of ``classify_cashflow()``.

    Mirrors the TypeScript ``CashflowClassification`` interface exactly
    so the frontend and backend can never silently drift apart.
    """
    __slots__ = (
        "effect", "role",
        "income_effect", "expense_effect", "transfer_effect",
        "needs_review", "review_reason",
    )

    def __init__(
        self,
        effect: str,
        role: str,
        income_effect: float,
        expense_effect: float,
        transfer_effect: float,
        needs_review: bool = False,
        review_reason: str | None = None,
    ):
        self.effect = effect
        self.role = role
        self.income_effect = income_effect
        self.expense_effect = expense_effect
        self.transfer_effect = transfer_effect
        self.needs_review = needs_review
        self.review_reason = review_reason

    def __repr__(self) -> str:
        return (
            f"CashflowResult(effect={self.effect!r}, role={self.role!r}, "
            f"income={self.income_effect}, expense={self.expense_effect}, "
            f"transfer={self.transfer_effect})"
        )


# ---- Keyword pattern lists (ordered by priority within each group) --------
# Word-boundary matching is done by padding the description with spaces
# and checking ``f" {pattern} " in f" {description} "`` — equivalent to
# the frontend's ``\bPATTERN\b`` regex.

# Bill-pay phrases — internal transfers, not income or expense.
_PAYMENT_PATTERNS = [
    "online payment", "mobile payment", "automatic payment",
    "electronic payment", "payment thank you", "payment received",
    "autopay", "scheduled payment", "bill pay", "payment from",
]

# Refund / return / reversal phrases — reduce expenses.
_REFUND_PATTERNS = [
    "refund", "return", "reversal", "cashback",
    "statement credit", "credit adjustment", "reward redemption",
]

# Income patterns — payroll, salary, direct deposit, dividends.
_INCOME_PATTERNS = [
    "payroll", "direct deposit", "salary",
    "dividend", "capital gain",
]

# Interest-earned patterns (savings interest, not credit card interest).
_INTEREST_EARNED_PATTERNS = [
    "interest earned", "interest paid", "interest credit",
    "dividend earned", "dividend paid", "dividend credit",
    "apy", "annual percentage yield",
]

# Fee / charge patterns.
_FEE_PATTERNS = [
    "monthly fee", "service fee", "maintenance fee", "annual fee",
    "late fee", "overdraft fee", "atm fee", "wire fee", "transaction fee",
    "fee", "charge", "network fee",
    "interest charge", "finance charge",
]

# Contribution patterns (401k, IRA, HSA, 529).
_CONTRIBUTION_PATTERNS = [
    "contribution", "contrib",
    "employee contrib", "employee deferral",
]

# Employer match patterns.
_MATCH_PATTERNS = [
    "employer match", "employer contrib", "company match", "company contrib",
    "match",
]

# Rollover patterns.
_ROLLOVER_PATTERNS = [
    "rollover", "direct rollover",
    "trustee-to-trustee", "trustee to trustee",
]

# Staking / crypto reward patterns.
_STAKING_PATTERNS = [
    "staking", "stake reward", "reward",
    "airdrop", "yield farm",
]

# Trade buy patterns.
_TRADE_BUY_PATTERNS = [
    "buy", "purchase", "bought", "you bought",
]

# Trade sell patterns.
_TRADE_SELL_PATTERNS = [
    "sell", "sold", "you sold",
]

# Escrow patterns (mortgage-specific).
_ESCROW_PATTERNS = [
    "escrow", "property tax",
    "hazard insurance", "pmi",
]

# Principal payment patterns.
_PRINCIPAL_PATTERNS = [
    "principal", "principal payment", "principal reduction",
]

# Internal transfer patterns.
_TRANSFER_PATTERNS = [
    "scheduled transfer", "online transfer", "automatic transfer",
    "recurring transfer", "internal transfer",
    "transfer from", "transfer to",
    "wire transfer", "wire out", "wire in",
    "ach transfer",
]

# Medical / healthcare spend patterns (HSA-specific).
_MEDICAL_PATTERNS = [
    "medical", "pharmacy", "hospital", "doctor", "dental",
    "vision", "optical", "clinic", "health",
    "copay", "co-pay", "deductible",
    "prescription", "rx",
]

# Distribution / withdrawal patterns (IRA, 401k).
_WITHDRAWAL_PATTERNS = [
    "distribution", "withdrawal", "disbursement",
    "rmd", "required minimum",
]


# ---- Helper functions ----

def _match_any(description: str, patterns: list[str]) -> bool:
    """Return True if *any* pattern in the list appears as a word-bounded
    substring in ``description`` (case-insensitive).

    Uses space-padding for word-boundary semantics: ``" payment "`` inside
    ``" online payment thank you "`` matches, but ``" repayment "`` does not
    match ``" payment "``.  Equivalent to the frontend's ``\\bPATTERN\\b`` regex.
    """
    d = f" {description.lower()} "
    return any(f" {p} " in d for p in patterns)


def _result(
    abs_amt: float,
    effect: str,
    role: str,
    needs_review: bool = False,
    review_reason: str | None = None,
) -> CashflowResult:
    """Build a ``CashflowResult`` with consistent numerical-effect
    computation from an effect name.
    """
    income = 0.0
    expense = 0.0
    transfer = 0.0

    if effect in ("income", "interest"):
        income = abs_amt
    elif effect in ("expense", "fee"):
        expense = abs_amt
    elif effect == "expense_reversal":
        expense = -abs_amt
    elif effect == "income_reversal":
        income = -abs_amt
    else:
        # transfer, contribution, withdrawal, investment_buy/sell,
        # principal_payment, ignored, needs_review
        transfer = abs_amt

    return CashflowResult(
        effect=effect,
        role=role,
        income_effect=income,
        expense_effect=expense,
        transfer_effect=transfer,
        needs_review=needs_review,
        review_reason=review_reason,
    )


# ===================================================================
# classify_cashflow() — THE canonical classification function
# ===================================================================

def classify_cashflow(
    amount: float,
    account_type: str | None,
    description: str | None,
) -> CashflowResult:
    """Classify a transaction into its *FinancialEffect* + *CashflowRole*.

    This is a **pure function** — no DB reads, no side effects.  It mirrors
    the TypeScript ``classifyCashflow()`` in ``ui/lib/api.ts`` exactly, so
    the backend dashboard aggregation and frontend Activity page use the
    same keyword patterns and classification rules.

    Each account-type branch applies description-based keyword detection
    in priority order — the FIRST matching pattern wins.

    Args:
        amount: Raw signed transaction amount.
        account_type: The account's ``account_type`` string (e.g. ``"checking"``).
        description: The transaction description / merchant name text.

    Returns:
        A ``CashflowResult`` with deterministic ``effect``, ``role``, and
        numerical ``income_effect`` / ``expense_effect`` / ``transfer_effect``.
    """
    # Normalize legacy account type strings ("Credit Card" → "credit_card")
    # so imports or old data created before the schema validator still classify.
    at = (account_type or "").strip().lower().replace(" ", "_")
    desc = (description or "").strip()
    abs_amt = abs(amount)
    is_pos = amount > 0
    is_neg = amount < 0

    # ---- CREDIT CARD ----
    if at == "credit_card":
        if _match_any(desc, _PAYMENT_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if _match_any(desc, _REFUND_PATTERNS):
            return _result(abs_amt, "expense_reversal", "earn")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        return _result(abs_amt, "expense", "spend")

    # ---- LOAN ----
    if at == "loan":
        if _match_any(desc, _PRINCIPAL_PATTERNS):
            return _result(abs_amt, "principal_payment", "debt")
        if _match_any(desc, _FEE_PATTERNS) or _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if _match_any(desc, _PAYMENT_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if is_pos:
            return _result(abs_amt, "transfer", "transfer")  # disbursement
        return _result(abs_amt, "principal_payment", "debt")

    # ---- MORTGAGE ----
    if at == "mortgage":
        if _match_any(desc, _ESCROW_PATTERNS):
            return _result(abs_amt, "transfer", "save")
        if _match_any(desc, _PRINCIPAL_PATTERNS):
            return _result(abs_amt, "principal_payment", "debt")
        if _match_any(desc, _FEE_PATTERNS) or _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if _match_any(desc, _PAYMENT_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if is_pos:
            return _result(abs_amt, "transfer", "transfer")
        return _result(abs_amt, "principal_payment", "debt")

    # ---- INVESTMENT ----
    if at == "investment":
        if _match_any(desc, _TRADE_BUY_PATTERNS):
            return _result(abs_amt, "investment_buy", "invest")
        if _match_any(desc, _TRADE_SELL_PATTERNS):
            return _result(abs_amt, "investment_sell", "invest")
        # Dividend detection — "DIVIDEND" or "DIV" as word boundaries
        d = f" {desc.lower()} "
        if " dividend " in d or " div " in d or _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "income", "earn")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        return _result(abs_amt, "transfer", "transfer")

    # ---- CRYPTO ----
    if at == "crypto":
        if _match_any(desc, _TRADE_BUY_PATTERNS):
            return _result(abs_amt, "investment_buy", "invest")
        if _match_any(desc, _TRADE_SELL_PATTERNS):
            return _result(abs_amt, "investment_sell", "invest")
        if _match_any(desc, _STAKING_PATTERNS):
            return _result(abs_amt, "income", "earn")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        return _result(abs_amt, "transfer", "transfer")

    # ---- 401(k) ----
    if at == "401k":
        if _match_any(desc, _ROLLOVER_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if _match_any(desc, _MATCH_PATTERNS):
            return _result(abs_amt, "contribution", "save")
        if _match_any(desc, _CONTRIBUTION_PATTERNS):
            return _result(abs_amt, "contribution", "save")
        if _match_any(desc, _TRADE_BUY_PATTERNS):
            return _result(abs_amt, "investment_buy", "invest")
        if _match_any(desc, _TRADE_SELL_PATTERNS):
            return _result(abs_amt, "investment_sell", "invest")
        d = f" {desc.lower()} "
        if " dividend " in d or " div " in d or _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "income", "earn")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if is_pos:
            return _result(abs_amt, "contribution", "save")
        return _result(abs_amt, "ignored", "invest")

    # ---- IRA ----
    if at == "ira":
        if _match_any(desc, _ROLLOVER_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if _match_any(desc, _CONTRIBUTION_PATTERNS):
            return _result(abs_amt, "contribution", "save")
        if _match_any(desc, _WITHDRAWAL_PATTERNS):
            return _result(abs_amt, "withdrawal", "transfer")
        if _match_any(desc, _TRADE_BUY_PATTERNS):
            return _result(abs_amt, "investment_buy", "invest")
        if _match_any(desc, _TRADE_SELL_PATTERNS):
            return _result(abs_amt, "investment_sell", "invest")
        d = f" {desc.lower()} "
        if " dividend " in d or " div " in d or _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "income", "earn")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if is_pos:
            return _result(abs_amt, "contribution", "save")
        return _result(abs_amt, "ignored", "invest")

    # ---- HSA ----
    if at == "hsa":
        if _match_any(desc, _CONTRIBUTION_PATTERNS) or _match_any(desc, _MATCH_PATTERNS):
            return _result(abs_amt, "contribution", "save")
        if _match_any(desc, _TRADE_BUY_PATTERNS):
            return _result(abs_amt, "investment_buy", "invest")
        if _match_any(desc, _TRADE_SELL_PATTERNS):
            return _result(abs_amt, "investment_sell", "invest")
        if _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "income", "earn")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if _match_any(desc, _MEDICAL_PATTERNS):
            return _result(abs_amt, "expense", "spend")
        if is_pos:
            return _result(abs_amt, "contribution", "save")
        return _result(abs_amt, "expense", "spend")

    # ---- 529 ----
    if at == "529":
        if _match_any(desc, _CONTRIBUTION_PATTERNS):
            return _result(abs_amt, "contribution", "save")
        if _match_any(desc, _WITHDRAWAL_PATTERNS):
            return _result(abs_amt, "withdrawal", "transfer")
        if _match_any(desc, _TRADE_BUY_PATTERNS):
            return _result(abs_amt, "investment_buy", "invest")
        if _match_any(desc, _TRADE_SELL_PATTERNS):
            return _result(abs_amt, "investment_sell", "invest")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if is_pos:
            return _result(abs_amt, "contribution", "save")
        return _result(abs_amt, "ignored", "invest")

    # ---- CHECKING ----
    if at == "checking":
        if is_pos and _match_any(desc, _INCOME_PATTERNS):
            return _result(abs_amt, "income", "earn")
        if is_pos and _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "interest", "earn")
        if is_neg and _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if _match_any(desc, _TRANSFER_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if _match_any(desc, _REFUND_PATTERNS):
            return _result(abs_amt, "expense_reversal", "earn")
        if is_pos:
            return _result(abs_amt, "income", "earn")
        return _result(abs_amt, "expense", "spend")

    # ---- SAVINGS ----
    if at == "savings":
        if _match_any(desc, _INTEREST_EARNED_PATTERNS):
            return _result(abs_amt, "interest", "earn")
        if _match_any(desc, _TRANSFER_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if is_neg and not _match_any(desc, _TRANSFER_PATTERNS):
            return _result(abs_amt, "needs_review", "transfer", True,
                           "Savings account debit without transfer pattern — may be a merchant purchase or fee.")
        if is_pos:
            return _result(abs_amt, "transfer", "transfer")
        return _result(abs_amt, "transfer", "transfer")

    # ---- DEBIT CARD ----
    if at == "debit_card":
        if _match_any(desc, _REFUND_PATTERNS):
            return _result(abs_amt, "expense_reversal", "earn")
        if _match_any(desc, _INCOME_PATTERNS):
            return _result(abs_amt, "income", "earn")
        if _match_any(desc, _TRANSFER_PATTERNS):
            return _result(abs_amt, "transfer", "transfer")
        if _match_any(desc, _FEE_PATTERNS):
            return _result(abs_amt, "fee", "spend")
        if is_pos:
            return _result(abs_amt, "income", "earn")
        return _result(abs_amt, "expense", "spend")

    # ---- OTHER ----
    if at == "other":
        return _result(abs_amt, "needs_review", "transfer", True,
                       "Unknown account type \"other\" — manually classify this transaction.")

    # ---- Fallback ----
    return _result(abs_amt, "needs_review", "transfer", True,
                   f"Unrecognized account type \"{at}\" — add classification rules for this type.")


# ------------------------------------------------------------------
# Auto-detection keywords (scanned from statement text to guess type)
# ------------------------------------------------------------------

PDF_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("credit_card", [
        "credit card", "payment due", "minimum payment",
        "new balance", "previous balance", "purchases",
        "cash advances", "credit limit", "available credit",
        "statement closing date", "payments and credits",
    ]),
    ("checking", [
        "checking account", "checking summary",
        "account summary", "beginning balance",
        "deposits and credits", "checks paid",
        "debits and withdrawals", "overdraft",
        "available balance", "current balance",
    ]),
    ("savings", [
        "savings account", "savings summary",
        "interest earned", "annual percentage yield",
        "savings statement", "money market",
    ]),
    ("mortgage", [
        "mortgage", "principal", "escrow",
        "mortgage payment", "loan number",
    ]),
    ("loan", [
        "loan statement", "loan account",
        "student loan", "auto loan", "personal loan",
        "loan balance", "principal balance",
    ]),
    ("401k", [
        "401(k)", "401k", "retirement plan",
        "employer contribution", "employee contribution",
        "netbenefits", "retirement savings",
    ]),
    ("investment", [
        "brokerage", "investment account",
        "portfolio", "trade confirmation",
        "dividend", "you bought", "you sold",
        "securities", "capital gains",
    ]),
    ("hsa", [
        "health savings", "hsa",
        "health savings account",
    ]),
    ("529", [
        "529 plan", "education savings",
        "529 account", "education plan",
    ]),
    ("ira", [
        "ira", "individual retirement",
        "roth ira", "traditional ira",
        "rollover ira", "sep ira",
    ]),
    ("crypto", [
        "crypto", "bitcoin", "ethereum",
        "digital asset", "cryptocurrency",
    ]),
]

CSV_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("credit_card", [
        "credit card", "payment due date", "minimum payment",
        "statement date", "credit limit",
    ]),
    ("401k", [
        "401k", "401(k)", "retirement", "netbenefits",
    ]),
    ("investment", [
        "trade date", "settle date", "symbol", "cusip",
        "quantity", "price", "cost basis",
        "security name", "security type",
    ]),
    ("savings", [
        "interest earned", "apy", "dividend rate",
    ]),
]
