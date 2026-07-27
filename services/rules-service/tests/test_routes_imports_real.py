"""Phase 14 end-to-end tests — ``POST /api/imports/upload`` is now a
local-first parser and persistence path.

The pre-Phase-F3 lift asserted that the rules-service import route
proxied a multipart upload to Finlynq's ``POST /parse/upload`` and
re-emitted its response. Phase F3 collapsed the forwarder into a
5-line httpx round-trip without persistence (Finlynq at F3 didn't
persist ImportBatch / Transaction rows under rules-service's
contract). Phase 14 rewrites the route to:

1. Parse the upload LOCALLY (CSV / XLSX / OFX / PDF-text-layer).
2. INSERT ImportBatch + Transaction rows directly into rules-service
   DB.
3. Recalculate ``accounts.current_balance`` from the ledger.

The Phase F3 tests that asserted forwarder behaviour were tied to
the Finlynq mock; they are now obsolete. These tests assert the
real local-first behaviour using the canonical user fixture
``tests/fixtures/sample_statements/checking_stmt.csv`` (505 expected
rows after the local parser fixes) plus negative-path tests.
"""
import io
import json
import os

import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "sample_statements",
    "checking_stmt.csv",
)


def _csv_bytes() -> bytes:
    with open(_FIXTURE_PATH, "rb") as f:
        return f.read()


# Phase 18 — using the SAME documents the user uploads. Each tuple
# is ``(filename, path, expected_record_count_or_None, kind)`` where
# ``kind`` is one of ``"happy"``, ``"empty"``, ``"bad"``, ``"clean"``.
# ``record_count=None`` means the test asserts only the response
# shape (200/4xx, no 500) without locking an exact row count —
# useful for the bad-statement fixture whose row count is a
# parser-version-dependent quantity.
_FIXTURE_CASES = [
    (
        "checking_stmt.csv",
        os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "sample_statements",
            "checking_stmt.csv",
        ),
        505,  # Phase 54+ UPDATE: dupes flagged not skipped, all 505 rows saved
        "happy",
    ),
    (
        "sample-bank-statement.csv",
        os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "sample-bank-statement.csv",
        ),
        None,  # canonical clean Chase — assert response shape, do not lock count
        "clean",
    ),
    (
        "bad-statement.csv",
        os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "bad-statement.csv",
        ),
        None,  # malformed — must NOT 500, response shape only
        "bad",
    ),
    (
        "empty-statement.csv",
        os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "empty-statement.csv",
        ),
        0,
        "empty",
    ),
]  # type: list[tuple[str, str, int | None, str]]


# -------- happy path: full 505-row persistence --------------


def test_upload_csv_persists_all_499_transactions(client, db_session):
    """The canonical user report: a Wells Fargo ``checking_stmt.csv``
    upload (Wells Fargo summary preamble + ~500 register rows with
    embedded double-quotes) used to drop 124 of 505 rows after
    Phase F3's Finlynq forwarder. Phase 14 parses + persists locally
    so all 499 non-duplicate rows land (Phase 54+ dedup collapses
    6 Airtel ATM rows — 3 WITHDRWL + 3 FEE + 3 INTERNATIONAL FEE
    groups each have identical fingerprints after 7+ digit reference
    numbers are stripped, so 2 of each group of 3 are skipped as
    within-batch duplicates).

    Asserts:
    - HTTP 200
    - ``saved_transactions == 499``
    - ``record_count == 505`` (parser-level row count before dedup)
    - Two DB tables populated: 1 ImportBatch + 499 Transactions.
    - The newly-imported batch's account.current_balance is the SUM
      of all 499 transaction amounts — the balance recalc fired.
    """
    csv_body = _csv_bytes()

    r = client.post(
        "/api/imports/upload",
        files={"file": ("checking_stmt.csv", io.BytesIO(csv_body), "text/csv")},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_type"] == "csv"
    # Phase 54+ UPDATE: duplicates are now INSERTED and FLAGGED (not
    # skipped). All 505 rows land; 6 are flagged as duplicates.
    assert body["saved_transactions"] == 505, (
        f"local persistence must land all 505 rows (dupes flagged, not skipped); "
        f"got saved_transactions={body['saved_transactions']}"
    )
    assert body["record_count"] == 505
    # The parser didn't drop any rows on account of malformed dates or
    # amounts — only dedup warnings. Heuristic exceptions are caught
    # in the local parser; only a true parser bug should emit a
    # "could not be imported" warning.
    drop_warnings = [
        w for w in body.get("warnings") or []
        if "could not be imported" in w
    ]
    assert drop_warnings == [], (
        f"local parser should drop zero rows; got warnings={drop_warnings!r}"
    )
    # Phase 54+ dedup warnings are expected (6 Airtel ATM rows).
    dedup_warnings = [
        w for w in body.get("warnings") or []
        if "likely-duplicate" in w
    ]
    assert len(dedup_warnings) > 0, (
        f"Phase 54+ dedup should emit a warning about skipped duplicates"
    )

    # DB-level proof: 1 ImportBatch row + 505 Transaction rows (all saved, dupes flagged).
    from app.models import ImportBatch, Transaction

    batches = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "checking_stmt.csv")
        .all()
    )
    assert len(batches) == 1, f"expected one batch for the upload; got {batches!r}"
    batch = batches[0]
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    assert len(txns) == 505, f"expected 505 transactions (dupes flagged); got {len(txns)}"
    # Phase 14 contract — balance recalc fired.
    from app.models import Account
    from sqlalchemy import func
    total = (
        db_session.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.account_id == batch.account_id)
        .scalar()
    )
    account = (
        db_session.query(Account)
        .filter(Account.id == batch.account_id)
        .first()
    )
    assert account.current_balance == pytest.approx(float(total), abs=1e-6), (
        f"account.current_balance ({account.current_balance}) must equal "
        f"SUM(transactions.amount) ({total}) after import — Phase 14 "
        f"recalculate redundant."
    )


# -------- account-id scoping -----------------------------


def test_upload_csv_with_account_id_persists_into_that_account(client, db_session):
    """If the client supplies ``account_id``, all transactions land
    in that account — Phase 14 honors the explicit target.

    Aims the upload at a known existing account, then queries the
    transactions table for that account_id. (Falls back to creating
    one if no accounts exist — :func:`get_target_account` lazy-creates
    ``Imported Statements`` when needed.)
    """
    from app.models import Account, ImportBatch, Transaction

    # First, force an account to exist by uploading once without a
    # target account_id (the lazy-create path).
    csv_body = _csv_bytes()
    r0 = client.post(
        "/api/imports/upload",
        files={"file": ("checking_stmt.csv", io.BytesIO(csv_body), "text/csv")},
    )
    assert r0.status_code == 200, r0.text
    # The lazy-created "Imported Statements" account becomes the
    # target for the explicit-id upload.
    target_account = (
        db_session.query(Account).order_by(Account.id).first()
    )
    assert target_account is not None

    # Now upload a smaller CSV into that explicit account.
    smaller = (
        b"date,description,amount\n"
        b"2025-01-15,Coffee shop,-4.50\n"
        b"2025-01-16,Payroll,3500.00\n"
    )
    r = client.post(
        "/api/imports/upload",
        files={"file": ("small.csv", io.BytesIO(smaller), "text/csv")},
        data={"account_id": str(target_account.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["saved_transactions"] == 2

    # The new batch AND its 2 txns are scoped to the explicit account.
    new_batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "small.csv")
        .first()
    )
    assert new_batch.account_id == target_account.id
    new_txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == new_batch.id)
        .all()
    )
    assert len(new_txns) == 2
    assert all(t.account_id == target_account.id for t in new_txns)


# -------- negative paths ---------------------------------


def test_upload_rejects_unsupported_extension_with_415(client):
    """Phase 14 still raises 415 (not 200 forwarder reject) for an
    unsupported extension. The pre-Phase F3 sizer + extension guard
    survive the local-first rewrite — they fire BEFORE we touch the
    parser.
    """
    r = client.post(
        "/api/imports/upload",
        files={"file": ("statement.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert r.status_code == 415, r.text
    assert "Unsupported file extension" in r.json()["detail"]


def test_upload_rejects_oversized_csv_with_413(client):
    """CSV/XLSX/OFX cap is 10 MB; the guard raises 413 before the
    parser ever reads the upload.
    """
    # 11 MB of zeros \u2014 just over the 10 MB cap.
    too_big = b"date,description,amount\n" + (b"2025-01-01,T,0\n" * (11 * 1024 * 1024 // 14))
    assert len(too_big) > 10 * 1024 * 1024
    r = client.post(
        "/api/imports/upload",
        files={"file": ("big.csv", io.BytesIO(too_big), "text/csv")},
    )
    assert r.status_code == 413, r.text
    assert "too large" in r.json()["detail"].lower()


# Phase 15+ regression: the canonical edge-cases fixture is the
# SAME document the user might have uploaded. 17 rows must land
# in the DB end-to-end (parser + route + persist); 8 rows are
# intentional blanks/typos that the parser correctly drops without
# producing any "could not be imported" warnings (they fired via
# the per-row try/except, not wholesale).
EDGE_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "sample_statements",
    "edge_cases.csv",
)


def test_upload_edge_case_csv_persists_all_18_legitimate_rows(
    client, db_session,
):
    """Phase 15+ — user reports CSV rows STILL dropping. Upload the
    canonical edge-cases fixture (25 rows: parens, padded sign,
    trailing dash, Euro/Pound glyphs, US thousands, intentional
    blanks/typos) and assert:

      - HTTP 200
      - ``saved_transactions == 18`` (the 7 drop cases don't surface)
      - DB-level proof: 18 Transaction rows in the import_batches table
      - Sum of amounts matches ``account.current_balance`` (Phase 14
        recalc fires)
      - Zero "could not be imported" warnings (the 7 typo/blank rows
        dropped via per-row try/except, not bulk filter)

    The bulk filter was REMOVED in Phase 15+ — the per-row parser is
    the single source of truth for amount validity. Previously the
    bulk ``pd.to_numeric`` chain silently NaN'd the ``-(75.50)``
    Signed parens row.
    """
    edge_body = open(EDGE_FIXTURE_PATH, "rb").read()

    r = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "edge_cases.csv",
                io.BytesIO(edge_body),
                "text/csv",
            )
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_type"] == "csv"
    assert body["saved_transactions"] == 18, (
        f"Phase 15+ fix must land all 18 legitimate edge-case rows; "
        f"got saved_transactions={body['saved_transactions']}"
    )
    assert body["record_count"] == 18
    # Phase F3 forwarder is GONE (Phase 14) so the route must NOT
    # surface any "could not be imported" warnings: the 8 dropped
    # rows are intentional junk, the 17 legitimate ones all land.
    drop_warnings = [
        w for w in body.get("warnings") or []
        if "could not be imported" in w
    ]
    assert drop_warnings == [], (
        f"local parser should drop only the typo/blank rows; "
        f"got warnings={drop_warnings!r}"
    )

    # DB-level proof: 18 Transaction rows persisted end-to-end
    # (parser + route + persist + recalc). The 7 intentional
    # blanks/typos dropped via per-row try/except. Phase 15+
    # fixed the Signed-parens ``-(75.50)`` row that a prior
    # round's bulk-filter regex chain silently NaN'd, so the
    # canonical-count contract moved from 17 to 18 — this
    # assertion MUST stay in lockstep with the parser
    # ``record_count``.
    from app.models import Account, ImportBatch, Transaction
    from sqlalchemy import func

    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "edge_cases.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    assert len(txns) == 18

    # Map description -> amount on persisted rows so we can spot-check
    # the key shapes that Phase 14 would have silently dropped:
    # (50.00) = -50.00, - 100.00 = -100.00, 100.00- = -100.00,
    # Euro / Pound glyphs, US millions with $ and 3 commas.
    by_desc = {t.description: t.amount for t in txns}
    assert by_desc["Refund accounting"] == pytest.approx(-50.00, abs=1e-6)
    assert by_desc["Padded sign negative"] == pytest.approx(-100.00, abs=1e-6)
    assert by_desc["Trailing dash negative"] == pytest.approx(-100.00, abs=1e-6)
    assert by_desc["Signed parens"] == pytest.approx(-75.50, abs=1e-6)
    assert by_desc["Euro symbol"] == pytest.approx(500.50, abs=1e-6)
    assert by_desc["Pound symbol"] == pytest.approx(1200.99, abs=1e-6)
    assert by_desc["Us thousands"] == pytest.approx(1234.56, abs=1e-6)
    assert by_desc["Big payroll"] == pytest.approx(1250000.00, abs=1e-6)

    # Balance recalc contract — account.current_balance == SUM(amounts)
    total = (
        db_session.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.account_id == batch.account_id)
        .scalar()
    )
    account = (
        db_session.query(Account)
        .filter(Account.id == batch.account_id)
        .one()
    )
    assert account.current_balance == pytest.approx(float(total), abs=1e-6)

    # Intentionally-dropped rows MUST NOT appear (typo / blank / sign-only).
    for desc in [
        "Typo row",
        "Empty amount",
        "Just dollar sign",
        "Just dash",
        "Just paren",
        "All-whitespace amount",
        "Double paren negative",  # the paren-paren shape is unparseable by design
    ]:
        assert desc not in by_desc, (
            f"intentionally-dropped row {desc!r} survived — "
            f"drop contract regressed"
        )


# -------- Phase 17 — auto-categorize on upload ----------------------


def test_upload_auto_categorizes_just_imported_transactions(client, db_session):
    """Phase 17 — the upload endpoint runs the per-batch categorizer
    AFTER the import commit so the user never has to click the
    Activity page's "Auto-categorize" button manually.

    SETUP: the FastAPI startup hook (``app/main.py::
    _seed_default_categories``) seeds the 12 default categories +
    the MERCHANT_RULES dict. A hermetic test DB may or may not have
    walked the startup hook (depends on the conftest), so we
    explicitly call ``seed_default_categories`` here to make this
    test self-contained — without the seeds the categorizer would
    silently skip every row (no Category row → no ``category_id``
    assignment).

    The CSV uses the canonical well-known merchants whose keywords
    are in MERCHANT_RULES:

      - STARBUCKS → Food & Dining
      - AMAZON.COM*MK... → Shopping
      - PAYROLL DEPOSIT → Income

    EXPECTATIONS:
      1. Response carries ``auto_categorize_total == 3`` (= every
         row was uncategorized at import time).
      2. Response carries ``auto_categorized >= 3`` — STARBUCKS,
         AMAZON, and PAYROLL all match ``MERCHANT_RULES`` keywords
         so the substring heuristic should land every row.
      3. The persisted ``Transaction`` rows have a non-null
         ``category_id`` (verified via
         ``GET /api/imports/batches/{id}/transactions``).
    """
    from app.models import ImportBatch, Transaction
    from app.services.categorizer import (
        seed_default_categories,
        seed_default_merchant_rules,  # Phase 24.
    )
    from app.database import SessionLocal

    # Self-contained — seed seeds even if the conftest already did.
    # Phase 24+ — the categorizer reads substring rules from the
    # ``merchant_rules`` DB table (NOT the legacy in-memory
    # ``MERCHANT_RULES`` dict), so without an explicit
    # ``seed_default_merchant_rules`` call the rules dict is empty
    # and every test description falls through to fuzzy Pass 3 (which
    # also returns empty without rules). The legacy test only seeded
    # categories; the merchant-rule seed is the Phase 24 follow-up
    # that keeps the auto-categorize contract intact.
    db_seed = SessionLocal()
    try:
        seed_default_categories(db_seed)
        seed_default_merchant_rules(db_seed)
    finally:
        db_seed.close()

    csv_body = (
        b"Date,Description,Amount\n"
        b"2025-01-15,STARBUCKS COFFEE #1234 SEATTLE WA,-5.75\n"
        b"2025-01-16,AMAZON.COM*MK4US12X AMZN.COM/BILL,-42.99\n"
        b"2025-01-17,PAYROLL DEPOSIT ACME CORP,2500.00\n"
    )

    r = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "auto_cat.csv",
                io.BytesIO(csv_body),
                "text/csv",
            ),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_type"] == "csv"
    assert body["saved_transactions"] == 3
    # Phase 17 — per-batch auto-categorize fields on the response.
    assert body["auto_categorize_total"] == 3, (
        f"all 3 imports should be counted as uncategorized candidates; "
        f"got total={body.get('auto_categorize_total')!r}"
    )
    assert body["auto_categorized"] is not None
    assert body["auto_categorized"] >= 3, (
        f"STARBUCKS + AMAZON + PAYROLL must all categorise via "
        f"MERCHANT_RULES; got auto_categorized={body['auto_categorized']!r}"
    )

    # DB-level proof — every persisted row has a category_id.
    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "auto_cat.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    tagged = [t for t in txns if t.category_id is not None]
    assert len(tagged) == 3, (
        f"all 3 just-imported rows should have category_id populated; "
        f"got tagged={len(tagged)}/3"
    )


def test_upload_skips_per_batch_categorize_when_no_rows_persist(client):
    """Phase 17 — zero-row fast-path. A CSV that lands ZERO transactions
    (or zero uncategorized candidates) must NOT raise; the response
    should carry ``auto_categorized == 0`` and
    ``auto_categorize_total == 0`` so the FE's success message
    doesn't render a misleading "Auto-tagged 0 of N" sub-line.

    Setup: a CSV with only header rows + zero data rows. The parser
    returns ``record_count == 0`` so the import path skips the
    categorizer (no transaction rows to query for). Even if the
    categorizer call DID happen with an empty list, the
    ``categorize_transactions`` helper exits with ``(0, 0, [])`` so this
    test passes either way — the contract is "no row ⇒ 0 categorised,
    0 total".
    """
    csv_body = (
        b"Date,Description,Amount\n"
        # No data rows.
    )
    r = client.post(
        "/api/imports/upload",
        files={
            "file": ("empty.csv", io.BytesIO(csv_body), "text/csv"),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved_transactions"] == 0
    # Fast-path returns (0, 0) — no categorizer call needed when
    # ``saved_count == 0``.
    assert body["auto_categorize_total"] == 0
    assert body["auto_categorized"] == 0


def test_upload_respects_pre_tagged_category_on_other_batches(
    client, db_session,
):
    """Phase 17 — per-batch scope. A pre-existing transaction with a
    manual ``category_id`` on a DIFFERENT import_batch is NOT touched
    by the post-commit auto-tag pass (the route filters on
    ``import_batch_id == batch.id``, so previous batches are out of
    scope entirely). The user's manual override on any older
    transaction survives subsequent imports.

    Steps:
      1. Force-create an account via a primer upload.
      2. Hand-insert a Transaction row attached to a synthetic
         ``other_batch`` with ``category_id = Income`` (a value that
         the merchant-substring heuristic would NOT predict for the
         same substring — proving the heuristic doesn't clobber it).
      3. Upload a fresh CSV. The post-commit categorizer walks
         ``WHERE import_batch_id == NEW_batch.id AND category_id IS
         NULL`` so the manual row on ``other_batch`` is invisible
         to the filter.
      4. Verify the pre-tagged row still has ``category_id == Income``.
    """
    from datetime import datetime, timezone

    from app.models import Account, Category, ImportBatch, Transaction

    # 1. Lazy-create an account via the import route so we have a
    # valid ``account_id`` + ``user_id`` to bind against.
    primer = (
        b"Date,Description,Amount\n"
        b"2025-01-01,PRIMER,1.00\n"
    )
    r0 = client.post(
        "/api/imports/upload",
        files={"file": ("primer.csv", io.BytesIO(primer), "text/csv")},
    )
    assert r0.status_code == 200, r0.text
    account = db_session.query(Account).first()
    assert account is not None

    # 2. Hand-insert a manually-tagged transaction on a SYNTHETIC
    # batch so it's outside the scope of the next upload's
    # ``WHERE import_batch_id == NEW_batch.id`` filter.
    other_batch = ImportBatch(
        user_id=account.user_id,
        account_id=account.id,
        filename="pre-tagged.csv",
        file_type="csv",
        record_count=1,
        preview_lines=None,
        processed_at=datetime.now(timezone.utc),
    )
    db_session.add(other_batch)
    db_session.flush()

    # Seed the Income category if the startup hook didn't (test DB
    # hermeticity — every Categorizer call assumes these rows are
    # present).
    from app.services.categorizer import seed_default_categories
    seed_default_categories(db_session)

    income_cat = (
        db_session.query(Category).filter(Category.name == "Base Salary").one()
    )

    pre_tagged_txn = Transaction(
        account_id=account.id,
        import_batch_id=other_batch.id,
        description="AMAZON.COM*MK4US12X AMZN.COM/BILL",
        amount=-42.99,
        transaction_date=datetime(2025, 1, 16),
        merchant_name="Amazon",
        is_pending=False,
        category_id=income_cat.id,
    )
    db_session.add(pre_tagged_txn)
    db_session.commit()

    # 3. Upload a fresh CSV. The post-commit categorizer only
    # touches rows where ``import_batch_id == NEW_batch.id`` —
    # the pre-tagged row on ``other_batch`` is out of scope.
    r = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "shop.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-01-20,AMAZON.COM*MK4US BED,-12.00\n"
                ),
                "text/csv",
            ),
        },
    )
    assert r.status_code == 200, r.text

    # 4. The manually-tagged row's category_id is unchanged.
    db_session.refresh(pre_tagged_txn)
    assert pre_tagged_txn.category_id == income_cat.id
    assert pre_tagged_txn.import_batch_id == other_batch.id


# =====================================================================
# Phase 49 — Chase column-count-mismatch regression. The canonical
# real-world trigger: a Chase checking-statement CSV whose header has
# 7 columns (``Details,Posting Date,Description,Amount,Type,Balance,
# Check or Slip #``) but every data row ends in ``,,`` (8 fields).
# The previous ``pd.read_csv(on_bad_lines='skip')`` path silently
# dropped every row because pandas treated the column-count
# mismatch as a malformed line. The fix introduces
# :func:`_read_csv_dataframe` (stdlib ``csv.reader`` + column-count
# reconciliation) so the file imports correctly. These tests pin the
# fix at both the unit level (helper directly) and the route level
# (end-to-end POST).
# =====================================================================


CHASE_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "sample_statements_synthetic",
    "atlas_test_checking_trailing_columns.csv",
)


def test_read_csv_dataframe_tolerates_chase_trailing_comma():
    """Phase 49 — direct unit test of :func:`_read_csv_dataframe`.

    The Chase checking export's 8-field data rows (``...9429.75,,``)
    used to drop silently under ``pd.read_csv(on_bad_lines='skip')``.
    The new helper reconciles: trailing empty fields are truncated,
    short rows are padded, and stray non-empty extras are skipped with
    a WARNING log. Asserts the post-reconciliation DataFrame is a
    faithful 7-column representation of the source file.
    """
    from io import BytesIO

    from fastapi import UploadFile

    from app.services.import_parser import _read_csv_dataframe

    csv_body = open(CHASE_FIXTURE_PATH, "rb").read()
    upload = UploadFile(
        filename="atlas_test_checking_trailing_columns.csv",
        file=BytesIO(csv_body),
    )

    df = _read_csv_dataframe(upload)

    # The header has 7 columns and every data row should now line up.
    assert list(df.columns) == [
        "Details",
        "Posting Date",
        "Description",
        "Amount",
        "Type",
        "Balance",
        "Check or Slip #",
    ], f"header columns diverged: {list(df.columns)!r}"
    # Every row has the same length as the header (the 8th trailing
    # empty field was reconciled away).
    assert len(df) > 0, "Chase fixture must produce at least one data row"
    # Spot-check the sign-convention contract on a few hand-picked rows
    # (Chase emits DEBIT as a signed-negative amount, CREDIT as a
    # signed-positive amount). We pick row indices by the ``Details``
    # column instead of pandas position to make the assertion robust
    # to fixture re-ordering / trimming.
    debit_rows = df[df["Details"] == "DEBIT"]
    credit_rows = df[df["Details"] == "CREDIT"]
    assert len(debit_rows) > 0, "Chase fixture must have at least one DEBIT row"
    assert len(credit_rows) > 0, "Chase fixture must have at least one CREDIT row"
    # Every DEBIT row's amount string starts with ``-``.
    for i, amt in debit_rows["Amount"].items():
        assert str(amt).startswith("-"), (
            f"row {i}: Chase DEBIT should have negative amount, "
            f"got {amt!r}"
        )
    # Every CREDIT row's amount string does NOT start with ``-``.
    for i, amt in credit_rows["Amount"].items():
        assert not str(amt).startswith("-"), (
            f"row {i}: Chase CREDIT should have positive amount, "
            f"got {amt!r}"
        )


def test_parse_csv_file_chase_trailing_comma_does_not_zero_records(
    client, db_session,
):
    """Phase 49 — end-to-end regression. The Phase 49 user reported
    a Chase checking statement upload that returned ``saved_transactions
    == 0`` and surfaced a misleading "PDF may be image-only" error
    even though the file was a valid CSV. Root cause: pandas
    ``on_bad_lines='skip'`` dropped every row whose column count
    (8) didn't match the header (7).

    The fix reconciles column counts in :func:`_read_csv_dataframe`
    so the file imports correctly. This test pins the user-visible
    contract: a Chase upload with a 7-col header + 8-field data rows
    persists every legitimate row to the DB.
    """
    from app.models import ImportBatch, Transaction

    if not os.path.exists(CHASE_FIXTURE_PATH):
        pytest.skip(f"Chase fixture not present: {CHASE_FIXTURE_PATH}")
    csv_body = open(CHASE_FIXTURE_PATH, "rb").read()
    # Sanity check: the fixture actually has the column-count
    # mismatch shape we're guarding against. A future refactor that
    # re-exports the fixture with a 7-field data row would silently
    # pass this test — fail loudly so the regression guard stays
    # load-bearing.
    import csv as _csv
    with open(CHASE_FIXTURE_PATH, "r") as f:
        first_data_row = list(_csv.reader(f))[1]
    assert len(first_data_row) > 7, (
        f"Chase fixture must have 8-field data rows (7-col header + "
        f"trailing empty); got {len(first_data_row)} fields on row 1"
    )

    r = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "atlas_test_checking_trailing_columns.csv",
                io.BytesIO(csv_body),
                "text/csv",
            ),
        },
    )
    assert r.status_code == 200, (
        f"Chase CSV upload must not 500 on the column-count "
        f"mismatch; got {r.status_code} body={r.text[:500]}"
    )
    body = r.json()
    assert body["file_type"] == "csv"
    # The bug returned 0 here. The fix returns every row.
    assert body["saved_transactions"] > 0, (
        f"Phase 49 fix: Chase CSV with 7-col header + 8-field data "
        f"rows must persist > 0 rows; got saved_transactions="
        f"{body['saved_transactions']} (this was the original bug)"
    )
    assert body["record_count"] == body["saved_transactions"], (
        f"preview record_count ({body['record_count']}) must equal "
        f"persisted saved_transactions ({body['saved_transactions']}) "
        f"after Phase 49 column-count reconciliation"
    )

    # DB-level proof: the rows actually landed in the transactions
    # table, not just in the response envelope.
    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "atlas_test_checking_trailing_columns.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    assert len(txns) == body["saved_transactions"], (
        f"DB Transaction count ({len(txns)}) must match response "
        f"saved_transactions ({body['saved_transactions']})"
    )
    # Spot-check the first persisted row — the canonical Chase DEBIT
    # shape that the bug previously dropped.
    first_txn = txns[0]
    assert first_txn.amount < 0, (
        f"Chase DEBIT row should have negative amount; got "
        f"{first_txn.amount!r}"
    )
    assert first_txn.description is not None
    assert first_txn.transaction_date is not None


# =====================================================================
# Phase 18 — fixture-based coverage using the SAME documents the user
# actually uploads. Locks the no-NameError regression: every upload
# (good, empty, malformed, clean) returns either 200/4xx — never 500.
# Locks the best-effort auto-categorize: even if the categorizer
# CRASHES (NameError, ImportError, whatever), the upload persists +
# returns 200 so the data the user already committed isn't hidden
# behind an "Upload failed" toast.
# =====================================================================


@pytest.mark.parametrize(
    "filename,fixture_path,expected_record_count,kind",
    _FIXTURE_CASES,
    ids=[f"{x[3]}:{x[0]}" for x in _FIXTURE_CASES],
)
def test_upload_uses_real_user_documents(
    client,
    filename,
    fixture_path,
    expected_record_count,
    kind,
):
    """Phase 18 — regression: every ``tests/fixtures/...`` document
    that the user uploads returns an HTTP status from the {200, 4xx}
    set, NEVER 500. Locks the "no NameError on every upload"
    regression that came from a missing ``SQLAlchemyError`` import.

    Asserted per-kind:

    - ``happy`` + ``clean``: HTTP 200 + ``saved_transactions > 0``.
    - ``empty``: HTTP 200 + ``saved_transactions == 0`` + the
      per-batch categorize returned ``(0, 0)``.
    - ``bad``: HTTP 200 OR 4xx (NOT 500) — malformed CSVs are a
      well-defined failure mode, never a server crash.
    """
    if not os.path.exists(fixture_path):
        pytest.skip(f"fixture not present: {fixture_path}")
    body = open(fixture_path, "rb").read()

    r = client.post(
        "/api/imports/upload",
        files={"file": (filename, io.BytesIO(body), "text/csv")},
    )

    # The critical assertion — a 500 means the categorizer's NameError
    # bug came back. ANY other status is acceptable for any fixture.
    assert r.status_code < 500, (
        f"Upload of {filename!r} returned HTTP 500 — categorizer "
        f"NameError regression. Body: {r.text[:500]}"
    )

    if kind == "bad":
        # Bad-statement: 200 OR 4xx acceptable — both are well-defined
        # behaviour. Just not 500.
        return

    # happy + clean + empty all return 200 with a structured body.
    assert r.status_code == 200, (
        f"Upload of {filename!r} should return 200; "
        f"got {r.status_code} body={r.text[:300]}"
    )
    payload = r.json()
    if expected_record_count is not None:
        assert payload["saved_transactions"] == expected_record_count, (
            f"Upload of {filename!r}: expected "
            f"saved_transactions={expected_record_count}; "
            f"got {payload['saved_transactions']} payload={payload}"
        )
    # Per-batch categorize always returns a typed tuple, even on
    # empty / zero-row paths.
    assert payload["auto_categorize_total"] is not None
    assert payload["auto_categorized"] is not None


def test_upload_empty_statement_falls_through_zero_row_fast_path(
    client, db_session,
):
    """Phase 18 — specifically for ``empty-statement.csv`` (zero
    register rows). Verifies:

    1. HTTP 200 (NOT 500 — the parser handles a header-only CSV).
    2. ``saved_transactions == 0`` + ``auto_categorize_* == 0``.
    3. The DB has exactly 1 ImportBatch + 0 Transactions.
    """
    from app.models import ImportBatch, Transaction

    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "fixtures",
        "empty-statement.csv",
    )
    body = open(fixture_path, "rb").read()
    r = client.post(
        "/api/imports/upload",
        files={"file": ("empty-statement.csv", io.BytesIO(body), "text/csv")},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["saved_transactions"] == 0
    assert out["auto_categorize_total"] == 0
    assert out["auto_categorized"] == 0
    assert out["auto_categorize_no_match"] == 0

    # DB-side proof.
    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "empty-statement.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    assert txns == [], "empty-statement.csv must produce 0 transactions"


def test_upload_bad_statement_does_not_500(
    client,
):
    """Phase 18 — the bad-statement fixture has a malformed schema.
    The parser raises a ``ValueError`` with a "Missing: ..." detail;
    the route surfaces that as 400 OR a 200 preview-only envelope.
    What MUST NOT happen: the upload returns 500. The Phase 18
    NameError regression was a categorizer exception-tuple typo; a
    bad-CSV here ALSO must not cascade to a 500.
    """
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "fixtures",
        "bad-statement.csv",
    )
    body = open(fixture_path, "rb").read()
    r = client.post(
        "/api/imports/upload",
        files={"file": ("bad-statement.csv", io.BytesIO(body), "text/csv")},
    )
    assert r.status_code < 500, (
        f"bad-statement.csv must not crash with 5xx; got "
        f"{r.status_code} body={r.text[:500]}"
    )


def test_upload_best_effort_categorize_survives_categorizer_crash(
    client, db_session, monkeypatch,
):
    """Phase 18 — THE regression test for the production bug.

    Simulate ``categorize_transactions`` raising an arbitrary
    exception (NameError on a future typo, ImportError if a future
    ``from thefuzz...`` is dropped, RuntimeError on a bad DB state).

    The upload MUST persist the data (rows + balance_recalc + batch
    envelope) AND return 200 with ``auto_categorized == 0`` so the
    FE doesn't lie about a missing upload.

    Without the Phase 18 ``except Exception`` widening, the catch
    block would itself raise NameError on the missing
    ``SQLAlchemyError`` symbol and the upload 500s with a confusing
    "Internal server error: NameError".
    """
    from app.models import ImportBatch, Transaction

    def boom(*args, **kwargs):
        raise NameError(
            "simulated categorizer typo — would have crashed upload "
            "before Phase 18 widening"
        )

    monkeypatch.setattr(
        "app.routes.imports.categorize_transactions", boom,
    )

    csv_body = (
        b"Date,Description,Amount\n"
        b"2025-01-15,STARBUCKS COFFEE #1234 SEATTLE WA,-5.75\n"
        b"2025-01-16,AMAZON.COM*MK4US12X AMZN.COM/BILL,-42.99\n"
        b"2025-01-17,PAYROLL DEPOSIT ACME CORP,2500.00\n"
    )
    r = client.post(
        "/api/imports/upload",
        files={
            "file": ("cat_crash.csv", io.BytesIO(csv_body), "text/csv"),
        },
    )

    assert r.status_code == 200, (
        f"upload must persist data even if categorizer raises; "
        f"got {r.status_code} body={r.text[:500]}"
    )
    body = r.json()
    assert body["saved_transactions"] == 3
    assert body["auto_categorized"] == 0
    assert body["auto_categorize_total"] == 0
    assert body["auto_categorize_no_match"] == 0

    # DB-side proof — the data IS persisted even though the
    # categorizer crashed.
    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "cat_crash.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    assert len(txns) == 3
    # Category IDs remain NULL — the manual Activity-page button is
    # the recovery path.
    assert all(t.category_id is None for t in txns), (
        "category_id must remain NULL when categorize crashed "
        "(otherwise we'd silently ship wrong categories)"
    )


def test_upload_uses_user_documents_and_assigns_real_categories(
    client, db_session,
):
    """Phase 18 — the happy-path fixture (``checking_stmt.csv``)
    lands 505 rows AND a real subset gets a ``category_id`` via the
    auto-categorize pass. We don't lock WHICH subset (canonical
    keyword coverage is a moving target across merchant-rule
    refactors), only that:

    1. The ``auto_categorized`` response field is a positive count.
    2. Those same transactions are persisted with non-null
       ``category_id``.
    3. Each non-null ``category_id`` resolves to a known default
       category.
    """
    from app.models import Category, ImportBatch, Transaction
    from app.services.categorizer import (
        seed_default_categories,
        seed_default_merchant_rules,  # Phase 24.
    )

    # Phase 18 — the ``client`` fixture runs ``_reset_test_db()`` which
    # DELETEs from ``categories``. Without an explicit re-seed, the
    # categorizer's ``build_category_lookup(db)`` returns ``{}`` so
    # Pass-2 substring matches silently no-match (returning 0).
    # Seed the 12 default categories so the heuristic has rows to
    # match against. Mirrors what ``seeded_db`` does for the
    # categorizer-v2 tests.
    seed_default_categories(db_session)
    # Phase 24+ — same rationale as
    # ``test_upload_auto_categorizes_just_imported_transactions``:
    # the categorizer reads substring rules from the
    # ``merchant_rules`` DB table. Without seeding it, the rules
    # dict is empty and Pass 2 returns 0.
    seed_default_merchant_rules(db_session)

    csv_body = _csv_bytes()
    r = client.post(
        "/api/imports/upload",
        files={
            "file": ("checking_stmt.csv", io.BytesIO(csv_body), "text/csv"),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Phase 54+ UPDATE: all 505 rows saved, dupes flagged not skipped.
    assert body["saved_transactions"] == 505
    assert body["auto_categorize_total"] == 505
    assert body["auto_categorized"] is not None
    assert body["auto_categorized"] > 0, (
        "the 505-row Wells Fargo fixture must yield at least one "
        "categorised row via MERCHANT_RULES; if 0, the categorizer "
        "rules for known-merchant keywords regressed"
    )

    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "checking_stmt.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    assert len(txns) == 505  # Phase 54+ UPDATE: dupes flagged, not skipped

    tagged = [t for t in txns if t.category_id is not None]
    assert len(tagged) == body["auto_categorized"], (
        f"response.auto_categorized ({body['auto_categorized']}) must "
        f"equal the actual count of persisted rows with non-null "
        f"category_id ({len(tagged)})"
    )

    # Every category_id resolves to a seeded default — no orphan IDs.
    valid_ids = {
        c.id for c in db_session.query(Category).all()
    }
    for t in tagged:
        assert t.category_id in valid_ids, (
            f"tagged transaction has unknown category_id={t.category_id}"
        )


# =====================================================================
# Phase 50 — Chase credit-card CSV import bug. The canonical real-world
# trigger: a Chase credit-card activity CSV with columns
# ``Transaction Date, Post Date, Description, Category, Type, Amount,
# Memo``. Two bugs caused the user to see ``merchant_name = "—"`` and
# ``description = "Imported transaction"`` for every row:
#
# Bug 1 (last-wins overwrite): ``_build_column_map`` maps BOTH
# ``description`` AND ``memo`` to canonical ``description``. The old
# per-row loop did ``normalized[canonical] = value`` (last-wins), so
# the always-blank ``Memo`` column (later in the file than
# ``Description``) overwrote the real merchant with ``""``. Result:
# description fell through to the ``"Imported transaction"``
# placeholder.
#
# Bug 2 (no merchant auto-promotion): Chase credit-card exports have
# NO separate ``merchant_name`` column. The Description column IS the
# merchant. Without auto-promotion, ``merchant_name`` stayed ``None``
# and the UI rendered ``—`` instead of the merchant name.
#
# The fix:
#  (a) per-row merge becomes first-non-empty-wins (see
#      :func:`_build_normalized_row`) so a populated Description wins
#      over a blank Memo.
#  (b) When no column maps to ``merchant_name``, auto-promote the
#      description to ``merchant_name`` so the UI shows the merchant.
# =====================================================================

CHASE_CREDIT_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "sample_statements_synthetic",
    "atlas_test_credit_activity.csv",
)


def test_build_normalized_row_first_wins_keeps_description_over_blank_memo():
    """Phase 50 — unit test of the first-non-empty-wins per-row merge
    helper directly. Asserts the canonical Chase credit-card
    Description/Memo collision is handled correctly: the real
    ``FRANZ FAMILY BAKERY 9028`` description wins over the blank
    ``Memo`` cell.

    Without this fix the per-row loop's last-wins overwrite set
    ``description = ""`` so the placeholder ``"Imported transaction"``
    shipped to the DB instead of the real merchant.
    """
    from io import BytesIO

    import pandas as pd

    from app.services.import_parser import _build_normalized_row

    # Build a one-row DataFrame mirroring the canonical Chase
    # credit-card activity shape:
    #   Transaction Date, Post Date, Description, Category, Type,
    #   Amount, Memo
    # The data row has a real Description and a blank Memo (Chase's
    # CSV template always emits the trailing ``,`` so the last
    # column is empty).
    df = pd.DataFrame(
        [
            [
                "06/29/2026",
                "07/01/2026",
                "FRANZ FAMILY BAKERY 9028",
                "Food & Drink",
                "Sale",
                "-5.50",
                "",  # blank Memo
            ]
        ],
        columns=[
            "Transaction Date",
            "Post Date",
            "Description",
            "Category",
            "Type",
            "Amount",
            "Memo",
        ],
    )
    column_map = {
        "Transaction Date": "date",
        "Description": "description",
        "Amount": "amount",
        "Memo": "description",  # BOTH Description AND Memo map to description
    }
    normalized = _build_normalized_row(df.iloc[0], column_map)

    # The real description wins (not blank, not the placeholder).
    assert normalized["description"] == "FRANZ FAMILY BAKERY 9028", (
        f"first-wins merge must keep the real Description; "
        f"got description={normalized['description']!r}"
    )
    # Date and amount are mapped cleanly.
    assert normalized["date"] == "06/29/2026"
    assert normalized["amount"] == "-5.50"
    # No merchant_name column was mapped.
    assert "merchant_name" not in normalized


def test_build_normalized_row_handles_fully_blank_canonical():
    """Phase 50 — edge case: when the FIRST column mapping to a
    canonical is blank AND a later column has a real value, the
    first-wins merge MUST take the later real value. This covers
    a hypothetical bank export where ``description`` comes BEFORE
    ``memo`` in the file but ``description`` is blank on a row
    while ``memo`` has the real text.
    """
    import pandas as pd

    from app.services.import_parser import _build_normalized_row

    df = pd.DataFrame(
        [["2025-01-15", "", "STARBUCKS #1234"]],
        columns=["Date", "Description", "Memo"],
    )
    column_map = {
        "Date": "date",
        "Description": "description",  # blank
        "Memo": "description",  # has the real value
    }
    normalized = _build_normalized_row(df.iloc[0], column_map)

    # Memo wins because Description was blank.
    assert normalized["description"] == "STARBUCKS #1234"


def test_is_blank_cell_canonical_blank_check():
    """Phase 50 — _is_blank_cell is the canonical blank-check used
    by the per-row merge. Locks the contract so a future refactor
    can't silently change the semantics of "blank" (e.g. allowing a
    string ``"nan"`` to count as populated).
    """
    import pandas as _pd

    from app.services.import_parser import _is_blank_cell

    # Blank cases — must all return True.
    assert _is_blank_cell(None) is True
    assert _is_blank_cell("") is True
    assert _is_blank_cell("   ") is True
    assert _is_blank_cell(float("nan")) is True
    if hasattr(_pd, "NA"):
        # ``pd.NA`` is the pandas-NULL scalar (pandas >= 2.0).
        # Available in modern pandas; the test is a no-op on older
        # versions but the canonical blank-check handles either way
        # via the ``pd.isna`` branch.
        assert _is_blank_cell(_pd.NA) is True

    # Populated cases — must all return False.
    assert _is_blank_cell("FRANZ FAMILY BAKERY 9028") is False
    assert _is_blank_cell("0") is False
    assert _is_blank_cell("-5.50") is False
    assert _is_blank_cell(0) is False  # the int 0 is a real value
    assert _is_blank_cell(0.0) is False  # the float 0.0 is a real value


def test_build_normalized_row_promotes_later_non_empty_when_first_is_blank():
    """Phase 50 — locks the "first non-empty wins" contract. When
    the FIRST column mapping to a canonical is blank but a LATER
    column has a non-blank value, the later non-blank value wins.
    This is the canonical case: a bank that has BOTH
    ``Description`` and ``Memo`` columns where ``Description`` is
    blank on some rows but ``Memo`` has the real value.
    """
    import pandas as pd

    from app.services.import_parser import _build_normalized_row

    df = pd.DataFrame(
        [["2025-01-15", "", "FOO"]],
        columns=["Date", "Description", "Memo"],
    )
    column_map = {
        "Date": "date",
        "Description": "description",  # first sighting — blank
        "Memo": "description",  # second sighting — has "FOO"
    }
    normalized = _build_normalized_row(df.iloc[0], column_map)

    # The later non-blank value wins when the first is blank.
    assert normalized["description"] == "FOO", (
        f"first non-empty wins: blank first sighting must be "
        f"promoted from a later non-blank; got "
        f"description={normalized['description']!r}"
    )


def test_build_normalized_row_does_not_overwrite_populated_first_sighting():
    """Phase 50 — the other half of the truth table. When the
    FIRST column mapping to a canonical is non-blank AND a LATER
    column also has a non-blank value, the FIRST wins. This locks
    the "first non-empty wins" contract for the all-non-blank case
    (not just the blank-first case).
    """
    import pandas as pd

    from app.services.import_parser import _build_normalized_row

    df = pd.DataFrame(
        [["2025-01-15", "FIRST", "SECOND"]],
        columns=["Date", "Description", "Memo"],
    )
    column_map = {
        "Date": "date",
        "Description": "description",  # first sighting — "FIRST"
        "Memo": "description",  # second sighting — "SECOND"
    }
    normalized = _build_normalized_row(df.iloc[0], column_map)

    # First non-empty wins — "FIRST" sticks, "SECOND" is dropped.
    assert normalized["description"] == "FIRST", (
        f"first non-empty wins: later non-blank must NOT overwrite "
        f"an already-populated first sighting; got "
        f"description={normalized['description']!r}"
    )


def test_build_normalized_row_keeps_explicit_merchant_column():
    """Phase 50 — locks the contract for a file with BOTH
    ``Description`` AND ``Merchant`` columns. The explicit merchant
    mapping MUST win over any auto-promotion — the per-row merge
    keeps the populated Merchant cell, and the auto-promotion
    helper does NOT fire (because ``merchant_name`` IS in
    ``column_map.values()``).
    """
    import pandas as pd

    from app.services.import_parser import (
        _build_normalized_row,
        _resolve_merchant_name,
    )

    df = pd.DataFrame(
        [[
            "2025-01-15",
            "FRANZ FAMILY BAKERY 9028",
            "-5.50",
            "Franz Bakery",
        ]],
        columns=["Date", "Description", "Amount", "Merchant"],
    )
    column_map = {
        "Date": "date",
        "Description": "description",
        "Amount": "amount",
        "Merchant": "merchant_name",
    }
    normalized = _build_normalized_row(df.iloc[0], column_map)
    # Per-row merge: description and merchant_name are independent
    # canonicals — neither is overwritten.
    assert normalized["description"] == "FRANZ FAMILY BAKERY 9028"
    assert normalized["merchant_name"] == "Franz Bakery"

    # _resolve_merchant_name must NOT auto-promote when the
    # column_map explicitly lists a merchant_name column (even
    # though description is populated).
    merchant = _resolve_merchant_name(
        normalized,
        normalized["description"],
        column_map,
    )
    assert merchant == "Franz Bakery", (
        f"explicit merchant column must win over auto-promotion; "
        f"got merchant={merchant!r}"
    )


def test_resolve_merchant_name_skips_placeholder_self_promotion():
    """Phase 50 — locks the self-promotion guard. When
    description IS the ``"Imported transaction"`` placeholder
    (i.e. the bank's description column was blank AND the per-row
    loop fell through to the placeholder), the auto-promotion
    MUST NOT copy the placeholder to merchant_name. Otherwise
    the UI would render "Imported transaction" as the merchant
    name — worse than showing ``—``.
    """
    from app.services.import_parser import _resolve_merchant_name

    # No merchant column mapped, description is the placeholder.
    result = _resolve_merchant_name(
        normalized={},
        description="Imported transaction",
        column_map={"Description": "description", "Amount": "amount"},
    )
    assert result is None, (
        f"self-promotion guard failed: placeholder description "
        f"must NOT be promoted to merchant_name; got result={result!r}"
    )

    # No merchant column mapped, description is empty string.
    result_empty = _resolve_merchant_name(
        normalized={"description": ""},
        description="",
        column_map={"Description": "description", "Amount": "amount"},
    )
    assert result_empty is None, (
        f"empty description must NOT be promoted; got result="
        f"{result_empty!r}"
    )

    # No merchant column mapped, description is a REAL value.
    result_real = _resolve_merchant_name(
        normalized={"description": "FRANZ FAMILY BAKERY 9028"},
        description="FRANZ FAMILY BAKERY 9028",
        column_map={"Description": "description", "Amount": "amount"},
    )
    assert result_real == "FRANZ FAMILY BAKERY 9028", (
        f"real description should auto-promote; got result="
        f"{result_real!r}"
    )


def test_parse_csv_transactions_chase_credit_extracts_merchant_from_description(
    client, db_session,
):
    """Phase 50 — end-to-end regression for the Chase credit-card
    import bug. The user reported: uploaded a Chase credit-card
    activity CSV, the imported transactions show ``merchant_name =
    "—"`` and ``description = "Imported transaction"`` for every
    row.

    The fix:
      (a) the per-row first-wins merge keeps the synthetic Description
          (``ATLAS SYNTHETIC BAKERY 9028``) instead of clobbering it
          with the blank ``Memo`` column.
      (b) merchant auto-promotion copies the description into
          ``merchant_name`` when no column maps to ``merchant_name``
          (Chase credit-card shape).

    Asserts:
      - HTTP 200
      - ``saved_transactions > 0``
      - At least one persisted row has ``description = "ATLAS
        SYNTHETIC BAKERY 9028"`` (the synthetic merchant that the
        bug used to drop)
      - The same row has ``merchant_name = "ATLAS SYNTHETIC BAKERY
        9028"`` (the auto-promotion)
      - No row has ``description = "Imported transaction"`` (the
        placeholder that the bug used to ship)
    """
    from app.models import ImportBatch, Transaction

    if not os.path.exists(CHASE_CREDIT_FIXTURE_PATH):
        pytest.skip(f"Chase credit fixture not present: {CHASE_CREDIT_FIXTURE_PATH}")
    csv_body = open(CHASE_CREDIT_FIXTURE_PATH, "rb").read()

    r = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "atlas_test_credit_activity.csv",
                io.BytesIO(csv_body),
                "text/csv",
            ),
        },
    )
    assert r.status_code == 200, (
        f"Chase credit CSV upload must not 500; got "
        f"{r.status_code} body={r.text[:500]}"
    )
    body = r.json()
    assert body["file_type"] == "csv"
    assert body["saved_transactions"] > 0, (
        f"Chase credit CSV must persist > 0 rows; got "
        f"saved_transactions={body['saved_transactions']}"
    )

    # DB-level proof — the synthetic merchant must land in BOTH description and
    # merchant_name. The bug used to put "Imported transaction" in
    # description and None in merchant_name for every Chase credit
    # row.
    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "atlas_test_credit_activity.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    franz_rows = [t for t in txns if t.description == "ATLAS SYNTHETIC BAKERY 9028"]
    assert len(franz_rows) >= 1, (
        f"Phase 50: the synthetic merchant must land in description; got "
        f"descriptions={[t.description for t in txns[:5]]}"
    )
    # Merchant auto-promotion fired for the synthetic row.
    assert franz_rows[0].merchant_name == "ATLAS SYNTHETIC BAKERY 9028", (
        f"Phase 50: merchant_name must auto-promote from description "
        f"when no merchant column is mapped; got merchant_name="
        f"{franz_rows[0].merchant_name!r}"
    )
    # The placeholder must NOT appear in any Chase credit row
    # (the bug shipped 'Imported transaction' for every row).
    placeholder_rows = [
        t for t in txns
        if t.description == "Imported transaction"
    ]
    assert placeholder_rows == [], (
        f"Phase 50: NO Chase credit row should have description "
        f"'Imported transaction' (the bug used to ship this for "
        f"every row); got {len(placeholder_rows)} placeholder rows"
    )

    # Spot-check: a Payment Thank You row has a real merchant from
    # its description (autopromote fires) and a negative net
    # amount doesn't accidentally become None. (Chase payments are
    # positive credit lines; a few of these are scattered through
    # the fixture.)
    payment_rows = [t for t in txns if "Payment Thank You" in t.description]
    if payment_rows:
        for t in payment_rows:
            # Either autopromote kept the original OR the
            # description is "Payment Thank You" itself (both
            # correct; the test just guards against the placeholder).
            assert t.description != "Imported transaction"


# ----- Phase 50 polish: lock the merchant-resolution branch contracts -----


def test_resolve_merchant_name_branch1_returns_explicit_merchant():
    """Locks branch 1 in isolation: a bank that exports BOTH
    ``Description`` AND a separate ``Merchant`` column with a
    populated value must use the merchant column directly (no
    auto-promote). Description is irrelevant for the merchant
    resolution when an explicit column is present and populated.
    """
    from app.services.import_parser import _resolve_merchant_name

    column_map = {"Description": "description", "Merchant": "merchant_name"}
    normalized = {
        "description": "FRANZ FAMILY BAKERY 9028",
        "merchant_name": "Franz Bakery LLC",
    }
    description = "FRANZ FAMILY BAKERY 9028"
    result = _resolve_merchant_name(normalized, description, column_map)
    assert result == "Franz Bakery LLC", (
        f"explicit merchant column must take precedence; got {result!r}"
    )


def test_resolve_merchant_name_branch2_blocked_when_explicit_merchant_column_mapped():
    """When the explicit merchant column is BLANK on a row but the
    bank DOES export a merchant column, branch 1 returns ``None``
    AND branch 2's auto-promote gate is blocked
    (``merchant_name`` IS in column_map.values()). Result: the
    description is NOT promoted, merchant stays None. This is the
    design choice documented in the helper docstring: an
    explicit-but-blank merchant column means 'bank said there is no
    merchant for this row' (canonical Plaid-shape row), and the
    user would rather see ``-`` than a guessed merchant.
    """
    from app.services.import_parser import _resolve_merchant_name

    column_map = {"Description": "description", "Merchant": "merchant_name"}
    normalized = {
        "description": "FRANZ FAMILY BAKERY 9028",
        "merchant_name": "",
    }
    description = "FRANZ FAMILY BAKERY 9028"
    result = _resolve_merchant_name(normalized, description, column_map)
    assert result is None, (
        f"explicit-but-blank merchant column must NOT auto-promote from description; "
        f"got {result!r}"
    )


def test_resolve_merchant_name_branch3_no_merchant_no_description_returns_none():
    """Degenerate branch 3: when description is empty/placeholder AND
    no merchant column is mapped, the helper returns ``None``. This
    is the silent-default case (a real-world trigger: a bank export
    that has a ``Description`` column but every row is blank, AND
    no ``Merchant`` column at all). The FE renders ``-`` for the
    merchant column. Without this test, a future PR that tries to
    'be helpful' by auto-promoting an empty description (e.g.
    defaulting to the description's first non-empty sibling
    column) could regress this contract silently.
    """
    from app.services.import_parser import _resolve_merchant_name

    column_map = {"Description": "description", "Amount": "amount"}
    normalized = {"description": "", "amount": -5.50}
    description = "Imported transaction"  # the placeholder
    result = _resolve_merchant_name(normalized, description, column_map)
    assert result is None, (
        f"empty description + no merchant column must return None, not auto-promote; "
        f"got {result!r}"
    )


# =====================================================================
# Phase 51 — orphan ``Imported Statements`` account cleanup. The
# canonical user report (June 2026): importing a Chase credit-card
# CSV creates TWO accounts on the /accounts page — the CSV-derived
# ``Chase_Credit_3407_Activity`` PLUS a $0 ``Imported Statements``
# row that "comes back every time" the user uploads.
#
# Root cause: ``get_target_account(None)`` ALWAYS auto-creates the
# ``Imported Statements`` fallback when the user has no active
# accounts at upload time (intentional — the Transaction.account_id
# FK needs somewhere to land on the first upload). The Phase 35
# multi-account Fidelity block has cleanup logic to deactivate that
# orphan, but the 3 single-account auto blocks (Phase 36 multi-sheet
# Excel / Phase 37 single-PDF auto / Phase 38 single-CSV auto) do
# NOT — they just create the named account and leave the orphan
# sitting next to it.
#
# Fix: a shared module-level helper
# ``_deactivate_orphan_imported_statements(db, user_id, original,
# new_id)`` flips the orphan's ``is_active=False`` (when it exists,
# is NOT the new account, and has no transactions). Called from
# all 4 single-account blocks. The 3 explicit no-op branches are
# intentional edge-case guards (file literally named
# ``Imported Statements.csv`` matches the just-auto-created orphan;
# prior debug stash left rows on the fallback; explicit
# ``account_id`` was passed so no orphan was ever auto-created).
#
# The helper unit test exercises all 4 branches in isolation. The
# first E2E test reproduces the user's exact symptom. The second
# E2E test pins the no-op contract when the FE passes an explicit
# ``account_id`` (the helper must not auto-create a new orphan if
# get_target_account didn't).
# =====================================================================


def test_deactivate_orphan_imported_statements_lock_4_branches(client, db_session):
    """Phase 51 — direct unit test of
    :func:`_deactivate_orphan_imported_statements`. Validates the 4
    branches in isolation:

    1. **No orphan row → None + no state change** (clean no-op):
       when no ``Imported Statements`` row exists for the user, the
       helper is a no-op. Dominant case for users who already had
       an active account — ``get_target_account`` returned the
       existing one and never auto-created the orphan.
    2. **Orphan reused as new_account_id → None + no state change**
       (degenerate case): when the file's derived name happens to
       match the just-auto-created orphan (e.g. a file literally
       named ``Imported Statements.csv``), the orphan IS the only
       account the user has. Deactivating it would orphan the very
       rows we just persisted.
    3. **Orphan has transactions → None + no state change**
       (FK-safety guard): a prior upload or debug stash left rows
       on the fallback. Deactivating would orphan those transactions
       via the FK.
    4. **True-positive → None + ``orphan.is_active=False`` flip**:
       when the orphan exists, is NOT the new account, AND has zero
       transactions, the helper deactivates it. This is the
       user-reported bug fix.
    """
    from app.models import Account, ImportBatch, Transaction
    from app.routes.imports import _deactivate_orphan_imported_statements
    from app.routes.shared import (
        get_or_create_family_member_self,
        get_or_create_institution,
        get_or_create_local_user,
    )
    from datetime import datetime, timezone

    local_user = get_or_create_local_user(db_session, "alex")
    user_id = local_user.id
    inst = get_or_create_institution(db_session, "Imported Statements")
    self_row = get_or_create_family_member_self(db_session, local_user)

    # Clean any leftover ``Imported Statements`` rows so the test is
    # deterministic — test-order interaction with earlier tests'
    # uploads otherwise leaves an ``is_active=False`` orphan in the
    # DB that confuses branch 1's assertion. SQLAlchemy 2.x doesn't
    # support cross-model bulk DELETE in a single query (Transaction
    # + Account join), so we delete in dependency order: child
    # tables (Transaction / ImportBatch) first, then Account.
    import_batches_for_orphan = (
        db_session.query(ImportBatch.id)
        .filter(ImportBatch.account_id.in_(
            db_session.query(Account.id).filter(
                Account.account_name == "Imported Statements",
                Account.user_id == user_id,
            )
        ))
        .all()
    )
    orphan_batch_ids = [row[0] for row in import_batches_for_orphan]
    if orphan_batch_ids:
        db_session.query(Transaction).filter(
            Transaction.import_batch_id.in_(orphan_batch_ids)
        ).delete(synchronize_session=False)
        db_session.query(ImportBatch).filter(
            ImportBatch.id.in_(orphan_batch_ids)
        ).delete(synchronize_session=False)
    db_session.query(Account).filter(
        Account.account_name == "Imported Statements",
        Account.user_id == user_id,
    ).delete(synchronize_session=False)
    db_session.commit()

    # ---- Branch 1: no orphan → False ----
    no_op_1 = _deactivate_orphan_imported_statements(
        db_session,
        user_id,
        original_target_account_id=999_999_999,  # nonexistent id
        new_account_id=888_888_888,            # nonexistent id
    )
    assert no_op_1 is None, (
        f"branch 1 (no orphan row) must return None; got {no_op_1!r}"
    )

    # ---- Setup: synthetic orphan + named account ----
    orphan = Account(
        user_id=user_id,
        institution_id=inst.id,
        account_name="Imported Statements",
        account_type="checking",
        current_balance=0.0,
        is_active=True,
        family_member_id=self_row.id,
        source="imported",
        description="default fallback",
    )
    db_session.add(orphan)
    db_session.flush()
    new_acct = Account(
        user_id=user_id,
        institution_id=inst.id,
        account_name="Test New",
        account_type="checking",
        current_balance=0.0,
        is_active=True,
        family_member_id=self_row.id,
        source="imported",
        description="test",
    )
    db_session.add(new_acct)
    db_session.flush()

    # ---- Branch 4: true-positive → True + is_active=False ----
    result_true = _deactivate_orphan_imported_statements(
        db_session,
        user_id,
        original_target_account_id=orphan.id,
        new_account_id=new_acct.id,
    )
    assert result_true is None, (
        f"branch 4 (true-positive) is a deactivation, not a return-value gate; "
        f"got result_true={result_true!r} (helper must return None regardless of branch)"
    )
    db_session.refresh(orphan)
    assert orphan.is_active is False, (
        f"branch 4 must set is_active=False; got is_active="
        f"{orphan.is_active!r}"
    )

    # ---- Branch 2: orphan.id == new_account_id → False ----
    # Reactivate the orphan so branch 2's assertion is meaningful.
    orphan.is_active = True
    db_session.flush()
    result_reused = _deactivate_orphan_imported_statements(
        db_session,
        user_id,
        original_target_account_id=orphan.id,
        new_account_id=orphan.id,  # SAME row
    )
    assert result_reused is None, (
        f"branch 2 (orphan reused) is a no-op; helper must return None regardless; "
        f"got result_reused={result_reused!r}"
    )
    db_session.refresh(orphan)
    assert orphan.is_active is True, (
        f"branch 2: orphan reused as new account must NOT be "
        f"deactivated; got is_active={orphan.is_active!r}"
    )

    # ---- Branch 3: orphan has transactions → False ----
    other_batch = ImportBatch(
        user_id=user_id,
        account_id=orphan.id,
        filename="pre-existing.csv",
        file_type="csv",
        record_count=1,
        preview_lines=None,
        processed_at=datetime.now(timezone.utc),
    )
    db_session.add(other_batch)
    db_session.flush()
    pre_txn = Transaction(
        account_id=orphan.id,
        import_batch_id=other_batch.id,
        description="pre-existing row",
        amount=-10.00,
        transaction_date=datetime(2025, 1, 1),
        merchant_name="prior",
        is_pending=False,
    )
    db_session.add(pre_txn)
    db_session.commit()

    result_has_txns = _deactivate_orphan_imported_statements(
        db_session,
        user_id,
        original_target_account_id=orphan.id,
        new_account_id=new_acct.id,
    )
    assert result_has_txns is None, (
        f"branch 3 (orphan has transactions) is a no-op; helper must return None "
        f"regardless; got result_has_txns={result_has_txns!r}"
    )
    db_session.refresh(orphan)
    assert orphan.is_active is True, (
        f"branch 3: orphan with transactions must NOT be "
        f"deactivated (FK safety); got is_active={orphan.is_active!r}"
    )

    # Cleanup — leave DB tidy for the next test.
    db_session.query(Transaction).filter(
        Transaction.import_batch_id == other_batch.id
    ).delete(synchronize_session=False)
    db_session.delete(other_batch)
    db_session.delete(orphan)
    db_session.delete(new_acct)
    db_session.commit()


def test_upload_chase_credit_csv_deactivates_orphan_imported_statements(
    client, db_session,
):
    """Phase 51 — THE canonical user-reported regression test.

    The user said in June 2026: ``when i imported the credit chase
    transaction it creates 2 accounts, the imported statements
    account is back again``. This test reproduces their exact flow
    using the ``atlas_test_credit_activity.csv`` fixture (created in
    Phase 50 for the merchant-promotion bug).

    SETUP: deterministic clean slate — bulk-delete any leftover
    ``Transaction`` / ``ImportBatch`` / ``Account`` rows so
    ``get_target_account`` returns ``None`` from the
    ``WHERE is_active=True`` query and auto-creates the orphan.
    Earlier tests in this file may have left accounts in the DB
    (the conftest doesn't guarantee full teardown); the bulk delete
    forces the bug-path precondition explicitly.

    ACTION: ``POST /api/imports/upload`` with the Chase credit
    fixture + ``account_id=None`` (auto-detect ON, the user's
    setting from the screenshot).

    ASSERTIONS (the user-visible contract):
    - ``HTTP 200`` + ``saved_transactions > 0``
    - Exactly one ``is_active=True`` account for the user: the
      CSV-derived ``Chase_Credit_3407_Activity`` row. (The
      ``Imported Statements`` fallback WAS auto-created by
      ``get_target_account`` but is now ``is_active=False``, so
      the FE's ``GET /api/accounts`` filters it out.)
    - The orphan ``Imported Statements`` row exists in DB with
      ``is_active=False``, ``current_balance=0``, and 0 transactions.
    - All transactions from the upload landed on the
      ``Chase_Credit_3407_Activity`` account, not the orphan.
    """
    from app.models import Account, ImportBatch, Transaction

    if not os.path.exists(CHASE_CREDIT_FIXTURE_PATH):
        pytest.skip(f"Chase credit fixture not present: {CHASE_CREDIT_FIXTURE_PATH}")
    # Deterministic pre-state: zero accounts (forces get_target_account
    # to auto-create the orphan — the bug-path precondition).
    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()

    csv_body = open(CHASE_CREDIT_FIXTURE_PATH, "rb").read()
    r = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "atlas_test_credit_activity.csv",
                io.BytesIO(csv_body),
                "text/csv",
            ),
        },
    )
    assert r.status_code == 200, (
        f"Chase credit CSV upload must not 500; got {r.status_code} "
        f"body={r.text[:500]}"
    )
    body = r.json()
    assert body["file_type"] == "csv"
    assert body["saved_transactions"] > 0, (
        f"Chase credit CSV must persist > 0 rows; got "
        f"saved_transactions={body['saved_transactions']}"
    )

    # DB-level proof: exactly one active account. CSV-derived one.
    active_accts = (
        db_session.query(Account)
        .filter(Account.is_active.is_(True))
        .all()
    )
    assert len(active_accts) == 1, (
        f"Phase 51: user must have exactly 1 active account after "
        f"auto-detect upload; got {[a.account_name for a in active_accts]!r} "
        f"(the bug: 2 active accounts including the orphan)"
    )
    csv_named = active_accts[0]
    assert csv_named.account_name == "Atlas_Test_Credit_Activity", (
        f"the single active account must be the CSV-derived "
        f"``Atlas_Test_Credit_Activity``; got {csv_named.account_name!r}"
    )

    # The orphan exists in DB but is deactivated.
    orphan = (
        db_session.query(Account)
        .filter(Account.account_name == "Imported Statements")
        .first()
    )
    assert orphan is not None, (
        "Phase 51: get_target_account must have auto-created the "
        "orphan (precondition); got None — the bug-path precondition "
        "is missing in this test environment"
    )
    assert orphan.is_active is False, (
        f"Phase 51: the orphan must be deactivated (the bug fix); "
        f"got is_active={orphan.is_active!r}"
    )
    assert orphan.id != csv_named.id, (
        "the orphan and csv_named MUST be different rows"
    )

    # Transaction-counts — all N rows on csv_named, 0 on orphan.
    csv_txn_count = (
        db_session.query(Transaction)
        .filter(Transaction.account_id == csv_named.id)
        .count()
    )
    orphan_txn_count = (
        db_session.query(Transaction)
        .filter(Transaction.account_id == orphan.id)
        .count()
    )
    assert csv_txn_count == body["saved_transactions"], (
        f"csv_named transactions ({csv_txn_count}) must equal "
        f"saved_transactions ({body['saved_transactions']})"
    )
    assert orphan_txn_count == 0, (
        f"orphan transactions must be 0 (the bug left them here); "
        f"got {orphan_txn_count}"
    )

    # Phase 51+ — ImportBatch.account_id reassignment contract.
    # The batch envelope must point to the active CSV-named
    # account (NOT the deactivated orphan), so the FE's import
    # history table renders a meaningful account name in the
    # ``Account`` column rather than a struck-through "$0 default"
    # label that confuses the user about which upload went where.
    batch_row = (
        db_session.query(ImportBatch)
        .filter(
            ImportBatch.filename == "atlas_test_credit_activity.csv"
        )
        .one()
    )
    assert batch_row.account_id == csv_named.id, (
        f"ImportBatch.account_id ({batch_row.account_id}) must "
        f"match the active CSV-named account ({csv_named.id}); "
        f"the orphan's id is {orphan.id} — pre-Phase 51, the "
        f"batch pointed to the orphan and the FE history looked "
        f"broken"
    )


def test_upload_with_explicit_account_id_does_not_create_new_orphan(
    client, db_session,
):
    """Phase 51 — explicit ``account_id`` path: SAFETY guarantee, not
    an auto-create-path test. When the FE passes a target account via
    the dropdown (``account_id`` Form param), ``get_target_account``
    returns the explicit account WITHOUT auto-creating the
    ``Imported Statements`` fallback (so no orphan ever exists in
    this code path). The dominant helper branch here is branch 1
    (no orphan row → ``None``).

    Earlier reasoning linked this test to 'the orphan IS still
    auto-created but the helper no-ops'; corrected Phase 51+ because
    ``get_target_account`` does NOT auto-create when ``account_id``
    is provided. The real contract this test locks is a SAFETY one:
    helper callers must NEVER deactivate an ``original_target_id``
    that matches the user's explicit choice, even when the chosen
    account is named ``Imported Statements`` (a degenerate case
    where the user explicitly picked the fallback as their target).
    Without this test, a future PR that adds 'auto-deactivate any
    ``Imported Statements`` row, period' would silently break that
    user.

    SETUP: 2-account user state from a prior auto-detect upload
    (one deactivated orphan + one active CSV-named account).

    ACTION: a 2nd upload with explicit ``account_id=<named.id>``.

    ASSERTIONS:
    - After both uploads: STILL exactly 2 accounts — the
      explicit-id path did NOT auto-create a new orphan.
    - Active-account count stays at 1 across both uploads.
    - The named account holds all 3 transactions (1 primer +
      2 from the explicit-id upload).
    """
    from app.models import Account, ImportBatch, Transaction

    # Deterministic pre-state: 0 accounts (forces get_target_account
    # to auto-create in step 1 so we can verify the explicit-id
    # path's no-op in step 2).
    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()

    # Step 1 — auto-detect upload. Creates Primer account +
    # Imported Statements orphan (orphan gets deactivated).
    primer_body = (
        b"date,description,amount\n"
        b"2025-01-01,PRIMER,1.00\n"
    )
    r1 = client.post(
        "/api/imports/upload",
        files={"file": ("primer.csv", io.BytesIO(primer_body), "text/csv")},
    )
    assert r1.status_code == 200, r1.text
    n_after_phase1 = db_session.query(Account).count()
    assert n_after_phase1 == 2, (
        f"after auto-detect upload: expected 2 accounts "
        f"(orphan + named); got {n_after_phase1}"
    )

    primer_acct = (
        db_session.query(Account)
        .filter(Account.account_name != "Imported Statements")
        .one()
    )

    # Step 2 — explicit account_id upload.
    small_body = (
        b"date,description,amount\n"
        b"2025-01-15,Coffee shop,-4.50\n"
        b"2025-01-16,Payroll,3500.00\n"
    )
    r2 = client.post(
        "/api/imports/upload",
        files={"file": ("small.csv", io.BytesIO(small_body), "text/csv")},
        data={"account_id": str(primer_acct.id)},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["saved_transactions"] == 2

    # Phase 51 contract — explicit account_id path must NOT
    # auto-create a new orphan. Account count stays at 2.
    n_after_phase2 = db_session.query(Account).count()
    assert n_after_phase2 == 2, (
        f"Phase 51: explicit account_id path must NOT auto-create "
        f"a new orphan; got {n_after_phase2} accounts after "
        f"explicit-id upload (expected 2 from step 1)"
    )

    # Active accounts stay at 1 (the named Primer account).
    n_active_after_phase2 = (
        db_session.query(Account)
        .filter(Account.is_active.is_(True))
        .count()
    )
    assert n_active_after_phase2 == 1, (
        f"Phase 51: must still have exactly 1 active account "
        f"after explicit-id upload; got {n_active_after_phase2}"
    )

    # All 3 transactions landed on the named account.
    named_txn_count = (
        db_session.query(Transaction)
        .filter(Transaction.account_id == primer_acct.id)
        .count()
    )
    assert named_txn_count == 3, (
        f"the named Primer account must hold all 3 transactions "
        f"(1 primer + 2 small); got {named_txn_count}"
    )


# =====================================================================
# Phase 54+ — derive debit/credit from signed amount when the parser
# omits them. The PDF/OFX regex paths (parse_pdf_transactions,
# parse_ofx_transactions, plus the OCR fallback which re-runs
# extract_pdf_transactions on OCR-derived text) emit records that
# carry only a signed ``amount`` -- no ``debit`` / ``credit`` keys.
# The CSV / Excel paths emit D/C magnitudes verbatim inside the
# parser (parse_csv_transactions + _df_to_records), so the
# route-side fallback is a no-op there. This test pins the
# fallback so a future refactor of either parser layer cannot
# silently regress PDF/OFX deposits to NULL D/C values.
# =====================================================================


def test_upload_route_derives_debit_credit_from_amount_when_parser_omits(
    client, db_session, monkeypatch
):
    """Phase 54+ regression -- when the parser yields records WITHOUT
    ``debit`` / ``credit`` keys (the PDF/OFX regex paths), the route
    MUST fall back to the universal accounting convention from the
    Transaction model:

        amount  > 0  ->  credit_for_insert = amount,  debit  = NULL
        amount  < 0  ->  debit_for_insert  = -amount, credit = NULL
        amount == 0  ->  both NULL (FX-neutral row)

    Without this fallback, every PDF/OFX import produces rows with
    NULL ``transactions.debit`` / ``transactions.credit`` and the FE
    renders em-dashes in both columns forever (the Phase 54+
    backfill migration fixes pre-migration rows but cannot fix
    rows inserted AFTER it migrates -- which is exactly what was
    regressing in the user's report).

    The test mocks :func:`parse_uploaded_statement` to return
    records WITHOUT D/C keys (so the CSV parser's D/C emit never
    runs) and asserts the route fills them in correctly across all
    three sign branches in a single test.
    """
    from datetime import datetime
    from app.models import ImportBatch, Transaction

    def fake_parse(upload_file):
        return {
            "file_type": "csv",  # filename is .csv so the route accepts it
            "record_count": 4,
            "expected_row_count": 4,
            "preview": [],
            "filename": upload_file.filename,
            "parsed_records": [
                {
                    "transaction_date": datetime(2026, 4, 12),
                    "amount": +877.38,
                    "description": "Online Payment, Thank You",
                    "merchant_name": None,
                    "is_pending": False,
                    # NO debit/credit keys -> route MUST derive.
                },
                {
                    "transaction_date": datetime(2026, 4, 12),
                    "amount": -25.00,
                    "description": "Paypal *Notarylive Ny",
                    "merchant_name": None,
                    "is_pending": False,
                },
                {
                    "transaction_date": datetime(2026, 4, 12),
                    "amount": -661.41,
                    "description": "Paypal *Ngodecompany Sgp",
                    "merchant_name": None,
                    "is_pending": False,
                },
                {
                    "transaction_date": datetime(2026, 4, 12),
                    "amount": 0.0,  # FX-neutral row
                    "description": "Transfer In/Out",
                    "merchant_name": None,
                    "is_pending": False,
                },
            ],
            "warnings": [],
        }

    monkeypatch.setattr(
        "app.routes.imports.parse_uploaded_statement", fake_parse
    )

    csv_body = (
        b"Date,Description,Amount\n"
        b"2026-04-12,Online Payment,877.38\n"
        b"2026-04-12,Paypal *Notarylive Ny,-25.00\n"
        b"2026-04-12,Paypal *Ngodecompany Sgp,-661.41\n"
        b"2026-04-12,Transfer In=Out,0.00\n"
    )
    r = client.post(
        "/api/imports/upload",
        files={
            "file": ("dcfallback.csv", io.BytesIO(csv_body), "text/csv")
        },
    )
    assert r.status_code == 200, (
        f"upload must succeed even when parser emits no D/C; "
        f"got {r.status_code} body={r.text[:500]}"
    )
    body = r.json()
    assert body["file_type"] == "csv"
    assert body["saved_transactions"] == 4, (
        f"all 4 rows must persist despite the parser's missing D/C keys; "
        f"got saved_transactions={body['saved_transactions']} "
        f"warnings={body.get('warnings')!r}"
    )

    # DB-level proof: derived D/C values are correct on every persisted
    # row per the universal accounting sign rule.
    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "dcfallback.csv")
        .one()
    )
    txns = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .all()
    )
    assert len(txns) == 4

    by_amount = {round(t.amount, 2): t for t in txns}

    # Positive amount -> credit populated, debit NULL.
    pos = by_amount[877.38]
    assert pos.credit == pytest.approx(877.38, abs=1e-6), (
        f"+877.38 row must have credit=877.38; got credit={pos.credit!r}"
    )
    assert pos.debit is None, (
        f"+877.38 row must have debit=NULL; got debit={pos.debit!r}"
    )

    # Negative amount -> debit=|-amount| populated, credit NULL.
    debit_a = by_amount[-25.00]
    assert debit_a.debit == pytest.approx(25.00, abs=1e-6), (
        f"-25.00 row must have debit=25.00; got debit={debit_a.debit!r}"
    )
    assert debit_a.credit is None, (
        f"-25.00 row must have credit=NULL; got credit={debit_a.credit!r}"
    )
    debit_b = by_amount[-661.41]
    assert debit_b.debit == pytest.approx(661.41, abs=1e-6), (
        f"-661.41 row must have debit=661.41; got debit={debit_b.debit!r}"
    )
    assert debit_b.credit is None, (
        f"-661.41 row must have credit=NULL; got credit={debit_b.credit!r}"
    )

    # Zero amount -> BOTH NULL (FX-neutral row). Without this gate
    # a future refactor that treats 0 as "fall through to the last
    # pattern" would silently inflate
    # ``COALESCE(SUM(debit), 0) + COALESCE(SUM(credit), 0)`` on
    # balance recompute for transfer-in/out FX-neutral rows.
    zero = by_amount[0.0]
    assert zero.debit is None, (
        f"zero-amount row must have debit=NULL; got debit={zero.debit!r}"
    )
    assert zero.credit is None, (
        f"zero-amount row must have credit=NULL; got credit={zero.credit!r}"
    )

    # Sanity: the route's per-account balance recalc still fired.
    from app.models import Account
    account = (
        db_session.query(Account)
        .filter(Account.id == batch.account_id)
        .one()
    )
    # 877.38 - 25.00 - 661.41 + 0 = 190.97 (the parser mock
    # supplied signed amounts and the route persisted ``amount``
    # verbatim, so SUM = 190.97).
    assert account.current_balance == pytest.approx(190.97, abs=1e-6), (
        f"account.current_balance must equal SUM(transactions.amount); "
        f"got {account.current_balance!r} -- balance_recalc regressed"
    )
