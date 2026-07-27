"""Phase 4 + Phase 28 route tests — /api/transactions/."""
from datetime import datetime, timezone

import pytest

from app.models import Category, Transaction

pytest_plugins = ["tests.test_routes_auth_helpers"]


def test_list_transactions_empty_returns_empty_list(client):
    """No transactions → empty list with 200."""
    r = client.get("/api/transactions/")
    assert r.status_code == 200
    assert r.json() == []


def test_get_transaction_missing_returns_404(client):
    """GET ``/api/transactions/{nonexistent}`` returns 404 (not 500)."""
    r = client.get("/api/transactions/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Transaction not found"


# ----------------------------------------------------------------------
# Phase 28 — detach (category_id=null) + uncategorized filter
# ----------------------------------------------------------------------


def test_update_transaction_with_null_category_id_detaches(
    client, db_session, make_account, make_transaction
):
    """PUT {category_id: null} clears the row's category.

    Phase 28 user complaint: "i see an option to detach the rule
    but when i click nothing happens." Root cause was the BE
    patch filter ``if v is not None`` silently dropping an
    explicit ``null`` (treating it as "field absent"). Switching
    to ``model_dump(exclude_unset=True)`` preserves explicit
    null so the FE's detach button is no longer a dead click.

    The conftest only bootstraps the schema; categories are NOT
    seeded by default. We create the ``Food & Dining`` row inline
    so this test doesn't depend on ``seed_default_merchant_rules``
    (which would also seed ~117 merchant rules that this test
    doesn't care about).
    """
    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    txn = make_transaction(
        account_id=seed.id,
        description="DETACH-ME",
        merchant_name="DETACH-ME",
    )
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)

    # Manually tag the transaction (simulating a prior pass-1
    # categoriser run) so the detach path is non-trivial.
    food_cat = Category(
        name="Food & Dining",
        description="Detach test category",
    )
    db_session.add(food_cat)
    db_session.commit()
    db_session.refresh(food_cat)
    txn.category_id = food_cat.id
    db_session.commit()
    db_session.refresh(txn)
    assert txn.category_id is not None

    # Detach — FE sends explicit null.
    resp = client.put(
        f"/api/transactions/{txn.id}",
        json={"category_id": None},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["category_id"] is None
    assert body["category_name"] is None

    # The DB row reflects the detach.
    db_session.expire_all()
    refreshed = (
        db_session.query(Transaction).filter_by(id=txn.id).first()
    )
    assert refreshed is not None
    assert refreshed.category_id is None


def test_update_transaction_with_omitted_category_id_preserves_value(
    client, db_session, make_account, make_transaction
):
    """Belt-and-suspenders: omit category_id (no key) keeps the value.

    The ``model_dump(exclude_unset=True)`` switch must NOT
    regress the "field absent → keep current" path. A FE that
    only updates ``merchant_name`` (e.g. a parser-correction
    form) should leave category_id untouched.
    """
    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    food_cat = Category(
        name="Food & Dining",
        description="Omit-keep test category",
    )
    db_session.add(food_cat)
    db_session.commit()
    db_session.refresh(food_cat)
    txn = make_transaction(
        account_id=seed.id,
        description="OMIT-KEEP",
        merchant_name="BEFORE",
    )
    txn.category_id = food_cat.id
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)

    # Update ONLY merchant_name. category_id is absent from the payload.
    resp = client.put(
        f"/api/transactions/{txn.id}",
        json={"merchant_name": "AFTER"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["merchant_name"] == "AFTER"
    # category_id unchanged (still food_cat.id).
    assert body["category_id"] == food_cat.id


def test_list_transactions_uncategorized_filter(
    client, db_session, make_account, make_transaction
):
    """GET /?uncategorized=true returns only category_id IS NULL rows.

    Phase 28 user complaint: "how do i filter for all
    'uncategorized' or 'promote to rule' in activity page."
    The new query param lets the FE's "Untagged" status filter
    pull every untagged row in one round-trip without a
    synthetic "uncategorized" Category row.
    """
    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    food_cat = Category(
        name="Food & Dining",
        description="Uncategorized filter test category",
    )
    db_session.add(food_cat)
    db_session.commit()
    db_session.refresh(food_cat)

    tagged = make_transaction(
        account_id=seed.id,
        description="TAGGED",
    )
    tagged.category_id = food_cat.id
    db_session.add(tagged)
    untagged_a = make_transaction(
        account_id=seed.id,
        description="UNTAGGED-A",
    )
    untagged_b = make_transaction(
        account_id=seed.id,
        description="UNTAGGED-B",
    )
    db_session.add_all([untagged_a, untagged_b])
    db_session.commit()

    # Filter: only untagged.
    resp = client.get("/api/transactions/?uncategorized=true")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    descriptions = {r["description"] for r in rows}
    assert "UNTAGGED-A" in descriptions
    assert "UNTAGGED-B" in descriptions
    assert "TAGGED" not in descriptions
    # Every row's category_id is null.
    assert all(r["category_id"] is None for r in rows)


def test_list_transactions_uncategorized_wins_over_explicit_category(
    client, db_session, make_account, make_transaction
):
    """Phase 28 — ?uncategorized=true and ?category_id=X are mutually exclusive.

    A client sending both gets the ``uncategorized`` semantics
    (it's the more specific filter; AND-ing the two would
    always return zero rows). This test pins the contract.
    """
    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    food_cat = Category(
        name="Food & Dining",
        description="Uncategorized-wins test category",
    )
    db_session.add(food_cat)
    db_session.commit()
    db_session.refresh(food_cat)
    tagged = make_transaction(
        account_id=seed.id,
        description="TAGGED-AGAIN",
    )
    tagged.category_id = food_cat.id
    untagged = make_transaction(
        account_id=seed.id,
        description="UNTAGGED-AGAIN",
    )
    db_session.add_all([tagged, untagged])
    db_session.commit()

    # Both filters set: uncategorized wins.
    resp = client.get(
        f"/api/transactions/?uncategorized=true&category_id={food_cat.id}"
    )
    assert resp.status_code == 200, resp.text
    descriptions = {r["description"] for r in resp.json()}
    assert "UNTAGGED-AGAIN" in descriptions
    assert "TAGGED-AGAIN" not in descriptions


# ----------------------------------------------------------------------
# Phase 52+ — debit/credit wire contract on /api/transactions/
# The ``TransactionResponse`` schema declares ``debit`` and ``credit``
# as Optional[float] = None; without explicit ``debit=t.debit`` /
# ``credit=t.credit`` in the route's manual TransactionResponse(...)
# construction, Pydantic defaults both to None on every response and
# the FE's ``formatBookkeepingCell`` falls through to ``—`` (em-dash)
# for every row — the user-visible bug reported on the screenshot
# where the dual-column Debit/Credit view renders no data. These
# three tests pin the wire contract on ``GET list``, ``GET single``,
# and ``PUT update`` so a future refactor that drops the keys is
# caught loudly.
# ----------------------------------------------------------------------


def test_list_transactions_response_includes_debit_credit_keys(
    client, db_session, make_account, make_transaction
):
    """GET /api/transactions/ — every response row includes the
    ``debit`` and ``credit`` keys (may be None for legacy rows but the
    KEYS themselves are present so the FE's optional chain doesn't
    silently drop to undefined).
    """
    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    # conftest's make_transaction auto-derives debit/credit from
    # amount (amount > 0 → credit, amount < 0 → debit, amount == 0
    # → both NULL). Two seeded rows cover the populated-and-null
    # branches.
    populated = make_transaction(
        account_id=seed.id,
        description="POPULATED-DUAL",
        amount=-10.68,
    )
    zero_amount = make_transaction(
        account_id=seed.id,
        description="ZERO-AMOUNT",
        amount=0.0,
    )
    db_session.add_all([populated, zero_amount])
    db_session.commit()

    resp = client.get("/api/transactions/")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    rows_by_desc = {r["description"]: r for r in rows}
    assert "POPULATED-DUAL" in rows_by_desc
    assert "ZERO-AMOUNT" in rows_by_desc

    pop_row = rows_by_desc["POPULATED-DUAL"]
    # Keys are present on every row, regardless of populated state.
    assert "debit" in pop_row
    assert "credit" in pop_row
    # conftest auto-derivs amount=-10.68 → debit=10.68, credit=None.
    assert pop_row["debit"] == pytest.approx(10.68, abs=1e-6)
    assert pop_row["credit"] is None

    zero_row = rows_by_desc["ZERO-AMOUNT"]
    assert "debit" in zero_row
    assert "credit" in zero_row
    # FX-neutral zero row keeps both sides NULL.
    assert zero_row["debit"] is None
    assert zero_row["credit"] is None


def test_get_transaction_response_includes_debit_credit_keys(
    client, db_session, make_account, make_transaction
):
    """GET /api/transactions/{id} — single-fetch response passes
    debit/credit through (same wire contract as the list endpoint).
    """
    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    txn = make_transaction(
        account_id=seed.id,
        description="SINGLE-DUAL",
        amount=25.0,
    )
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)

    resp = client.get(f"/api/transactions/{txn.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # amount=25 → credit=25, debit=None.
    assert "debit" in body
    assert "credit" in body
    assert body["debit"] is None
    assert body["credit"] == pytest.approx(25.0, abs=1e-6)


def test_update_transaction_response_includes_debit_credit_keys(
    client, db_session, make_account, make_transaction
):
    """PUT /api/transactions/{id} — partial-update response also
    echoes debit/credit back to the caller so a FE that updates
    one field can re-render the bookkeeping columns without a
    follow-up GET.
    """
    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    txn = make_transaction(
        account_id=seed.id,
        description="UPDATE-DUAL",
        amount=-7.78,
    )
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)

    # Update merchant_name (no debit/credit change). Response should
    # still echo debit=7.78, credit=None.
    resp = client.put(
        f"/api/transactions/{txn.id}",
        json={"merchant_name": "CORRECTED"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["merchant_name"] == "CORRECTED"
    assert "debit" in body
    assert "credit" in body
    assert body["debit"] == pytest.approx(7.78, abs=1e-6)
    assert body["credit"] is None


def test_list_import_batch_transactions_includes_debit_credit_keys(
    client, db_session, make_account, make_transaction
):
    """GET /api/imports/batches/{batch_id}/transactions — the
    import-history "View" panel drilldown. Same wire contract as
    the transactions endpoints: every row in the response must
    carry ``debit`` and ``credit`` keys so the FE's
    ``listBatchTransactions`` surface doesn't silently fall back to
    em-dashes on every row of the per-batch transactions view.

    This pins the 4th construction site — reviewer-caught after the
    initial 3-site fix in ``routes/transactions.py`` had already
    shipped. ``routes/imports.py::get_import_batch_transactions``
    had the same manual ``TransactionResponse(...)`` shape but
    wasn't passing ``t.debit`` / ``t.credit``; without this test
    a future refactor that drops the keys from one site and not
    another would 500 only this drilldown surface while leaving
    /activity visibly broken.

    The :class:`ImportBatch` row is constructed inline (no
    ``make_import_batch`` fixture helper exists in conftest and the
    shape is a single insert + commit, so a one-shot fixture is
    heavier than the call site).
    """
    # Import here so the test doesn't pull routes/imports into the
    # collections-time module graph (which would import the optional
    # pytesseract dependency).
    from app.models import ImportBatch

    seed = make_account()
    db_session.add(seed)
    db_session.commit()
    db_session.refresh(seed)
    # ``ImportBatch``'s column set is id, user_id, account_id,
    # filename, file_type, record_count, created_at (server default),
    # processed_at, preview_lines — ``saved_transactions`` is derived
    # in the route via ``COUNT(transactions.import_batch_id == batch.id)``
    # at read time, not persisted on the row. Passing it as a kwarg
    # surfaces as a SQLAlchemy InvalidRequestError on instantiation,
    # which is why an earlier draft of this test failed loudly.
    batch = ImportBatch(
        user_id=seed.user_id,
        account_id=seed.id,
        filename="phase52-batch.csv",
        file_type="csv",
        record_count=2,
        processed_at=datetime.now(timezone.utc),
    )
    db_session.add(batch)
    db_session.commit()
    db_session.refresh(batch)
    seeded_purchase = make_transaction(
        account_id=seed.id,
        import_batch_id=batch.id,
        description="BATCH-PURCHASE",
        amount=-15.50,
    )
    seeded_payment = make_transaction(
        account_id=seed.id,
        import_batch_id=batch.id,
        description="BATCH-PAYMENT",
        amount=200.00,
    )
    db_session.add_all([seeded_purchase, seeded_payment])
    db_session.commit()

    resp = client.get(f"/api/imports/batches/{batch.id}/transactions")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    rows_by_desc = {r["description"]: r for r in rows}
    assert "BATCH-PURCHASE" in rows_by_desc
    assert "BATCH-PAYMENT" in rows_by_desc

    purchase_row = rows_by_desc["BATCH-PURCHASE"]
    # Keys must be present on every row.
    assert "debit" in purchase_row
    assert "credit" in purchase_row
    # amount=-15.50 → conftest auto-derives debit=15.50, credit=None.
    assert purchase_row["debit"] == pytest.approx(15.50, abs=1e-6)
    assert purchase_row["credit"] is None

    payment_row = rows_by_desc["BATCH-PAYMENT"]
    assert "debit" in payment_row
    assert "credit" in payment_row
    # amount=+200.00 → debit=None, credit=200.00.
    assert payment_row["debit"] is None
    assert payment_row["credit"] == pytest.approx(200.00, abs=1e-6)
