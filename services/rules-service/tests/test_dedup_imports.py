"""Phase 54+ regression tests — fingerprint-based dedup on
``POST /api/imports/upload``.

The user's screenshot (June 2026) showed three rows for what was
actually two underlying payments:

  - ``Paypal *Notarylive Ny`` — em-dash Amount, status "Promote to rule"
  - ``PAYPAL *NOTARYLIVE 4029253733 NY 401...`` — debit $25.00
  - ``ONLINE PAYMENT, THANK YOU`` — credit $877.30

Pre-Phase-54, all three were inserted; the Activity page showed
12 rows where the user expected 2. Phase 54+ collapses duplicates by
canonical fingerprint + signed amount (±$0.05) + date (±1 day)
keyed on the same account.

The tests pin:

  - **Fingerprint helper**: UPPERCASE, strip punctuation (.,*#:;()…), strip
    7+ digit blobs (ref IDs), strip trailing ``...`` / ``…`` ellipsis,
    collapse whitespace.
  - **Within-batch dedup**: literal duplicate rows in the same CSV
    insert once, skip the rest.
  - **Cross-batch dedup**: re-importing the same CSV produces zero
    new transactions (idempotency).
  - **±$0.05 tolerance**: a $25.00 row paired with a $25.04 row
    dedup-collates (real-world bank rounding is within 5 cents).
  - **Differentiating ref numbers**: short store / unit numbers
    (4-6 digits) stay distinct so ``"STARBUCKS #1234"`` does NOT
    merge with ``"STARBUCKS #5678"``.

False-positive trade-off documented inline: legitimate two-same-merchant
same-day same-amount rows WILL dedup-collide. Frequency-counting overrides
+ per-row approve/dismiss UI is a future Surface under ``Settings → Clean
up duplicates``. The user explicitly chose the simpler skip-on-hit
contract (vs. frequency-count-with-roundtrips) for this phase.
"""
import io
import os

import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# ============================================================
# Fingerprint helper — direct unit tests
# ============================================================


def test_canonicalize_description_for_dedup_paypal_variants_collapse():
    """The canonical user report. Real-world PayPal export rows from
    the same payment canonicalize identically.

    Real-world Citi CSV export ``"PAYPAL *NOTARYLIVE 4029253733 NY"``
    (full 10-digit PayPal ref + state suffix) and the abbreviated
    PDF export form ``"Paypal *Notarylive Ny"`` (no ref number, no
    state) both fingerprint to ``"PAYPAL NOTARYLIVE NY"`` under the
    Phase 54+ rules: UPPERCASE + strip ``*`` + strip ``,`` + drop the
    10-digit blob (``\\d{7,}``).

    Known limitation (documented in
    :func:`_canonicalize_description_for_dedup`): a TRUNCATED Citi
    export whose PayPal row ends in a short ``3-digit tail`` like
    ``"... NY 401..."`` (the ``"401"`` being a fragment of the
    full ref) WILL leave ``" NY 401"`` in the fingerprint — that
    row does NOT dedup-match the abbreviated variant. The user
    accepted this trade-off in v1 (per-message vs global
    frequency-counting); a future ``Settings → Clean up duplicates``
    affordance can layer a frequency-counting override with
    per-row approve/dismiss.
    """
    from app.routes.imports import _canonicalize_description_for_dedup

    fp_long = _canonicalize_description_for_dedup(
        "PAYPAL *NOTARYLIVE 4029253733 NY"
    )
    fp_short = _canonicalize_description_for_dedup("Paypal *Notarylive Ny")
    assert fp_long == fp_short == "PAYPAL NOTARYLIVE NY", (
        f"PayPal variants with full 10-digit ref must canonicalize "
        f"identically; got long={fp_long!r} short={fp_short!r}"
    )


def test_canonicalize_description_for_dedup_payment_thank_you():
    """``ONLINE PAYMENT, THANK YOU`` and ``ONLINE PAYMENT THANK YOU``
    are the same payment — comma is just a punctuation difference.

    Strip the comma, collapse whitespace.
    """
    from app.routes.imports import _canonicalize_description_for_dedup

    fp_with_comma = _canonicalize_description_for_dedup(
        "ONLINE PAYMENT, THANK YOU"
    )
    fp_clean = _canonicalize_description_for_dedup("ONLINE PAYMENT THANK YOU")
    assert fp_with_comma == fp_clean == "ONLINE PAYMENT THANK YOU", (
        f"comma variants must collapse; got with-comma={fp_with_comma!r} "
        f"clean={fp_clean!r}"
        ""
    )


def test_canonicalize_description_for_dedup_strips_long_ref_ids():
    """Long payment reference IDs (7+ digits) are stripped so a
    CSV+PDF re-import of the same payment collates.

    Auto-pay export shape: ``AUTOMV 9999900000761984AUTOPAY AUTO-PMT``
    (16-digit ref ID concatenated to merchant name).
    """
    from app.routes.imports import _canonicalize_description_for_dedup

    fp = _canonicalize_description_for_dedup(
        "AUTOMV 9999900000761984AUTOPAY AUTO-PMT"
    )
    assert fp == "AUTOMV AUTOPAY AUTO-PMT", (
        f"16-digit ref blob must strip; got {fp!r}"
    )


def test_canonicalize_description_for_dedup_keeps_short_store_numbers():
    """Short (4-6 digit) numbers are PRESERVED so two distinct store
    registers are NOT merged. This locks the false-positive-prevention
    trade-off.

    ``STARBUCKS #1234`` (Seattle register)
    ``STARBUCKS #5678`` (Bellevue register)

    Different stores are conceptually different purchases even if
    same merchant.
    """
    from app.routes.imports import _canonicalize_description_for_dedup

    fp_a = _canonicalize_description_for_dedup("STARBUCKS #1234")
    fp_b = _canonicalize_description_for_dedup("STARBUCKS #5678")
    assert fp_a == "STARBUCKS #1234"
    assert fp_b == "STARBUCKS #5678"
    assert fp_a != fp_b, (
        f"distinct store numbers must NOT merge; got a={fp_a!r} b={fp_b!r}"
    )


def test_canonicalize_description_for_dedup_empty_input_returns_empty():
    """Empty / None input returns empty string so the caller short-circuits
    the dedup (no fingerprint = no dedup; insert unconditionally).
    """
    from app.routes.imports import _canonicalize_description_for_dedup

    assert _canonicalize_description_for_dedup(None) == ""
    assert _canonicalize_description_for_dedup("") == ""
    assert _canonicalize_description_for_dedup("   ") == ""


def test_canonicalize_description_for_dedup_unicode_ellipsis():
    """``...`` ascii ellipsis AND ``…`` unicode ellipsis are stripped.
    Real-world bank exports truncate with both.
    """
    from app.routes.imports import (
        _canonicalize_description_for_dedup,
    )

    fp_ascii = _canonicalize_description_for_dedup(
        "STARBUCKS COFFEE 1234 SEATTLE WA..."
    )
    fp_unicode = _canonicalize_description_for_dedup(
        "STARBUCKS COFFEE 1234 SEATTLE WA…"
    )
    assert fp_ascii == fp_unicode == "STARBUCKS COFFEE 1234 SEATTLE WA"


# ============================================================
# End-to-end dedup via ``POST /api/imports/upload``
# ============================================================


_CITI_PAYPAL_THANK_YOU_CSV = (
    # Properly CSV-quoted — commas inside the description fields would
    # otherwise act as field separators and the rows would parse as
    # 4+ fields (dropped by the column-count reconciler). ``\r\n``
    # matches the ``csv.writer`` default dialect so ``_read_csv_dataframe``
    # produces the canonical 3-row recon output.
    b'Date,Description,Amount\r\n'
    b'2025-04-12,"ONLINE PAYMENT, THANK YOU",877.30\r\n'
    b'2025-04-12,Online Payment Thank You,877.30\r\n'  # within-batch dup
    b'2025-04-12,Paypal *Notarylive Ny,-25.00\r\n'
    # Cross-format dedup target: paypal exported to a SECOND format
    # (CSV with the 10-digit ref) — same payment, different string.
    b'2025-04-12,"PAYPAL *NOTARYLIVE 4029253733 NY",-25.00\r\n'
)


def test_upload_dedups_within_batch(client, db_session):
    """A CSV with two identical rows inserts one, skips one (within-batch
    dedup). The canonical case: the customer export lists a payment
    twice (rare bank-export anomaly).
    """
    from app.models import ImportBatch

    csv_body = (
        b"Date,Description,Amount\n"
        b"2025-04-12,STARBUCKS COFFEE #1234 SEATTLE WA,-5.75\n"
        b"2025-04-12,STARBUCKS COFFEE #1234 SEATTLE WA,-5.75\n"  # exact dup
    )
    r = client.post(
        "/api/imports/upload",
        files={"file": ("within_batch.csv", io.BytesIO(csv_body), "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Phase 54+ UPDATE: duplicates are now INSERTED and FLAGGED (not
    # skipped). Both rows land; one is marked is_duplicate=True.
    assert body["saved_transactions"] == 2, (
        f"both rows should be saved (flagged, not skipped); got "
        f"saved_transactions={body['saved_transactions']}"
    )
    warnings = body.get("warnings") or []
    assert any("duplicate" in w.lower() for w in warnings), (
        f"Phase 54+: the import should surface a duplicate warning; "
        f"got warnings={warnings!r}"
    )

    batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "within_batch.csv")
        .one()
    )
    from app.models import Transaction
    persisted_count = (
        db_session.query(Transaction)
        .filter(Transaction.import_batch_id == batch.id)
        .count()
    )
    assert persisted_count == 2, (
        f"Phase 54+: both rows must be persisted; "
        f"got {persisted_count} Transaction rows"
    )
    # Verify one row is flagged as duplicate.
    dup_count = (
        db_session.query(Transaction)
        .filter(
            Transaction.import_batch_id == batch.id,
            Transaction.is_duplicate.is_(True),
        )
        .count()
    )
    assert dup_count == 1, (
        f"Phase 54+: exactly 1 row should be flagged as duplicate; "
        f"got {dup_count}"
    )


# Helper for the rest of the test module: shared fixture that guarantees
# a clean slate before each test wipes existing accounts/transactions,
# then returns the local user's first active account id.


def _wipe_and_get_or_create_account(db_session, client) -> int:
    """Deterministic pre-state — zero out all accounts + transactions
    so the dedup pre-condition (``no existing rows``) is explicit.
    Returns the FIRST active account id (the one auto-created by the
    first upload).
    """
    from app.models import Account, ImportBatch, Transaction

    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()
    return _first_active_account_id(db_session, client)


def _first_active_account_id(db_session, client) -> int:
    """Upload a single-row CSV so ``get_target_account`` auto-creates
    the user's first account, then return the resolved id.
    """
    r = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "primer.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n2025-01-01,PRIMER,1.00\n"
                ),
                "text/csv",
            ),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return body["account_id"]


def test_upload_dedups_cross_format_reimport(client, db_session):
    """Re-importing the SAME CSV must be idempotent — every row
    skips because a matching row already exists in the DB. The
    cross-batch dedup path catches the dominant real-world bug:
    importing the same Excel + PDF for the same period.
    """
    from app.models import Account, ImportBatch, Transaction

    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()

    # First upload — all 4 rows land. (CSV has TWO within-batch dup
    # pairs so this is really 2 unique payments: $877.30 credit +
    # $25.00 PayPal.)
    r1 = client.post(
        "/api/imports/upload",
        files={
            "file": ("paypal_first.csv", io.BytesIO(_CITI_PAYPAL_THANK_YOU_CSV), "text/csv"),
        },
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    # Phase 54+ UPDATE: all 4 rows are saved (duplicates are flagged,
    # not skipped). 2 are flagged as duplicates.
    assert body1["saved_transactions"] == 4, (
        f"first import should land all 4 rows (dupes flagged, not skipped); "
        f"got saved_transactions={body1['saved_transactions']}"
    )

    # Pull the persisted batch id so we can prove the second upload's
    # ``batch_id`` is a NEW row (the rerun creates a new envelope).
    first_batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "paypal_first.csv")
        .one()
    )
    first_batch_id = first_batch.id

    # Second upload — same CSV, same account. All 4 rows must be
    # flagged as duplicates (cross-batch dedup). We pass the first
    # upload's account_id explicitly so the dedup window queries the
    # same account (dedup is account-scoped).
    r2 = client.post(
        "/api/imports/upload",
        files={
            "file": ("paypal_second.csv", io.BytesIO(_CITI_PAYPAL_THANK_YOU_CSV), "text/csv"),
        },
        data={"account_id": str(body1["account_id"])},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    # Phase 54+ UPDATE: re-import saves all rows (flagged as duplicates,
    # not skipped). 4 rows land, all flagged as duplicates.
    assert body2["saved_transactions"] == 4, (
        f"re-import saves all rows (flagged as dupes); "
        f"got saved_transactions={body2['saved_transactions']}"
    )
    assert any(
        "duplicate" in w.lower() for w in (body2.get("warnings") or [])
    ), (
        f"Phase 54+: re-import must surface a duplicate warning; "
        f"got warnings={body2.get('warnings')!r}"
    )

    # DB-level proof — total rows = 4 (first import) + 4 (second import)
    # = 8. All 4 from the second import are flagged as duplicates.
    total_txns = (
        db_session.query(Transaction).count()
    )
    assert total_txns == 8, (
        f"Phase 54+: re-import inserts all rows (flagged as dupes); "
        f"got total_txns={total_txns} (expected 8)"
    )
    # Filter by second import's batch to verify ALL 4 are flagged.
    second_batch_row = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "paypal_second.csv")
        .one()
    )
    dup_in_second_batch = (
        db_session.query(Transaction)
        .filter(
            Transaction.import_batch_id == second_batch_row.id,
            Transaction.is_duplicate.is_(True),
        )
        .count()
    )
    assert dup_in_second_batch == 4, (
        f"Phase 54+: all 4 rows from the second import should be flagged "
        f"as dupes; got {dup_in_second_batch} duplicate(s)"
    )

    # New ImportBatch envelope WAS created for the second import
    # (the batch id is NOT zero — it represents an "empty" import).
    second_batch = (
        db_session.query(ImportBatch)
        .filter(ImportBatch.filename == "paypal_second.csv")
        .one()
    )
    assert second_batch.id != first_batch_id, (
        "second import should create a separate batch envelope even "
        "when all rows skipped"
    )


def test_dedup_respects_amount_tolerance(client, db_session):
    """±$0.05 amount tolerance: a $25.00 first-upload row matches a a $25.00 first-upload row matches a a $25.00 first-upload row matches a
    $25.04 second-upload row (within tolerance). Real-world bank
    rounding lives in this band.

    Without the tolerance, the two rows would be treated as distinct
    and the dedup would fail. With the tolerance, the second import
    skips cleanly.
    """
    from app.models import Account, ImportBatch, Transaction

    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()

    # First upload: $25.00 PayPal.
    r1 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "twenty_five.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.00\n"
                ),
                "text/csv",
            ),
        },
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["saved_transactions"] == 1

    # Second upload: same description, $25.04 (4 cents off), same
    # account. Pass account_id explicitly so the dedup window queries
    # the same account (dedup is account-scoped).
    first_account_id = r1.json()["account_id"]
    r2 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "twenty_five_rounded.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.04\n"
                ),
                "text/csv",
            ),
        },
        data={"account_id": str(first_account_id)},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    # Phase 54+ UPDATE: the duplicate row is saved and FLAGGED (not
    # skipped). saved_transactions=1 (the flagged duplicate).
    assert body2["saved_transactions"] == 1, (
        f"±$0.05 tolerance must flag -25.00 + -25.04 as duplicate; got "
        f"saved_transactions={body2['saved_transactions']} "
        f"warnings={body2.get('warnings')!r}"
    )
    # Verify the new row is flagged as duplicate.
    from app.models import Transaction as Txn
    flagged = (
        db_session.query(Txn)
        .filter(Txn.is_duplicate.is_(True))
        .count()
    )
    assert flagged == 1, (
        f"the second import row should be flagged as duplicate; "
        f"got {flagged} flagged row(s)"
    )


def test_dedup_amount_outside_tolerance_inserts(client, db_session):
    """The inverse: $25.00 vs $25.10 is 10 cents apart — outside the
    ±$0.05 tolerance window, so the second row IS inserted. The
    dedup must not over-match.
    """
    from app.models import Account, ImportBatch, Transaction

    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()

    r1 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "first_25.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.00\n"
                ),
                "text/csv",
            ),
        },
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["saved_transactions"] == 1

    r2 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "second_25.csv",  # explicit .csv so the parser dispatches
                # to the CSV branch (a .xlsx extension would mistakenly
                # route to pd.read_excel which doesn't accept raw CSV)
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.10\n"
                ),
                "text/csv",
            ),
        },
        # Pass account_id so both uploads target the same account;
        # otherwise the non-generic filenames would create separate
        # accounts and the test would pass for the wrong reason.
        data={"account_id": str(r1.json()["account_id"])},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    # 10 cents apart → OUTSIDE ±$0.05 tolerance → second row inserts.
    assert body2["saved_transactions"] == 1, (
        f"$0.10 difference must NOT dedup (outside ±$0.05); got "
        f"saved_transactions={body2['saved_transactions']}"
    )
    total = db_session.query(Transaction).count()
    assert total == 2, f"expected 2 total transactions; got {total}"


def test_dedup_account_scoped_does_not_collapse_across_accounts(
    client, db_session,
):
    """Dedup is keyed on account_id. Two rows with identical fingerprint
    but on DIFFERENT accounts must NOT collapse. Cross-account
    dedup would silently hide real money movement from one account
    to another.
    """
    from app.models import Account, ImportBatch, Transaction

    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()

    # Step 1 — auto-create an account A via auto-detect upload.
    r1 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "account_a.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.00\n"
                ),
                "text/csv",
            ),
        },
    )
    assert r1.status_code == 200, r1.text
    account_a_id = r1.json()["account_id"]    # Step 2 — explicitly target a manually-named account B (different
    # from A) and upload the SAME row. No cross-account dedup.
    # Insert Account B directly via the ORM (bypassing the POST
    # ``/api/accounts`` route) — three reasons:
    #   1) The POST route's trailing-slash 307 redirect can drop the
    #      body in the TestClient (varies by httpx/requests version),
    #      landing a 422 with no helpful detail.
    #   2) Account B must share ``user_id`` with Account A so a future
    #      cross-account listing would surface both rows — mirroring
    #      ``account_a`` via its ORM relationship is the cleanest way.
    #   3) This test is about dedup scoping, not account creation,
    #      so the contract being verified is the db-state shape, not
    #      the route's status code.
    account_a = db_session.get(Account, account_a_id)
    new_b = Account(
        user_id=account_a.user_id,
        institution_id=account_a.institution_id,
        family_member_id=account_a.family_member_id,
        account_name="Manual Account B",
        account_type="checking",
        current_balance=0.0,
        is_active=True,
        source="manual",
    )
    db_session.add(new_b)
    db_session.commit()
    db_session.refresh(new_b)
    account_b_id = new_b.id

    r2 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "account_b.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.00\n"
                ),
                "text/csv",
            ),
        },
        data={"account_id": str(account_b_id)},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    # Cross-account dedup MUST NOT fire — these are DIFFERENT accounts.
    assert body2["saved_transactions"] == 1, (
        f"same fingerprint on different accounts must NOT dedup; got "
        f"saved_transactions={body2['saved_transactions']}"
    )
    assert body2["account_id"] == account_b_id
    # DB proof — 2 transactions, one per account.
    total = db_session.query(Transaction).count()
    assert total == 2, (
        f"cross-account dedup regression: {total} transactions "
        f"(expected 2 — one per account)"
    )


def test_dedup_warning_message_surfaces_flagged_count(client, db_session):
    """The dedup warning message includes the flagged count + a sample
    of descriptions so the user can verify what was flagged.
    """
    from app.models import Account, ImportBatch, Transaction

    db_session.query(Transaction).delete(synchronize_session=False)
    db_session.query(ImportBatch).delete(synchronize_session=False)
    db_session.query(Account).delete(synchronize_session=False)
    db_session.commit()

    # First upload: 1 row.
    r1 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "lonely.csv",
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.00\n"
                ),
                "text/csv",
            ),
        },
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    # First-import warning list should NOT include a dedup line.
    dedup_warn_1 = [
        w for w in (body1.get("warnings") or []) if "duplicate" in w.lower()
    ]
    assert dedup_warn_1 == [], (
        f"first import (no prior row) must not surface a dedup warning; "
        f"got {dedup_warn_1!r}"
    )

    # Second import: same row → must dedup-warn.
    r2 = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "lonely.csv",  # filename reused → deterministic order
                io.BytesIO(
                    b"Date,Description,Amount\n"
                    b"2025-04-12,Paypal *Notarylive Ny,-25.00\n"
                ),
                "text/csv",
            ),
        },
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()  # was ``r.json()`` — that parsed r1's body
    # (the *first* upload, which had no prior rows so no dedup warning).
    # Using r2 here so the assertion below validates the SECOND upload's
    # dedup_warning shape, which is the contract under test.
    dedup_warn_2 = [
        w for w in (body2.get("warnings") or []) if "duplicate" in w.lower()
    ]
    assert len(dedup_warn_2) == 1, (
        f"second import must surface exactly one dedup warning; "
        f"got {dedup_warn_2!r}"
    )
    msg = dedup_warn_2[0]
    assert "1" in msg or "one" in msg.lower(), (
        f"warning must mention the flagged count; got {msg!r}"
    )
    assert "Paypal" in msg or "Notarylive" in msg, (
        f"warning must include a sample description; got {msg!r}"
    )
