"""Phase 5 + 5b.2 + 7 lift — /api/imports/ statement-upload UX with OCR fallback.

Phase 7 update: added .ofx + .qfx support (free Plaid alternative via
the standard OFX/QFX bank statement format from ofxparse library).
Phase 5b.2 update: when parse_uploaded_statement returns a PDF with
``record_count == 0``, the route falls back to ``ocr_parse_statement``
(pytesseract on rasterized pages).

Lift provenance: ``benefitsiq-backend/app/routes/imports.py``
(``docs/benefitsiq-merge-plan.md`` §4 Reuse Map item 18). Substantive changes:

- ``get_or_create_demo_user`` -> ``get_or_create_local_user(db, settings.local_user)``.
- ``from app.db import get_db`` → ``from app.database import get_db``.
- ``get_target_account`` flips ``Account.is_active == True`` ->
  ``Account.is_active.is_(True)`` (safer SQLAlchemy 2.0 idiom).
- Phase 5: explicit size guards + extension validation BEFORE the
  parser is invoked, returning 413 (file too large) and 415
  (unsupported media type).
- Phase 5b.2: OCR fallback for text-less PDFs (record_count==0 -> OCR).
- Phase 7: extension list + dispatcher now covers .ofx + .qfx + auth
  enforced + OCR fallback dead-code dropped + OCR cap lowered 200→50 MB.
- Phase-F2 #1 round-1: forwarder maps Finlynq 4xx→4xx verbatim + 5xx→502
  Bad Gateway; imports ``forward_detail`` (public) from
  ``app.routes.shared`` instead of the private ``_forward_detail`` from
  ``app.routes.categories``.
- Phase-F2 #1 round-2: forwarder now ALSO handles 3xx — a Finlynq
  302/304 (future OAuth or cache-redirect flow) is mapped to 502
  Bad Gateway instead of crashing on an empty redirect body that
  ``return r.json()`` can't decode.
"""
import json as _json
import logging
import re

# Phase 51 — the canonical account name for the auto-created fallback
# that ``get_target_account`` writes when the user has no active
# accounts. Hoisted to a module-level constant so the helper below,
# any test fixture that asserts on it, and a future i18n/rename pass
# share a single source of truth. Same anti-pattern-prevention
# pattern as :data:`services.import_parser.IMPORTED_TRANSACTION_PLACEHOLDER`
# in Phase 50.
IMPORTED_STATEMENTS_ACCOUNT_NAME = "Imported Statements"
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.auth import require_user
from app.account_types import (
    CREDIT_ACCOUNT_TYPES,
    PDF_TYPE_KEYWORDS,
    CSV_TYPE_KEYWORDS,
)
from app.database import get_db
from app.models import Account, ImportBatch, Transaction, User
from app.routes.shared import (
    get_or_create_family_member_self,
    get_or_create_institution,
    get_or_create_local_user,
    recalculate_account_balance,
)
from app.schemas import ImportBatchResponse, ImportResponse, TransactionResponse
from app.services.categorizer import categorize_transactions
from app.services.transfer_classifier import run_transfer_detection
from app.services.import_parser import (
    extract_pdf_transactions,
    parse_uploaded_statement,
)
from app.services.ocr_parser import ocr_parse_statement

# Module-level logger (declared AFTER all imports — see top of file).
_logger = logging.getLogger(__name__)


# =====================================================================
# Phase 54+ — fingerprint-based dedup for ``POST /api/imports/upload``.
# =====================================================================
# User spec: ``description fingerprint + (±$0.05) amount + date``.
# Two-row keep-one row.
#
# Canonical real-world trigger (June 2026 user report):
#   ``Paypal *Notarylive Ny`` — em-dash Amount, status "Promote to rule"
#   ``PAYPAL *NOTARYLIVE 4029253733 NY 401...`` — debit $25.00
#   ``ONLINE PAYMENT, THANK YOU`` — credit $877.30
# These three rows describe the same two payments (one PayPal, one
# autopay) under three different strings. The previous contract inserted
# all three; the Activity page showed 12 rows where the user expected
# 2. A fingerprint collapses ALL THREE payment forms into one row;
# the cross-format (Excel + PDF) re-import is the dominant trigger.
#
# Trade-offs documented inline:
#   - **False-positive risk (two-same-merchant same-day same-amount)**:
#     A user with two legitimately distinct $5.00 Starbucks charges on
#     the same day (morning coffee + return-trip coffee) will see the
#     SECOND row dropped as "duplicate" by this contract. The user
#     explicitly chose this trade-off (skip-on-hit, ±$0.05) over a
#     frequency-counting dedup which would be correct but slower.
#     A future ``Settings → Clean up duplicates`` affordance can add
#     a frequency-count override + per-row approve/dismiss UI.
#   - **N+1 query**: each candidate row triggers one SELECT against a
#     bounded window (same account, ±1 calendar day). For a 500-row
#     upload that's ~500ms on SQLite — acceptable. A future optimisation
#     is a single bulk-prefetch of the whole upload's date window
#     keyed by (account_id, fingerprint) into an in-memory dict; not
#     done in v1 because the SQL is straightforward and the perf is
#     fine within the dedup tolerance.
#   - **Date window ±1 day**: covers weekend-posted and TZ-shift
#     variations without widening the candidate space so much that
#     unrelated same-merchant rows on adjacent days merge.
# =====================================================================

# Strip 7+ digit sequences (payment reference IDs like
# ``PAYPAL *NOTARYLIVE 4029253733 NY 401...``'s trailing tail).
# 4–6 digit runs are kept — those are usually store / register / unit
# numbers that legitimately distinguish two same-merchant same-day rows.
_DIGIT_BLOB_RE = re.compile(r"\d{7,}")

# Strip these punctuation chars that banks insert around merchant names
# differently across CSV / PDF / OFX exports. The fingerprint's purpose
# is to match across formats, so normalizing them is the whole point.
#
# ``#`` is PRESERVED (not in the strip class) so register/store markers
# like ``STARBUCKS #1234`` vs ``STARBUCKS #5678`` fingerprint distinctly —
# the user sees the same symbol in the UI when they debug a collision.
# ``*`` IS stripped because PayPal flips between ``"PAYPAL *FOO"`` and
# ``"PAYPAL FOO"`` form across export formats; collapsing it is the
# whole point of the dedup. ``...`` / unicode ``…`` is stripped to
# normalize truncation tails.
_FINGERPRINT_STRIP_PUNCT_RE = re.compile(r"[.,*:;()…]+")

# Trailing-ellipsis stripper. Real-world bank exports truncate long
# description strings with `...` (some with the unicode `…`); strip
# them so truncated + full forms match.
_TRAILING_ELLIPSIS_RE = re.compile(r"\.{3,}$|…$")

# Whitespace collapse-after-everything-mutated sweep.
_WHITESPACE_COLLAPSE_RE = re.compile(r"\s+")

_DEDUP_AMOUNT_TOLERANCE = 0.05  # ± 5 cents per the user spec
_DEDUP_DATE_WINDOW = timedelta(days=1)  # ± 1 calendar day
# Bounded to 1000 candidates per query — a high-cardinality day (>1000
# transactions on one account in ±1 day) is a true edge case; we
# accept the silent-truncation risk in exchange for bounding the per-row
# query cost. A future Phase 55+ bulk pre-fetch (one query per
# ``account_id`` over the upload's full [min_date, max_date] window)
# replaces this N+1 with O(account) — documented in the route's
# inline comments.
_DEDUP_QUERY_CANDIDATE_LIMIT = 1000  # bounded candidate set per query


def _canonicalize_description_for_dedup(description: str | None) -> str:
    """Stable fingerprint for dedup matching.

    Returns the canonical form suitable for exact-string equality
    comparison. Two descriptions that fingerprint to the same string
    are treated as the same payment across CSV / PDF / OFX / Excel
    imports.

    Rules (applied in order):
      1. ``None`` / empty → ``""`` (caller treats this as
         "no fingerprint available"; the row is NEVER deduped).
      2. ``.strip()`` then ``.upper()``.
      3. Strip trailing ``...`` / ``…`` ellipsis tails.
      4. Strip ``.,*#:;()…`` punctuation.
      5. Strip 7+ digit sequences (payment reference IDs).
      6. Collapse all whitespace runs to a single space.

    Examples (the user's actual rows):
      - ``"PAYPAL *NOTARYLIVE 4029253733 NY 401..."``
            → ``"PAYPAL NOTARYLIVE NY"``
      - ``"Paypal *Notarylive Ny"``
            → ``"PAYPAL NOTARYLIVE NY"``
      - ``"ONLINE PAYMENT, THANK YOU"``
            → ``"ONLINE PAYMENT THANK YOU"``
      - ``"AUTOMV 9999900000761984AUTOPAY AUTO-PMT"``
            → ``"AUTOMV AUTOPAY AUTO-PMT"``

    Notes:
      - Asterisk ``*`` IS stripped so ``"PAYPAL *NOTARYLIVE"`` and
        ``"PAYPAL NOTARYLIVE"`` match. Real-world banks include or
        drop the asterisk arbitrarily between export formats.
      - 4-6 digit runs are NOT stripped so ``"STARBUCKS #1234"``
        and ``"STARBUCKS #5678"`` stay distinct (different store
        registers). This is the trade-off documented above.
    """
    if not description:
        return ""
    s = description.strip().upper()
    if not s:
        return ""
    s = _TRAILING_ELLIPSIS_RE.sub("", s)
    s = _FINGERPRINT_STRIP_PUNCT_RE.sub("", s)
    s = _DIGIT_BLOB_RE.sub("", s)
    s = _WHITESPACE_COLLAPSE_RE.sub(" ", s).strip()
    return s


def _find_duplicate_in_window(
    db: Session,
    *,
    account_id: int,
    fingerprint: str,
    txn_date: datetime,
    signed_amount: float,
) -> Transaction | None:
    """Query existing ``Transaction`` rows within the dedup window
    (same account_id, ±1 calendar day of ``txn_date``, signed amount
    within ±$0.05) and return the first row whose ``description``
    canonicalizes to ``fingerprint``.

    Returns ``None`` when ``fingerprint`` is empty (caller short-circuits)
    OR when no candidate row fingerprints identically. The first match
    (id ASC, deterministic) wins so a re-import with N copies of the
    same payment collapses to N identical skips with the SAME
    matched-row id — no flaky ordering.
    """
    if not fingerprint:
        return None
    lower_date = txn_date - _DEDUP_DATE_WINDOW
    upper_date = txn_date + _DEDUP_DATE_WINDOW
    abs_amount = abs(signed_amount)
    low_amount = abs_amount - _DEDUP_AMOUNT_TOLERANCE
    high_amount = abs_amount + _DEDUP_AMOUNT_TOLERANCE

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == account_id,
            Transaction.transaction_date >= lower_date,
            Transaction.transaction_date <= upper_date,
            Transaction.amount >= signed_amount - _DEDUP_AMOUNT_TOLERANCE,
            Transaction.amount <= signed_amount + _DEDUP_AMOUNT_TOLERANCE,
        )
        .order_by(Transaction.id.asc())
        .limit(_DEDUP_QUERY_CANDIDATE_LIMIT)
        .all()
    )
    for candidate in candidates:
        # Belt-and-suspenders: the SQL filter did the same ±$0.05 gate,
        # but ``abs()`` here is also a numerical truth-check (float
        # representation can drift at the boundary; the SQL filter is
        # inclusive on both sides, the Python comparison is the
        # definitive gate). Cost of running in the loop is trivial.
        if (
            abs(candidate.amount - signed_amount) <= _DEDUP_AMOUNT_TOLERANCE
            and _canonicalize_description_for_dedup(candidate.description)
            == fingerprint
        ):
            return candidate
    return None


# Phase 52+ — filename-driven account-type detection. The PDF / CSV
# statement header usually contains phrases like "Credit Card Statement"
# but transaction descriptions rarely do (they're just merchant names
# + amounts). So checking ONLY the transaction text often misclassifies
# a credit-card PDF as "checking" (the previous default-fallback). The
# filename is the most reliable signal: ``credit_card_2024_loan.pdf``
# → credit_card, ``amex_bronze.csv`` → credit_card, etc.
#
# Normalises the filename so underscores / hyphens count as word
# boundaries ("credit_card" matches the keyword "credit card").
# Returns ``None`` if no keyword matches so the caller can fall
# through to transaction-text detection.
def _detect_type_from_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    # Normalise _/- and strip the extension; uppercase for comparison.
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    normalised = stem.replace("_", " ").replace("-", " ").upper()
    # ``PDF_TYPE_KEYWORDS`` and ``CSV_TYPE_KEYWORDS`` are unioned — the
    # order is preserved (credit_card before loan, etc.) so ties resolve
    # to the more-specific type.
    combined = list(PDF_TYPE_KEYWORDS) + list(CSV_TYPE_KEYWORDS)
    for acct_type, keywords in combined:
        if any(kw.upper() in normalised for kw in keywords):
            return acct_type
    return None

# Generic filenames that don't convey enough info to auto-create a new
# account. When these are uploaded and the user already has an active
# account, we fall back to that account instead of creating a new one.
# Non-generic filenames (e.g. ``checking_Chase3100_Activity_20260705.csv``)
# always trigger auto-account-creation so the user's Chase and Citi
# imports land in separate accounts.
_GENERIC_FILENAME_STEMS = frozenset({
    "statement", "statements", "transaction", "transactions",
    "activity", "export", "download", "imported statement", "data",
})


def _is_generic_filename(filename: str | None) -> bool:
    """Return True when the filename is too generic to derive an account.

    A generic filename (e.g. ``statement.csv``) doesn't convey enough
    bank/issuer info to justify creating a new account when the user
    already has active accounts. A non-generic filename
    (e.g. ``checking_Chase3100_Activity_20260705.csv``) always triggers
    auto-account-creation.
    """
    if not filename:
        return True
    stem = filename.rsplit(".", 1)[0].strip().lower() if "." in filename else filename.strip().lower()
    return stem in _GENERIC_FILENAME_STEMS


router = APIRouter(prefix="/api/imports", tags=["imports"])

# Phase 7 size guards. CSV + OFX are text (small); PDF can be heavy.
# Tighter on CSV/OFX (10MB), OCR-bounded on PDF (50MB cap matches
# text-layer to keep peak memory stable). Phase 8+ can expose
# MAX_OCR_BYTES via env var if a real user needs bigger scans.
MAX_TEXT_BYTES = 10 * 1024 * 1024  # 10 MB — CSV + OFX + Excel
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB — PDF (text-layer)
MAX_PDF_OCR_BYTES = 50 * 1024 * 1024  # 50 MB — PDF (image-only, OCR)
_ALLOWED_EXTENSIONS = (".csv", ".pdf", ".ofx", ".qfx", ".xlsx", ".xls")
# Phase 11 — cap the persisted preview_lines so a 200-page OCR scan
# doesn't bloat the DB column. The route slices the parser output to
# the first N lines before writing ``import_batches.preview_lines``.
_PREVIEW_LINES_CAP = 50


def get_target_account(db: Session, user: User, account_id: Optional[int] = None) -> Account:
    """Resolve the import target account — explicit id, otherwise the first active
    account, otherwise lazily create an 'Imported Statements' account."""
    if account_id:
        account = (
            db.query(Account)
            .filter(Account.id == account_id, Account.user_id == user.id)
            .first()
        )
        if account:
            return account
        raise HTTPException(status_code=404, detail="Account not found")

    account = (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.is_active.is_(True))
        .order_by(Account.id)
        .first()
    )
    if account:
        return account

    institution = get_or_create_institution(db, IMPORTED_STATEMENTS_ACCOUNT_NAME)
    # Phase 16 — every account owns a family_member_id (NOT NULL FK).
    # Bootstrap the local user's Self row right before the INSERT
    # so the cold-start path (no FamilyMembers card visit yet) gets
    # a satisfied FK. Mirrors post/PUT /api/accounts/ — keep both
    # defaulting to Self so the user sees a consistent "Imported
    # Statements" account on the Accounts page under Self rather
    # than getting a NOT NULL violation.
    self_row = get_or_create_family_member_self(db, user)
    account = Account(
        user_id=user.id,
        institution_id=institution.id,
        account_name=IMPORTED_STATEMENTS_ACCOUNT_NAME,
        account_type="checking",
        current_balance=0.0,
        is_active=True,
        family_member_id=self_row.id,
        # Phase 40 — orphan safety-net fallback. The route stamps
        # ``source='imported'`` so a future "Clean up orphans"
        # filter can find this row without sniffing account_name;
        # ``description`` records the safety-net provenance so a
        # user hovering the chip reads exactly what the row is
        # (vs. an unannotated default that looks like a manual
        # account at a glance).
        source="imported",
        description=(
            "Default fallback — auto-created when no account "
            "is explicitly selected and no other active accounts "
            "exist."
        ),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _deactivate_orphan_imported_statements(
    db: Session,
    user_id: int,
    original_target_account_id: int,
    new_account_id: int,
) -> None:
    """Phase 51 — degrade-then-cleanup orphan: the ``Imported Statements`` fallback.

    ``get_target_account(None)`` ALWAYS auto-creates an
    ``Imported Statements`` row when the user has no active accounts —
    that's the safety net so the ``Transaction.account_id`` FK is
    satisfiable on the very first upload. When one of the 4
    auto-creation blocks below (multi-account Fidelity / multi-sheet
    Excel / single-PDF auto / single-CSV auto) creates a
    more-specific account, the fallback becomes a $0, 0-txns orphan
    sitting next to the right one on the Accounts page. The Phase 51
    user report (Chase credit-card CSV upload → 2 accounts: the named
    one + the orphan) was the canonical bug.

    The Phase 35 multi-account block was the first to clean this up
    inline; Phase 36 / 37 / 38 single-account auto paths now share
    this helper so the orphan is deactivated across every import
    shape, not just the multi-account one.

    Designed to be called AFTER the auto-block has created or matched
    the more-specific account. The 3 no-op branches are intentional,
    not bugs — each guards a different real edge case:

    - **No orphan row**: an explicit ``account_id`` was passed (FE
      dropdown) OR the user already had an active account, so
      ``get_target_account`` returned an existing account and never
      auto-created the orphan. Helper is a clean no-op.
    - **Orphan reused as new account**: a file literally named
      ``Imported Statements.csv`` matches the just-auto-created
      orphan on the ``account_name == csv_name`` lookup. The orphan
      IS the only account the user has; deactivating it would
      orphan the very rows we just persisted.
    - **Orphan has transactions**: a debug stash or a prior upload
      left rows on the fallback. Deactivating would orphan those
      transactions via the FK.

    Returns ``None``. The 3 no-op branches return ``None`` for the
    same reason — callers have nothing to gate on (the helper
    self-logs the deactivation in the ``account_name == "Imported
    Statements"`` case). Operators grepping ``.run/backend.log`` for
    ``deactivated orphaned`` continue to find the marker. Test
    coverage is the unit test's return-value assertions.

    No SQLAlchemy-identity-map expire: this helper mutates ``orphan``
    only, NOT ``batch.account``. ``batch.account_id`` is a FK only
    (ImportBatch has no ``account`` relationship in the ORM), so any
    ``batch.account_id`` reassignment at the call site commits
    without the ``account`` reconciliation trap that triggered the
    KeyError removal in Phase 51.
    """
    orphan = (
        db.query(Account)
        .filter(
            Account.id == original_target_account_id,
            Account.account_name == IMPORTED_STATEMENTS_ACCOUNT_NAME,
            Account.user_id == user_id,
        )
        .first()
    )
    if orphan is None:
        # Phase 51: clean no-op when ``get_target_account`` never
        # auto-created the orphan (explicit account_id OR an existing
        # active account was returned). Quiet — this is the
        # dominant case for users mid-onboarding who already have an
        # account.
        return None
    if orphan.id == new_account_id:
        # Phase 51: fallback was reused (a file literally named
        # ``Imported Statements.csv`` matched the just-auto-created
        # orphan). Don't deactivate the only account the user has.
        return None
    txn_count = (
        db.query(Transaction)
        .filter(Transaction.account_id == orphan.id)
        .count()
    )
    if txn_count > 0:
        # Phase 51: rows landed on the orphan (a debug stash or
        # pre-Phase 51 manual upload). Don't deactivate — the FK
        # would orphan the transactions.
        return None
    orphan.is_active = False
    # Phase 39+ — explicit flush so the deactivation is persisted
    # BEFORE any subsequent query (recalculate_account_balance,
    # transaction inserts, batch.refresh) can dirty or reconcile
    # the orphan via SQLAlchemy's identity map. Without this, a
    # downstream query that touches ``orphan`` would re-load the
    # stale ``is_active=True`` row from the in-memory state.
    db.flush()
    _logger.info(
        "Auto-import: deactivated orphaned %r (#%d), replaced by Account #%d",
        orphan.account_name, orphan.id, new_account_id,
    )


def _validate_upload_shape(file: UploadFile) -> str:
    """Pre-flight the upload BEFORE invoking the parser. Returns the
    lowercased extension (``"csv"`` / ``"pdf"`` / ``"ofx"`` / ``"qfx"``)
    on success. Raises 415 for unsupported extensions and 413 for
    files exceeding the per-format size budget."""
    filename = file.filename or ""
    if not filename.lower().endswith(_ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file extension. Allowed: CSV, PDF, OFX/QFX "
                f"(free Plaid alternative). Got: {filename!r}"
            ),
        )
    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    file.file.seek(0)
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        cap = MAX_PDF_BYTES
    elif ext == "csv":
        cap = MAX_TEXT_BYTES
    elif ext in ("ofx", "qfx"):
        cap = MAX_TEXT_BYTES
    else:
        cap = MAX_TEXT_BYTES
    if size_bytes > cap:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File too large: {size_bytes} bytes exceeds the {cap}-byte "
                f"{ext.upper()} limit."
            ),
        )
    return ext


@router.post("/upload", response_model=ImportResponse)
async def upload_statement(
    file: UploadFile = File(...),
    account_id: Optional[int] = Form(None),
    # Phase 52 — when the FE confirms a detected account type, the BE
    # overrides its auto-detection with this hint before account creation.
    account_type_hint: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 14 — local-first parser and persistence.

    Single source of truth: parse the upload with the local parser,
    INSERT ``ImportBatch`` + ``Transaction`` rows, and re-calculate
    the target account's ``current_balance`` from the ledger.

    **Why this no longer proxies to Finlynq (Phase F3 was reverted).**

    The Phase F3 httpx forwarder
    (``{settings.finlynq_base_url}/parse/upload``) silently dropped
    rows on real-world CSVs — the canonical user report was a Wells
    Fargo checking_stmt.csv upload where 381 of 525 expected rows
    landed (124 silently dropped). Finlynq's ``POST /parse/upload``
    at F3 also does NOT persist ImportBatch / Transaction rows
    (its own ``app.models`` lands in Phase F5+, deferred), so the
    Phase F3 forwarder was a relay that returned Finlynq's response
    shape without writing anything to the canonical store. Without
    local persistence the FE's ``GET /api/imports/batches``
    + ``GET /api/imports/batches/{id}/transactions`` would return
    empty lists on every reload — a dead-import-data UX bug. Phase
    14 closes both: the parser runs locally AND the transactions
    land in rules-service's own ``transactions`` table so the read
    side has data to serve.

    **Local fallback chain** (which file types get which path):

    1. ``parse_uploaded_statement`` for CSV + Excel + OFX + PDF
       with text layer. Returns ``parsed_records`` as a list of
       canonical dicts ready for ``Transaction`` row creation.
    2. For PDFs that have a text layer but a noisy line layout
       (the parser heuristic returns 0 transactions even though
       there ARE records) — the future Phase 14.1 heuristic
       will mine these; today we surface the preview-only envelope.
    3. For PDFs with NO text layer (parsed_records == 0):
       ``ocr_parse_statement`` (pytesseract) + ``extract_pdf_transactions``
       on the OCR-derived text lines. Phase 5b.2 already shipped the
       OCR helper; Phase 14 wires it back into the upload path now
       that Finlynq is bypassed.
    4. If ALL paths return 0 records: persist the ``ImportBatch``
       envelope with the captured preview lines so the FE still
       renders an inspection panel; ``saved_transactions == 0``
       propagates back to the user as informational.

    **Account-balance recalculation** is mandatory after the
    ledger insert: ``Account.current_balance`` is computed from
    ``SUM(transactions.amount)`` in
    :func:`app.routes.shared.recalculate_account_balance`. Without
    this the dashboard hero number drifts the moment the user uploads
    any file — the original "Account $0 but Activity has +
    $12,345" complaint.
    """
    _validate_upload_shape(file)

    local_user = get_or_create_local_user(db, _current_user)
    target_account = get_target_account(db, local_user, account_id)

    # Phase 14 — local parse. ``parse_uploaded_statement`` seeks to
    # 0 internally between the preview and persist sub-calls so we
    # only need to seek once here.
    file.file.seek(0)
    # ``parsed`` is bound on every control-flow path so a refactor that
    # turns the ValueError into a log+continue (to support partial
    # parsing) doesn't trip an unbound-name bug. Default is an
    # empty-records envelope — the safest failure shape.
    parsed: dict = {"parsed_records": [], "warnings": []}
    try:
        parsed = parse_uploaded_statement(file)
    except ValueError as exc:
        # Bad CSV / PDF / OFX / Excel schemas raise a structured
        # ValueError here ("Missing: description" / "Could not parse
        # CSV file" / etc). Surface as 400 BAD REQUEST so the FE
        # renders a "fix this file" banner instead of a 500.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse uploaded statement: {exc}",
        )
    raw_records = parsed.get("parsed_records") or []
    preview = parsed.get("preview") or []
    file_type = parsed.get("file_type", "csv")
    warnings = list(parsed.get("warnings") or [])
    expected_row_count = (
        parsed.get("expected_row_count")
        or parsed.get("record_count")
        or len(raw_records)
    )

    # Phase 14 — OCR fallback path for image-only PDFs. Triggered
    # when the text-layer parser saw SOMETHING (lines exist) but
    # couldn't extract any transactions AND it's a PDF — the
    # heuristic fails on Word/Exotic bank layouts. We rasterise
    # pages via pytesseract and re-run the heuristic on the OCR-
    # derived text lines.
    # Phase 52 — extract suggested_account_type from OFX parser result.
    suggested_acct_type: str | None = parsed.get("suggested_account_type")

    if file_type == "pdf" and not raw_records:
        try:
            file.file.seek(0)
            ocr_result = ocr_parse_statement(file)
            ocr_lines = ocr_result.get("text_lines") or []
            # OCR sometimes returns lines without a usable money-
            # shape; the heuristic drops those naturally.
            raw_records = extract_pdf_transactions(ocr_lines)
            if raw_records:
                _logger.info(
                    "Import %s: PDF OCR fallback yielded %d transactions.",
                    file.filename, len(raw_records),
                )
            else:
                _logger.info(
                    "Import %s: PDF OCR ran but heuristic found 0 transactions.",
                    file.filename,
                )
            if not preview and ocr_result.get("preview"):
                preview = ocr_result["preview"]
        except ValueError as exc:
            # Tesseract missing binary / OCR hard-fail. Surface as a
            # warning so the user can install tesseract if they want
            # the image-only path; we don't abort the upload — the
            # empty-import-batches envelope is still useful.
            warnings.append(
                f"OCR fallback unavailable for this PDF: {exc}"
            )
            _logger.warning(
                "Import %s: OCR fallback failed: %s", file.filename, exc,
            )    # Phase 11 — cap preview_lines at the DB-bounded length.
    # ``_PREVIEW_LINES_CAP`` defined at module level; the JSON
    # blob can be a flat list of strings (PDF/OFX/OCR) OR a list of
    # dicts (CSV/XLSX) so we don't constrain the inner shape here.
    # NOTE — ``saved_count`` is computed AFTER the dedup loop below,
    # not at this point, so it reflects POST-DEDUP rows inserted.
    # Computing it BEFORE the loop (i.e. ``= len(raw_records)`` here)
    # is the bug the integration tests caught — the FE would then
    # render "2 of 2 saved" even when Phase 54+ dedup collapsed one.
    preview_payload = preview[:_PREVIEW_LINES_CAP]  
    preview_blob = (
        _json.dumps(preview_payload, default=str) if preview_payload else None
    )

    batch = ImportBatch(
        user_id=local_user.id,
        account_id=target_account.id,
        filename=file.filename or parsed.get("filename") or "unknown",
        file_type=file_type,
        record_count=parsed.get("record_count", len(raw_records)),
        preview_lines=preview_blob,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    db.flush()  # populates batch.id for the FK on the transactions below

    # Phase 35 — multi-account support. If the parser detected
    # multiple accounts (Fidelity Investment Report), resolve each
    # account by account_number, auto-creating when needed, and
    # route each transaction to the correct account.
    is_multi_account = parsed.get("is_multi_account", False)
    extracted_accounts = parsed.get("extracted_accounts") or {}
    account_id_map: dict[str, int] = {}  # account_number → account.id

    # Save the original target_account id BEFORE the multi-account block
    # potentially reassigns it — needed for the orphan cleanup check below.
    original_target_account_id: int = target_account.id

    if is_multi_account and extracted_accounts:
        fidelity_institution = get_or_create_institution(db, "Fidelity Investments")
        for acct_num, acct_meta in extracted_accounts.items():
            existing = (
                db.query(Account)
                .filter(
                    Account.account_number == acct_num,
                    Account.user_id == local_user.id,
                )
                .first()
            )
            if existing:
                account_id_map[acct_num] = existing.id
                # Phase 35+ — reactivate a previously-deactivated account.
                # When the user deletes a batch and re-imports, the
                # account may be inactive from a prior deactivation.
                if not existing.is_active:
                    existing.is_active = True
                    _logger.info(
                        "Multi-account import: reactivated Account #%d (%s)",
                        existing.id, existing.account_name,
                    )
                _logger.info(
                    "Multi-account import: matched %s → Account #%d (%s)",
                    acct_num, existing.id, existing.account_name,
                )
            else:
                self_row = get_or_create_family_member_self(db, local_user)
                new_acct = Account(
                    user_id=local_user.id,
                    institution_id=fidelity_institution.id,
                    account_name=acct_meta.get("account_name", f"Fidelity {acct_num}"),
                    account_type=acct_meta.get("account_type", "investment"),
                    account_number=acct_num,
                    current_balance=0.0,
                    is_active=True,
                    family_member_id=self_row.id,
                    # Phase 40 — Fidelity Investment Report split.
                    # The N-accounts count is captured at this
                    # moment so a re-import (which matches on
                    # account_number and skips the new-Acct path)
                    # keeps the original description intact.
                    source="imported",
                    description=(
                        f"Fidelity Investment Report: "
                        f"{len(extracted_accounts)} accounts from "
                        f"{file.filename or 'statement'}"
                    ),
                )
                db.add(new_acct)
                db.flush()
                account_id_map[acct_num] = new_acct.id
                _logger.info(
                    "Multi-account import: auto-created %s (#%d) for %s",
                    new_acct.account_name, new_acct.id, acct_num,
                )
        db.flush()
        # Update the batch to point to the first resolved account so
        # the response's account_id reflects a real Fidelity account
        # rather than the "Imported Statements" fallback.
        first_acct_id = next(iter(account_id_map.values()), None)
        if first_acct_id is not None:
            batch.account_id = first_acct_id
            target_account = db.query(Account).filter(Account.id == first_acct_id).first() or target_account
            # NOTE — ImportBatch has no ``account`` relationship in the
            # ORM (we only carry ``account_id`` as a FK column), so a
            # ``db.expire(batch, ["account"])`` call would raise
            # ``KeyError`` here. The FK reassignment above is sufficient:
            # any later code that reads ``batch.account_id`` hits the new
            # value without a stale-relationship reconciliation. Phase
            # 35's existing bulk-update path is a query->update that
            # also doesn't touch the (non-existent) relationship.
            _logger.info(
                "Multi-account import: batch #%d reassigned to Account #%d",
                batch.id, first_acct_id,
            )
        # Phase 51 — deactivate the "Imported Statements" fallback
        # that ``get_target_account`` auto-created before this
        # multi-account block fired. Same idiom as the single-account
        # blocks below (36 / 37 / 38): use ``original_target_account_id``
        # (saved before the reassignment) because ``target_account``
        # now points to the first Fidelity account, NOT the orphan.
        # The helper handles the no-op branches (no orphan, orphan
        # reused, orphan has transactions) and emits the
        # ``deactivated orphaned`` log marker.
        if first_acct_id is not None:
            _deactivate_orphan_imported_statements(
                db, local_user.id, original_target_account_id, first_acct_id,
            )

    # Phase 36 — Excel multi-sheet auto-account support. When the
    # user selects "Auto-detect" (account_id=None) and uploads a
    # multi-sheet Excel workbook, auto-create one account per sheet
    # (e.g. "Checking", "Savings") under an institution named after
    # the file. Single-sheet workbooks get a single account with the
    # sheet name. CSV/OFX/PDF single-sheet files are NOT affected
    # (they fall through to ``target_account``).
    # Phase 52 — for OFX files, override the suggested account type with
    # the parser's auto-detected value (or the FE's hint).
    if file_type in ("ofx", "qfx") and account_id is None and raw_records:
        # Phase 52+ — preference order: hint > filename > parser hint > checking.
        ofx_type = (
            account_type_hint
            or _detect_type_from_filename(file.filename)
            or suggested_acct_type
            or "checking"
        )
        # Find or create the target account with this type
        ofx_name = (
            (file.filename or "OFX Statement")
            .rsplit(".", 1)[0].strip().title()
            or "OFX Statement"
        )
        # Update target account type if it was the generic fallback
        if target_account.account_type == "checking" and target_account.account_name == IMPORTED_STATEMENTS_ACCOUNT_NAME:
            target_account.account_type = ofx_type
            db.add(target_account)
            db.flush()
        _logger.info(
            "OFX import: account_type=%s filename=%s",
            ofx_type, file.filename,
        )

    is_multi_sheet_excel = (
        file_type in ("xlsx", "xls")
        and account_id is None
        and any(r.get("sheet_name") for r in raw_records)
    )
    sheet_account_id_map: dict[str, int] = {}
    if is_multi_sheet_excel:
        unique_sheets = list(dict.fromkeys(
            r["sheet_name"] for r in raw_records if r.get("sheet_name")
        ))
        inst_name = (
            (file.filename or "Imported").rsplit(".", 1)[0].strip().title()
            or IMPORTED_STATEMENTS_ACCOUNT_NAME
        )
        institution = get_or_create_institution(db, inst_name)
        self_row = get_or_create_family_member_self(db, local_user)
        for sheet in unique_sheets:
            existing = (
                db.query(Account)
                .filter(
                    Account.account_name == sheet,
                    Account.user_id == local_user.id,
                    Account.institution_id == institution.id,
                )
                .first()
            )
            if existing:
                sheet_account_id_map[sheet] = existing.id
                _logger.info(
                    "Excel multi-sheet import: matched %r → Account #%d (%s)",
                    sheet, existing.id, existing.account_name,
                )
            else:
                new_acct = Account(
                    user_id=local_user.id,
                    institution_id=institution.id,
                    account_name=sheet,
                    account_type="checking",
                    current_balance=0.0,
                    is_active=True,
                    family_member_id=self_row.id,
                    # Phase 40 — Excel multi-sheet auto. The sheet
                    # name appears in the description so a
                    # "Checking" + "Savings" multi-sheet import
                    # produces two cards the user can disambiguate.
                    source="imported",
                    description=(
                        f"Excel sheet '{sheet}' from "
                        f"{file.filename or 'workbook'}"
                    ),
                )
                db.add(new_acct)
                db.flush()
                sheet_account_id_map[sheet] = new_acct.id
                _logger.info(
                    "Excel multi-sheet import: auto-created %r (#%d) under %r",
                    sheet, new_acct.id, inst_name,
                )
        db.flush()

        # Phase 51 — orphan cleanup. Defer to AFTER the per-sheet
        # loop so the helper sees the final set of auto-created /
        # matched sheet accounts. ``batch.account_id`` was set to
        # the orphan at ImportBatch construction time (above);
        # reassigning to the FIRST sheet account so the UI's
        # import-history table renders a real sheet account instead
        # of the deactivated orphan envelope is what Phase 36 was
        # missing pre-Phase 51 — the gemini review caught it.
        first_sheet_id = next(iter(sheet_account_id_map.values()), None)
        if first_sheet_id is not None:
            batch.account_id = first_sheet_id
            target_account = (
                db.query(Account)
                .filter(Account.id == first_sheet_id)
                .first()
                or target_account
            )
            _logger.info(
                "Excel multi-sheet import: batch #%d reassigned to Account #%d",
                batch.id, first_sheet_id,
            )
            _deactivate_orphan_imported_statements(
                db, local_user.id, original_target_account_id, first_sheet_id,
            )

    # Phase 37 — single-account PDF auto-account support. When the
    # user selects "Auto-detect" (account_id=None) and the PDF is
    # NOT multi-account (standalone HSA, brokerage, bank statement),
    # create a dedicated account named after the filename instead
    # of dumping everything into the generic "Imported Statements"
    # fallback. Account type is inferred from transaction-description
    # keywords (HSA, investment, brokerage, dividend, etc.).
    # Phase 52+ — auto-create a PDF account when:
    # (a) the target is the "Imported Statements" fallback (no active
    #     accounts), OR
    # (b) the filename is non-generic (contains bank/issuer info like
    #     ``credit_citi_2026.pdf``) so we can derive a distinct account
    #     name that won't collide with the user's existing accounts.
    pdf_has_meta = bool(parsed.get("pdf_issuer") and parsed.get("pdf_account_suffix"))
    is_single_pdf_auto = (
        file_type == "pdf"
        and account_id is None
        and not is_multi_account
        and raw_records
        and (
            not _is_generic_filename(file.filename)
            or pdf_has_meta
            or target_account.account_name == IMPORTED_STATEMENTS_ACCOUNT_NAME
        )
    )
    if is_single_pdf_auto:
        pdf_name = (
            (file.filename or "Imported Statement")
            .rsplit(".", 1)[0].strip().title()
            or "Imported Statement"
        )
        # Phase 52 — auto-detect bank issuer + account suffix from
        # the PDF parser's metadata so accounts get names like
        # "Citi Credit Card (...0690)" instead of the filename.
        pdf_issuer = parsed.get("pdf_issuer")
        pdf_account_suffix = parsed.get("pdf_account_suffix")
        # Phase 52 — scan the statement text for account-type keywords.
        # Uses the canonical keyword lists from app.account_types.
        text_sample = " ".join(
            str(r.get("description", ""))[:200] for r in raw_records[:10]
        ).upper()

        def _detect_pdf_type(text: str) -> str:
            """Scan text for account-type keywords; return canonical type."""
            for acct_type, keywords in PDF_TYPE_KEYWORDS:
                if any(kw.upper() in text for kw in keywords):
                    return acct_type
            return "checking"

        # Phase 52+ — filename FIRST (most reliable signal). A filename
        # like ``credit_card_2024_loan.pdf`` resolves to "credit_card"
        # before we ever scan transaction descriptions (which rarely
        # contain "credit card" themselves).
        pdf_type = _detect_type_from_filename(file.filename) or _detect_pdf_type(text_sample)
        # Phase 52 — if the FE sent an explicit type hint, honour it over
        # the auto-detected type (user overrode the suggestion).
        if account_type_hint and account_type_hint.strip():
            pdf_type = account_type_hint.strip().lower()
        # Phase 52 — if we detected issuer + account suffix, build
        # a meaningful account name and use the real bank institution.
        if pdf_issuer and pdf_account_suffix:
            type_label = pdf_type.replace("_", " ").title()
            pdf_name = f"{pdf_issuer} {type_label} (...{pdf_account_suffix})"
        inst_name = pdf_issuer or IMPORTED_STATEMENTS_ACCOUNT_NAME
        institution = get_or_create_institution(db, inst_name)
        self_row = get_or_create_family_member_self(db, local_user)
        existing = (
            db.query(Account)
            .filter(
                Account.account_name == pdf_name,
                Account.user_id == local_user.id,
            )
            .first()
        )
        if existing:
            target_account = existing
            batch.account_id = existing.id
            _logger.info(
                "Single-PDF import: matched %r → Account #%d (%s)",
                pdf_name, existing.id, existing.account_name,
            )
        else:
            new_acct = Account(
                user_id=local_user.id,
                institution_id=institution.id,
                account_name=pdf_name,
                account_type=pdf_type,
                account_number=pdf_account_suffix,
                current_balance=0.0,
                is_active=True,
                family_member_id=self_row.id,
                # Phase 40 — single-PDF auto. ``pdf_type`` is the
                # parser-inferred account type (hsa / investment /
                # credit_card / checking) so a user hovering the
                # chip can see exactly what shape the import
                # produced.
                source="imported",
                description=(
                    f"Imported PDF from {file.filename or 'statement'} "
                    f"({len(raw_records)} transactions, type={pdf_type})"
                ),
            )
            db.add(new_acct)
            db.flush()
            target_account = new_acct
            batch.account_id = new_acct.id
            # NOTE — ImportBatch has no ``account`` relationship in the
            # ORM (we only carry ``account_id`` as a FK column), so a
            # ``db.expire(batch, ["account"])`` call would raise
            # ``KeyError`` here. The FK reassignment above is the
            # correct contract; Phase 35's existing bulk-update path
            # is a query->update that also doesn't touch the
            # (non-existent) relationship.
            _logger.info(
                "Single-PDF import: auto-created %r (#%d, type=%s)",
                pdf_name, new_acct.id, pdf_type,
            )

        # Phase 51 — orphan cleanup. ``get_target_account`` auto-
        # created an "Imported Statements" fallback if the user
        # had no active accounts at upload time; the single-PDF
        # block just replaced it with a filename-derived account.
        # Deactivate the orphan so the Accounts page renders one
        # card, not two. ``target_account.id`` is now the
        # match-or-create result, so this call is safe regardless
        # of which branch fired above.
        _deactivate_orphan_imported_statements(
            db, local_user.id, original_target_account_id, target_account.id,
        )

    # Phase 38 — CSV auto-account support. When the user selects
    # "Auto-detect" (account_id=None) and uploads a CSV file, create
    # a dedicated account named after the filename (e.g.
    # "chase-checking.csv" → "Chase Checking") instead of falling
    # through to the generic "Imported Statements" account.
    # Phase 52+ — auto-create a CSV account when:
    # (a) the target is the "Imported Statements" fallback (no active
    #     accounts), OR
    # (b) the filename is non-generic (contains bank/issuer info like
    #     ``checking_Chase3100_Activity_20260705.csv``) so we can derive
    #     a distinct account name that won't collide with existing ones.
    # This fixes the bug where a Chase CSV upload with auto-detect would
    # import into the user's existing Citi card account instead of
    # creating a new Chase account.
    is_csv_auto = (
        file_type == "csv"
        and account_id is None
        and raw_records
        and (
            not _is_generic_filename(file.filename)
            or target_account.account_name == IMPORTED_STATEMENTS_ACCOUNT_NAME
        )
    )
    if is_csv_auto:
        csv_name = (
            (file.filename or "Imported Statement")
            .rsplit(".", 1)[0].strip().title()
            or "Imported Statement"
        )
        # Phase 52 — CSV auto-account:
        # 1) explicit FE hint wins,
        # 2) then filename (most reliable signal: ``amex_bronze.csv``
        #    → "credit_card" without scanning CSV cells),
        # 3) then column headers (only ``CSV_TYPE_KEYWORDS`` here),
        # 4) default to "checking".
        csv_type = "checking"
        csv_type_detected = False
        if account_type_hint and account_type_hint.strip():
            csv_type = account_type_hint.strip().lower()
            csv_type_detected = True
        elif (fname_type := _detect_type_from_filename(file.filename)):
            csv_type = fname_type
            csv_type_detected = True
        elif parsed.get("preview") and isinstance(parsed["preview"], list) and len(parsed["preview"]) > 0:
            first_row = parsed["preview"][0]
            if isinstance(first_row, dict):
                col_text = " ".join(str(k) for k in first_row.keys()).upper()
                for acct_type, keywords in CSV_TYPE_KEYWORDS:
                    if any(kw.upper() in col_text for kw in keywords):
                        csv_type = acct_type
                        csv_type_detected = True
                        break

        institution = get_or_create_institution(db, IMPORTED_STATEMENTS_ACCOUNT_NAME)
        self_row = get_or_create_family_member_self(db, local_user)
        existing = (
            db.query(Account)
            .filter(
                Account.account_name == csv_name,
                Account.user_id == local_user.id,
            )
            .first()
        )
        if existing:
            target_account = existing
            batch.account_id = existing.id
            _logger.info(
                "CSV import: matched %r → Account #%d (%s)",
                csv_name, existing.id, existing.account_name,
            )
        else:
            new_acct = Account(
                user_id=local_user.id,
                institution_id=institution.id,
                account_name=csv_name,
                account_type=csv_type,
                current_balance=0.0,
                is_active=True,
                family_member_id=self_row.id,
                # Phase 40 — single-CSV auto. ``raw_records`` is
                # the saved-transactions count; ``expected_row_count``
                # (the parser's row-with-failures total) is NOT
                # used because the FE renders that as a separate
                # warning via the ImportResponse envelope.
                source="imported",
                description=(
                    f"Imported CSV from {file.filename or 'statement'} "
                    f"({len(raw_records)} transactions)"
                ),
            )
            db.add(new_acct)
            db.flush()
            target_account = new_acct
            batch.account_id = new_acct.id
            _logger.info(
                "CSV import: auto-created %r (#%d)",
                csv_name, new_acct.id,
            )

        # Phase 51 — orphan cleanup, the user-reported
        # ``Import ED STATEMENTS comes back every CSV`` regression.
        # ``get_target_account(None)`` auto-created the orphan at
        # the top of this route when the user had no active
        # accounts; this block just replaced it with the
        # filename-derived CSV account. Deactivate the orphan so
        # the Accounts page renders one card, not two — matches
        # the helper call in Phase 35 multi-account + Phase 36
        # multi-sheet Excel + Phase 37 single-PDF auto above.
        _deactivate_orphan_imported_statements(
            db, local_user.id, original_target_account_id, target_account.id,
        )    # Phase 54+ — dedup state for the persist loop. ``seen_fingerprints``
    # catches within-batch duplicates (newly-added-but-unflushed rows
    # are NOT visible to ``db.query()`` until the loop's flush at the
    # bottom; an in-memory set is the only way to dedup a CSV where
    # the SAME row appears twice on adjacent lines). The cross-batch
    # check fires against ``db`` (already-persisted rows from prior
    # imports).
    #
    # UPDATE: duplicates are now INSERTED with ``is_duplicate=True``
    # and ``duplicate_of_id`` pointing to the original, rather than
    # skipped. The user reviews them on the Activity page and resolves
    # (keep this one / keep original / keep all).
    seen_fingerprints: dict[tuple[str, str, int], Transaction] = {}
    duplicates_flagged = 0
    flagged_descriptions: list[str] = []
    # Track the first-seen txn for within-batch dupes so we can set
    # ``duplicate_of_id`` on the second occurrence even before the
    # first is flushed (SQLAlchemy populates .id on flush).

    for record in raw_records:
        # Phase 35 — if this is a multi-account import, route the
        # transaction to the correct account based on its
        # ``account_number`` key. Falls back to ``target_account``
        # for single-account imports (existing behavior).
        txn_account_id = target_account.id
        if is_multi_account:
            rec_acct_num = record.get("account_number")
            if rec_acct_num and rec_acct_num in account_id_map:
                txn_account_id = account_id_map[rec_acct_num]
            else:
                # Unmatched row — fall back to first resolved account
                txn_account_id = next(iter(account_id_map.values()), target_account.id)
        elif is_multi_sheet_excel:
            sheet = record.get("sheet_name")
            if sheet and sheet in sheet_account_id_map:
                txn_account_id = sheet_account_id_map[sheet]
            else:
                # Unmatched row — fall back to the target account so a
                # sheet-less record still lands somewhere sane rather
                # than crashing the persist loop on a missing dict key.
                # Same fallback shape as the multi-account branch's
                # "no account_number" path above.
                txn_account_id = target_account.id

        # CRITICAL: Transaction model has NO ``user_id`` column —

        # CRITICAL: Transaction model has NO ``user_id`` column —
        # the FK chain runs through ``account.user_id``. Setting
        # ``user_id=local_user.id`` here would raise TypeError on
        # every upload (Phase 14 lesson: implicit scoping via the
        # account FK is intentional). The local_user variable is
        # only used for ImportBatch (which DOES have user_id).
        #
        # Phase 52+ — debit / credit triple-write. The parser now
        # emits unsigned-positive ``debit`` and ``credit`` magnitudes
        # alongside the signed ``amount`` (``amount = credit -
        # debit``), and we mirror those magnitudes verbatim into
        # the new Transaction columns. The historical per-type
        # sign-flip at THIS layer (``if account_type in
        # ``CREDIT_ACCOUNT_TYPES: amount = -amount``) is removed:
        # the parser already preserves the canonical bank-statement
        # sign convention so a purchase stored as ``-10.68``
        # already represents a money-out event in the universal
        # accounting convention (``amount = credit - debit`` =
        # 0 - 10.68 = -10.68``). The Phase 52 diesel-gate the old
        # flip was patching (a credit import whose transactions
        # landed in a ``checking``-typed account and surfaced as a
        # positive net worth contribution) is closed upstream
        # by the Phase 52 filename-based account-type detection
        # at upload time, so the per-type flip here is no longer
        # the right layer to defend a sign-flip at.
        #
        # Idempotency: a re-import of the same file would INSERT
        # a duplicate row (the unique-by-plaid-id guard does not
        # cover non-Plaid CSVs and is not in scope here). The
        # user's Business Logic stays as-is — duplicate-detection
        # is a separate concern (follow-up phase).
        # Phase 54+ — fingerprint dedup BEFORE constructing ``txn``.
        # The signer already validated ``record["amount"]`` parses as a
        # float so we can safely coerce. ``record["transaction_date"]``
        # is a ``datetime`` (the parser's ``_parse_date`` raises on bad
        # input so we always get a real DateTime here, never a NaT).
        description = record["description"]
        txn_date = record["transaction_date"]
        amount = float(record["amount"])
        fingerprint = _canonicalize_description_for_dedup(description)
        # Phase 54+ — dedup tracking. Instead of skipping duplicates,
        # we INSERT them but flag with is_duplicate=True and
        # duplicate_of_id pointing to the original. The user reviews
        # and resolves on the Activity page.
        is_dup = False
        dup_of_id: int | None = None
        if fingerprint:
            # Within-batch dedup — exact to the cent (no tolerance for
            # within-batch rows because CSV exports are byte-identical
            # when the bank writes the same row twice; ±$0.05 would
            # over-match). ``iso_date`` collapses TZ-aware datetimes
            # to calendar date so a 03:59 row and an 04:01 row on the
            # same day get the same key.
            iso_date = txn_date.date().isoformat()
            cents_key = int(round(amount * 100))
            within_batch_key = (fingerprint, iso_date, cents_key)
            if within_batch_key in seen_fingerprints:
                is_dup = True
                # The first-seen txn may not have an id yet (not
                # flushed). Store the object; we'll resolve the id
                # after flush.
                first_txn = seen_fingerprints[within_batch_key]
                if first_txn.id is not None:
                    dup_of_id = first_txn.id
                duplicates_flagged += 1
                if len(flagged_descriptions) < 10:
                    flagged_descriptions.append(description[:60])
                _logger.info(
                    "Import %s: flagging within-batch duplicate %r "
                    "(fingerprint=%r date=%s amount=%.2f)",
                    file.filename, description[:60],
                    fingerprint, iso_date, amount,
                )
            else:
                # Cross-batch dedup — query existing rows in the
                # ±1-day window with ±$0.05 signed-amount tolerance.
                matched = _find_duplicate_in_window(
                    db,
                    account_id=txn_account_id,
                    fingerprint=fingerprint,
                    txn_date=txn_date,
                    signed_amount=amount,
                )
                if matched is not None:
                    is_dup = True
                    dup_of_id = matched.id
                    duplicates_flagged += 1
                    if len(flagged_descriptions) < 10:
                        flagged_descriptions.append(description[:60])
                    _logger.info(
                        "Import %s: flagging cross-batch duplicate %r "
                        "(matches txn #%d fingerprint=%r)",
                        file.filename, description[:60],
                        matched.id, fingerprint,
                    )
        # ``get("debit")`` / ``get("credit")`` may be ``None`` for
        # zero-amount rows or legacy records without the field.
        # Mirror those to ``NULL`` on insert so a balance
        # ``COALESCE(SUM(debit), 0)`` doesn't inflate with phantom
        # zero-rows.
        # ``not isinstance(v, bool)`` deliberately tightens the
        # check: ``isinstance(True, (int, float)) == True`` is a
        # Python gotcha (bool is a subclass of int), so without the
        # guard a future bug that sent ``True`` to this route
        # would silently coerce to ``1.0`` in either column. The
        # CSV/Excel parsers never emit booleans here, but the
        # guard is cheap insurance for a future parser refactor.
        def _to_float_or_none(v: Any) -> float | None:
            if v is None:
                return None
            if isinstance(v, bool):
                return None
            if isinstance(v, (int, float)):
                return float(v)
            return None

        debit_for_insert = _to_float_or_none(record.get("debit"))
        credit_for_insert = _to_float_or_none(record.get("credit"))
        # Phase 54+ — derive debit/credit from signed amount when the
        # parser path didn't supply them. Universal accounting
        # convention from the Transaction model: ``amount = credit
        # - debit`` (positive = money in, negative = money out).
        # The CSV/Excel paths emit D/C magnitudes verbatim inside
        # their parsers (:func:`parse_csv_transactions` /
        # :func:`_df_to_records`) so the fallback is a no-op there.
        # The PDF/OFX regex paths (:func:`parse_pdf_transactions` /
        # :func:`parse_ofx_transactions` and the OCR-fallback path
        # which also calls ``extract_pdf_transactions(ocr_lines)``)
        # emit ONLY a signed ``amount`` and no D/C keys — so the
        # route MUST fill them in at this layer or the FE's
        # ``formatBookkeepingCell(...).populated === true`` gate
        # evaluates false for every PDF/OFX row and the dual-column
        # UI renders em-dashes forever (the canonical "Amount column
        # populates, Debit/Credit columns stay em-dash" report from
        # a Chase/Amex/BofA PDF upload).
        #
        # Sign rule (mirrors :func:`parse_csv_transactions`):
        #   amount  > 0  -> credit_for_insert = amount
        #   amount  < 0  -> debit_for_insert  = -amount
        #   amount == 0  -> both stay NULL (FX-neutral row)
        if debit_for_insert is None and credit_for_insert is None and amount != 0:
            if amount > 0:
                credit_for_insert = amount
            else:  # amount < 0 (we excluded == 0 above)
                debit_for_insert = -amount
        txn = Transaction(
            account_id=txn_account_id,
            import_batch_id=batch.id,
            description=record["description"],
            amount=amount,
            debit=debit_for_insert,
            credit=credit_for_insert,
            transaction_date=record["transaction_date"],
            merchant_name=record.get("merchant_name"),
            is_pending=bool(record.get("is_pending", False)),
            is_duplicate=is_dup,
            duplicate_of_id=dup_of_id,
        )
        db.add(txn)
        # Track within-batch fingerprints so the NEXT row can
        # reference this txn as its duplicate_of_id.
        if fingerprint:
            iso_date = txn_date.date().isoformat()
            cents_key = int(round(amount * 100))
            within_batch_key = (fingerprint, iso_date, cents_key)
            if within_batch_key not in seen_fingerprints:
                seen_fingerprints[within_batch_key] = txn

    db.flush()

    # Phase 54+ — post-flush fixup: within-batch duplicates whose
    # original hadn't been flushed yet now have duplicate_of_id=None.
    # After flush, all txns have IDs, so we can fix these up.
    _fixup_count = 0
    just_flushed = (
        db.query(Transaction)
        .filter(
            Transaction.import_batch_id == batch.id,
            Transaction.is_duplicate.is_(True),
            Transaction.duplicate_of_id.is_(None),
        )
        .all()
    )
    for dup in just_flushed:
        fp = _canonicalize_description_for_dedup(dup.description)
        if fp:
            iso = dup.transaction_date.date().isoformat()
            ck = int(round(dup.amount * 100))
            k = (fp, iso, ck)
            if k in seen_fingerprints:
                orig = seen_fingerprints[k]
                if orig.id is not None and orig.id != dup.id:
                    dup.duplicate_of_id = orig.id
                    _fixup_count += 1
    if _fixup_count > 0:
        db.flush()
        _logger.info(
            "Import %s: post-flush fixup set duplicate_of_id on %d within-batch duplicate(s)",
            batch.filename, _fixup_count,
        )

    # Phase 54+ — ALL rows are now saved (duplicates are flagged,
    # not skipped). ``saved_count`` = total raw records because every
    # row hits the DB. ``duplicates_flagged`` is the count that were
    # marked ``is_duplicate=True``.
    saved_count = len(raw_records)

    # Phase 35+36 — for multi-account / multi-sheet imports, recalculate
    # EVERY affected account's balance (not just the target_account).
    # For single-account imports, this is a no-op loop over one id.
    # CRITICAL — recalculate the target account's current_balance
    # from the ledger after the inserts. Without this the stored
    # balance drifts from ``SUM(transactions.amount)`` the moment
    # any upload lands and the dashboard hero number goes stale.
    if is_multi_account:
        for acct_id in account_id_map.values():
            recalculate_account_balance(db, acct_id)
    if is_multi_sheet_excel:
        for acct_id in sheet_account_id_map.values():
            recalculate_account_balance(db, acct_id)
    new_balance = recalculate_account_balance(db, target_account.id)
    _logger.info(
        "Import %s persisted: file_type=%s records=%d saved=%d "
        "balance=%.2f account_id=%d",
        batch.filename, file_type,
        parsed.get("record_count", len(raw_records)),
        saved_count, new_balance, target_account.id,
    )

    db.commit()
    db.refresh(batch)

    # Phase 17 — per-batch auto-categorize. Right after the import
    # commit, fetch the just-imported transactions that DON'T have a
    # manual category yet and run the substring-merchant categorizer
    # on them. The flow is:
    #
    # 1. SELECT FROM transactions WHERE import_batch_id == batch.id
    #    AND category_id IS NULL — excludes any pre-tagged rows so
    #    the user's manual override from a previous import survives
    #    intact.
    # 2. CALL categorize_transactions() — pure substring heuristic
    #    against the MERCHANT_RULES dict; returns (categorized,
    #    skipped). The service already short-circuits
    #    ``if txn.category_id == match.id`` so a row whose heuristic
    #    match is the SAME category it already has is NOT churned.
    # 3. COMMIT so the row updates flush + the FE can GET the
    #    category_id on a follow-up ``GET /api/imports/batches/{id}
    #    /transactions`` without the SELECT showing NULL.
    #
    # Per-batch scope (vs bulk-all-uncategorized) is intentional:
    # the user's previous 'Auto-categorize' button ran on ALL
    # rows, which can clobber manual overrides on older transactions
    # after a re-import. Scoping to ``import_batch_id`` keeps the
    # click-after-upload experience surgically precise — each upload
    # ONLY organsises the rows it just landed.
    #
    # Zero-row fast-path: if ``saved_count == 0`` (PDF preview-only
    # envelope or fully-malformed CSV) we skip the call entirely so
    # the response shape carries ``(0, 0)`` — clearer than
    # calling with an empty list.
    #
    # Resilience: the auto-categorize block catches a NARROW set of
    # known-safe blips so an arbitrary categorizer crash does NOT
    # 500 the upload. The data IS already persisted above — if the
    # safety net fails, the user sees an "Upload failed" toast while
    # the rows are silently in the DB, and re-clicking upload
    # DOUBLE-INSERTS 505 transactions.
    #
    # The tuple is intentional: anything NOT in it (``NameError``,
    # ``ImportError``, ``MemoryError``, ``RecursionError``, …) bubbles
    # up and 500s the upload — the operator sees it via ``app/main.py``'s
    # generic ``Exception`` handler + CORS headers, AND via the
    # ``_logger.exception(...)`` below. That preserves the operator
    # feedback channel without trading data integrity for it.

    # We do NOT attempt a partial rollback of the upload because the
    # original commit is irreversible; an inconsistency window where
    # ``category_id is None`` but the transaction row exists is
    # acceptable and recoverable via the manual button.
    auto_categorize_total = 0
    auto_categorized = 0
    auto_categorize_no_match = 0
    if saved_count > 0:
        try:
            just_added_txns = (
                db.query(Transaction)
                .filter(
                    Transaction.import_batch_id == batch.id,
                    Transaction.category_id.is_(None),
                )
                .all()
            )
            auto_categorize_total = len(just_added_txns)
            if auto_categorize_total > 0:
                auto_categorized, auto_categorize_no_match, _conflicts = (
                    categorize_transactions(db, just_added_txns)
                )
                # Phase 30g — transfer detection (pair internal
                # transfers + classify unpaired rows by direction).
                # Scoped to the batch owner so cross-user rows are
                # never touched. Runs AFTER the heuristic passes so
                # Debt/loan rows that matched a keyword rule keep
                # their category and are only LINKED, never
                # re-categorised.
                transfer_result = run_transfer_detection(db, batch.user_id)
                # Recount in-memory: the transfer pass also categorises
                # rows the heuristics left blank (Transfer In/Out,
                # paired Transfer), so ``auto_categorized`` reflects
                # every batch row that now has a category.
                auto_categorized = sum(
                    1 for t in just_added_txns if t.category_id is not None
                )
                if auto_categorized > 0 or transfer_result["pairs"] > 0 or transfer_result["classified"] > 0:
                    db.commit()
                _logger.info(
                    "Import %s: auto-categorized %d/%d just-imported transaction(s) "
                    "(no_match=%d transfers=%s filename=%s batch_id=%d)",
                    batch.filename, auto_categorized, auto_categorize_total,
                    auto_categorize_no_match, transfer_result,
                    batch.filename, batch.id,
                )
        except Exception as _cat_exc:
            # Auto-categorize is best-effort post-commit. The data IS
            # persisted (above) — MUST NOT 500 the upload. A 500 here
            # would trigger a user retry, which would DOUBLE-INSERT
            # every transaction because the first commit is irreversible.
            # The trade-off: silently swallow EVERY categorizer exception,
            # but the full traceback lands in the server log via
            # ``_logger.exception`` so an operator sees the real bug
            # without tricking the user into destroying their own ledger.
            # The FE gets a non-null ``auto_categorize_warning`` field so
            # it can render "Categories couldn't auto-assign — run the
            # button manually" instead of a silent "0 of 505 tagged".
            _logger.exception(
                "Import %s: auto-categorize pass crashed (%s); data "
                "persisted successfully but categories may be NULL. "
                "User can run the Activity page's Auto-categorize button "
                "to recover. Operator: fix the categorizer bug; the "
                "traceback above is the cause.",
                batch.filename, type(_cat_exc).__name__,
            )
            warnings.append(
                f"Auto-categorize temporarily unavailable ({type(_cat_exc).__name__}); "
                f"use the Activity page's Auto-categorize button to retry."
            )
            auto_categorized = 0
            auto_categorize_total = 0
            auto_categorize_no_match = 0

    # Phase 54+ — surface the dedup flag count as a friendly info line.
    # Duplicates are now INSERTED (not skipped) so the user can review
    # them on the Activity page and resolve (keep this / keep original).
    if duplicates_flagged > 0:
        sample = ", ".join(repr(d) for d in flagged_descriptions[:3])
        warnings.append(
            f"{duplicates_flagged} likely-duplicate row(s) imported and flagged "
            f"for review (e.g. {sample}). "
            f"Visit Activity to review and resolve duplicates."
        )

    # Phase 54+ — accuracy fix: all rows are now saved (including
    # duplicates). ``saved_count`` = total raw records, so the check
    # compares saved_count directly against expected_row_count.
    if saved_count < expected_row_count and not any(
        "could not be imported" in w
        or "safely skipped" in w
        or "none matched the transaction patterns" in w
        for w in warnings
    ):
        diff = expected_row_count - saved_count
        warnings.append(
            f"{diff} of {expected_row_count} rows could not be imported "
            f"(malformed dates, amounts, or unparseable fields)."
        )

    return ImportResponse(
        filename=batch.filename,
        file_type=batch.file_type,
        record_count=batch.record_count,
        preview=preview_payload,
        batch_id=batch.id,
        account_id=target_account.id,
        saved_transactions=saved_count,
        expected_row_count=expected_row_count,
        warnings=warnings,
        auto_categorized=auto_categorized,
        auto_categorize_total=auto_categorize_total,
        auto_categorize_no_match=auto_categorize_no_match,
        multi_account_ids=(
            list(account_id_map.values()) if is_multi_account and account_id_map else None
        ),
        # Phase 52 — surface the detected account type so the FE can
        # prompt the user to confirm before import completes.
        # Returns None when the type was defaulted to "checking"
        # without real detection (no filename hint, no column keywords),
        # so the frontend's existing type-prompt UI triggers and asks
        # the user to select the correct type.
        suggested_account_type=(
            pdf_type if is_single_pdf_auto
            else csv_type if is_csv_auto and csv_type_detected
            else target_account.account_type if target_account.account_type != "checking"
            else None
        ),
    )


@router.get("/batches", response_model=List[ImportBatchResponse])
async def list_import_batches(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    local_user = get_or_create_local_user(db, _current_user)
    batches = (
        db.query(ImportBatch)
        .filter(ImportBatch.user_id == local_user.id)
        .order_by(ImportBatch.created_at.desc())
        .all()
    )

    # Phase 11 — JSON-decode the persisted preview blob once at the top
    # of the loop so a bad row (legacy TEXT, no JSON) is caught and
    # surfaced as an empty list (no 500, but the user sees no preview
    # for THAT row — better than crashing the WHOLE batch history).
    results: List[ImportBatchResponse] = []
    # ``json`` import is local to the upload route above; reuse the
    # same module-alias here so a future import refactor doesn't have
    # to chase two import sites.
    import json as _json_decode
    for batch in batches:
        saved_count = (
            db.query(Transaction)
            .filter(Transaction.import_batch_id == batch.id)
            .count()
        )
        # Phase 39 — multi-account batch history. For batches whose
        # transactions span multiple accounts, resolve the distinct
        # account ids so the FE's import-history table can render
        # "2 accounts" rather than just the batch's primary account.
        multi_account_ids: Optional[List[int]] = None
        if saved_count > 0:
            distinct_accts = (
                db.query(Transaction.account_id)
                .filter(Transaction.import_batch_id == batch.id)
                .distinct()
                .all()
            )
            acct_ids = [r[0] for r in distinct_accts]
            if len(acct_ids) > 1:
                multi_account_ids = sorted(acct_ids)
        preview_decoded: Optional[List[Any]] = None
        if batch.preview_lines:
            try:
                preview_decoded = _json_decode.loads(batch.preview_lines)
            except _json_decode.JSONDecodeError:
                # Legacy row / corruption — render as None so the FE
                # falls back to its "no preview available" empty-state
                # without crashing the whole list endpoint.
                preview_decoded = None
        results.append(
            ImportBatchResponse(
                id=batch.id,
                filename=batch.filename,
                file_type=batch.file_type,
                record_count=batch.record_count,
                account_id=batch.account_id,
                saved_transactions=saved_count,
                created_at=batch.created_at,
                processed_at=batch.processed_at,
                preview_lines=preview_decoded,
                multi_account_ids=multi_account_ids,
            )
        )

    return results


@router.get(
    "/batches/{batch_id}/transactions",
    response_model=List[TransactionResponse],
)
async def get_import_batch_transactions(
    batch_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    local_user = get_or_create_local_user(db, _current_user)
    batch = (
        db.query(ImportBatch)
        .filter(ImportBatch.id == batch_id, ImportBatch.user_id == local_user.id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    # Phase 11 — joined-load Account + Category so the FE receives
    # ``TransactionResponse.account_name`` + ``category_name`` flat
    # fields without a follow-up N+1 read. Mirrors the list endpoint
    # so the activity page + the import-history "View" panel share
    # the same shape.
    transactions = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
        )
        .filter(Transaction.import_batch_id == batch.id)
        .order_by(Transaction.transaction_date.desc())
        .all()
    )

    out: List[TransactionResponse] = []
    for t in transactions:
        out.append(
            TransactionResponse(
                id=t.id,
                description=t.description,
                amount=t.amount,
                # Phase 52+ — surface the dual-column bookkeeping
                # values on the import-history "View" panel. Same
                # contract as ``routes/transactions.py``’s list /
                # get / update sites: without these the FE's
                # ``listBatchTransactions`` drilldown renders the
                # Debit / Credit columns as em-dashes for every
                # row even though the underlying Transaction rows
                # already carry the unsigned-positive magnitudes.
                debit=t.debit,
                credit=t.credit,
                transaction_date=t.transaction_date,
                merchant_name=t.merchant_name,
                is_pending=t.is_pending,
                account_id=t.account_id,
                account_name=t.account.account_name if t.account else None,
                account_type=t.account.account_type if t.account else None,
                category_id=t.category_id,
                category_name=t.category.name if t.category else None,
                is_duplicate=t.is_duplicate,
                duplicate_of_id=t.duplicate_of_id,
            )
        )
    return out


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Hard-delete an import batch AND its associated transactions.

    Phase 9: ``no option to delete the imported files, only view, add
    a delete`` — the user wanted a real delete, not a soft-archive.

    Why hard-delete over soft-archive (the pattern goals.py uses):
    ``import_batches`` is an upload-envelope, NOT a domain entity. The
    ledger side of an import is a set of ``Transaction`` rows; if the
    user uploaded the wrong CSV and wants to undo it, the natural
    action is "make it as if this upload never happened". A soft-
    archive table here would just be a row everyone kept forgetting
    about.

    Why we manually delete the transactions FIRST instead of relying
    on an FK cascade: the SQLAlchemy model declares the FK without
    ``ondelete=CASCADE`` (and the alembic initial migration does NOT
    add it at the DB level — checked in ``b0a32894ce60_initial.py``).
    So at the DB level the FK is a plain ``FOREIGN KEY`` with no
    cascade behavior. Deleting the parent batch without first clearing
    the child rows would raise ``ForeignKeyViolation``. The manual
    delete below is explicit (and idempotent — if there are zero
    matching transactions the DELETE is still a no-op).

    The FE surfaces a 2-step inline confirm pattern ("Delete N
    transactions?" / Cancel / Confirm) before calling this endpoint
    so destructive behavior is never accidental.

    Authorization is enforced two ways: (1) JWT via ``require_user``
    and (2) explicit ``ImportBatch.user_id == local_user.id`` filter
    on the lookup so a different user's batch id returns 404 (not 403)
    — mirroring the goals.py + accounts.py pattern of leaking nothing.
    """
    local_user = get_or_create_local_user(db, _current_user)
    batch = (
        db.query(ImportBatch)
        .filter(ImportBatch.id == batch_id, ImportBatch.user_id == local_user.id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    # Explicit cascade: clean up child transactions before dropping the
    # parent batch. No ORM ``ondelete=CASCADE`` and no DB-level cascade
    # (see the docstring), so this is required.
    affected_account_id = batch.account_id
    deleted_txns = (
        db.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .delete(synchronize_session=False)
    )
    db.delete(batch)
    db.flush()

    # Recalculate the affected account's balance from remaining
    # transactions so the stored current_balance stays in sync
    # with the ledger after the cascade delete.
    recalculate_account_balance(db, affected_account_id)
    db.commit()

    # Mirror the FE's confirmation message format so an operator
    # running queries can spot what the user consented to.
    _logger.info(
        "Deleted import batch #%d (filename=%s, cascaded %d transactions)",
        batch_id, batch.filename, deleted_txns,
    )
    return None
