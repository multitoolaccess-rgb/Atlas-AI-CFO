"""Phase F5 persistence contract — POST /parse/upload with ``account_id``.

When ``account_id`` is provided (Form field) AND the account belongs to
the authenticated user, the route:

1. Parses the uploaded statement via :func:`parse_uploaded_statement`.
2. Creates an ``ImportBatch`` row (envelope).
3. Persists ``Transaction`` rows for every parsed record.
4. Recalcites ``Account.current_balance`` from settled transactions.
5. Returns :class:`FinlynqParseResponse` with real ``batch_id``,
   ``account_id``, and ``saved_transactions``.

When ``account_id`` is omitted or the account is not found, the route
falls back to parse-only (``batch_id=None``, ``saved_transactions=None``).

Test matrix:
- CSV upload WITH account_id → transactions persisted, balance recalculated
- CSV upload WITHOUT account_id → parse-only, no DB writes
- CSV upload with non-existent account_id → parse-only, no crash
- CSV upload with account belonging to another user → parse-only (user-scoped)
- Balance recalculation: verify current_balance == SUM(transaction.amount)
- ImportBatch metadata: filename, file_type, record_count, processed_at
- Multiple uploads accumulate transactions and update balance
- Response shape: all FinlynqParseResponse fields populated correctly
"""
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from app.models import Account, ImportBatch, Institution, Transaction
from app.routes.shared import get_or_create_local_user


# ---- Fixtures ---------------------------------------------------------------

@pytest.fixture()
def seeded_account(db_session):
    """Seed a User + Institution + Account so the upload route can
    resolve ``account_id`` to a real row owned by the authenticated
    user (``local_user_sub="alex"``).

    Returns ``(account_id, institution_id)`` for assertions.
    """
    # The authenticated user is "alex" (from conftest's issue_token()).
    user = get_or_create_local_user(db_session, "alex")
    institution = Institution(name="Test Bank")
    db_session.add(institution)
    db_session.flush()

    account = Account(
        user_id=user.id,
        institution_id=institution.id,
        account_name="Test Checking",
        account_type="checking",
        current_balance=0.0,
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account.id, institution.id


@pytest.fixture()
def csv_body() -> bytes:
    """A minimal 3-row CSV that the parser can handle."""
    return (
        b"date,description,amount,merchant_name\n"
        b"2025-01-15,Coffee shop,-4.50,Blue Bottle\n"
        b"2025-01-16,Payroll,3500.00,Acme Corp\n"
        b"2025-01-17,Grocery,-87.32,Whole Foods\n"
    )


# ---- Helpers ----------------------------------------------------------------

def _upload_csv(
    client: TestClient,
    csv_body: bytes,
    account_id: Optional[int] = None,
) -> dict:
    """POST /parse/upload with optional ``account_id`` Form field."""
    data = {}
    if account_id is not None:
        data["account_id"] = str(account_id)
    response = client.post(
        "/parse/upload",
        files={"file": ("statement.csv", csv_body, "text/csv")},
        data=data,
    )
    return response


# ---- Tests ------------------------------------------------------------------


class TestParseUploadPersistence:
    """Phase F5: transactions are persisted when account_id is provided."""


    def test_csv_upload_with_account_id_persists_transactions(
        self, client_with_auth, seeded_account, csv_body, db_session,
    ):
        """Uploading a CSV with ``account_id`` creates ImportBatch +
        Transaction rows and returns real IDs.
        """
        account_id, _ = seeded_account
        response = _upload_csv(client_with_auth, csv_body, account_id=account_id)
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["batch_id"] is not None, "batch_id must be set after persistence"
        assert body["account_id"] == account_id
        assert body["saved_transactions"] == 3, (
            f"Expected 3 saved transactions, got {body['saved_transactions']}"
        )

        # Verify DB rows.
        batch = db_session.query(ImportBatch).filter(ImportBatch.id == body["batch_id"]).first()
        assert batch is not None, "ImportBatch row must exist"
        assert batch.filename == "statement.csv"
        assert batch.file_type == "csv"
        assert batch.account_id == account_id
        assert batch.record_count == 3

        txns = (
            db_session.query(Transaction)
            .filter(Transaction.import_batch_id == batch.id)
            .all()
        )
        assert len(txns) == 3, f"Expected 3 Transaction rows, got {len(txns)}"

        amounts = sorted([t.amount for t in txns])
        assert amounts == pytest.approx([-87.32, -4.50, 3500.0])


    def test_balance_recalculated_after_upload(
        self, client_with_auth, seeded_account, csv_body, db_session,
    ):
        """After persisting transactions, ``Account.current_balance``
        must equal the SUM of all settled transaction amounts.
        """
        account_id, _ = seeded_account
        response = _upload_csv(client_with_auth, csv_body, account_id=account_id)
        assert response.status_code == 200

        account = db_session.query(Account).filter(Account.id == account_id).first()
        expected_balance = 3500.0 - 4.50 - 87.32  # 3408.18
        assert account.current_balance == pytest.approx(expected_balance), (
            f"Balance should be {expected_balance}, got {account.current_balance}"
        )


    def test_import_batch_metadata_is_correct(
        self, client_with_auth, seeded_account, csv_body, db_session,
    ):
        """ImportBatch row carries correct filename, file_type,
        record_count, and a non-null processed_at timestamp.
        """
        account_id, _ = seeded_account
        response = _upload_csv(client_with_auth, csv_body, account_id=account_id)
        assert response.status_code == 200
        batch_id = response.json()["batch_id"]

        batch = db_session.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
        assert batch.filename == "statement.csv"
        assert batch.file_type == "csv"
        assert batch.record_count == 3
        assert batch.processed_at is not None, "processed_at must be set"
        assert batch.user_id is not None


    def test_preview_lines_stored_on_batch(
        self, client_with_auth, seeded_account, csv_body, db_session,
    ):
        """ImportBatch.preview_lines must be a JSON-encoded list of
        the first 50 parsed records (for the FE 'View' affordance).
        """
        import json

        account_id, _ = seeded_account
        response = _upload_csv(client_with_auth, csv_body, account_id=account_id)
        assert response.status_code == 200
        batch_id = response.json()["batch_id"]

        batch = db_session.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
        assert batch.preview_lines is not None
        preview = json.loads(batch.preview_lines)
        assert isinstance(preview, list)
        assert len(preview) == 3
        # Each record should have amount and description keys.
        for rec in preview:
            assert "amount" in rec, f"Preview record missing 'amount': {rec}"
            assert "description" in rec, f"Preview record missing 'description': {rec}"


class TestParseOnlyFallback:
    """When account_id is omitted or invalid, the route falls back to
    parse-only (no persistence).
    """


    def test_csv_upload_without_account_id_is_parse_only(
        self, client_with_auth, csv_body,
    ):
        """Without ``account_id``, the response has ``batch_id=None``
        and ``saved_transactions=None`` (backward-compatible
        parse-only mode).
        """
        response = _upload_csv(client_with_auth, csv_body, account_id=None)
        assert response.status_code == 200

        body = response.json()
        assert body["batch_id"] is None, (
            "batch_id must be None when no account_id is provided"
        )
        assert body["saved_transactions"] is None, (
            "saved_transactions must be None in parse-only mode"
        )
        # Parser still works — record_count and preview are populated.
        assert body["record_count"] == 3
        assert len(body["preview"]) >= 1


    def test_csv_upload_with_nonexistent_account_id_is_parse_only(
        self, client_with_auth, csv_body,
    ):
        """When ``account_id`` points to a non-existent account, the
        route logs a warning but does NOT crash — returns parse-only.
        """
        response = _upload_csv(client_with_auth, csv_body, account_id=99999)
        assert response.status_code == 200

        body = response.json()
        assert body["batch_id"] is None
        assert body["saved_transactions"] is None
        assert body["account_id"] == 99999  # echoed back even if not found


    def test_csv_upload_with_other_users_account_is_parse_only(
        self, client_with_auth, seeded_account, csv_body, db_session,
    ):
        """When ``account_id`` belongs to a different user, the
        user-scoped filter returns no match → parse-only.
        """
        # Create a second user's account.
        other_user = get_or_create_local_user(db_session, "other-user")
        institution = db_session.query(Institution).first()
        other_account = Account(
            user_id=other_user.id,
            institution_id=institution.id,
            account_name="Other Account",
            account_type="checking",
            current_balance=0.0,
            is_active=True,
        )
        db_session.add(other_account)
        db_session.commit()
        db_session.refresh(other_account)

        response = _upload_csv(
            client_with_auth, csv_body, account_id=other_account.id,
        )
        assert response.status_code == 200

        body = response.json()
        assert body["batch_id"] is None, (
            "Must not persist to another user's account"
        )
        assert body["saved_transactions"] is None


class TestMultipleUploads:
    """Multiple uploads to the same account accumulate transactions
    and keep the balance in sync.
    """


    def test_second_upload_accumulates_transactions(
        self, client_with_auth, seeded_account, csv_body, db_session,
    ):
        """A second upload to the same account creates a new
        ImportBatch and additional Transaction rows; the balance
        reflects the cumulative sum.
        """
        account_id, _ = seeded_account

        # First upload: 3 transactions, balance = 3408.18
        resp1 = _upload_csv(client_with_auth, csv_body, account_id=account_id)
        assert resp1.status_code == 200
        assert resp1.json()["saved_transactions"] == 3

        # Second upload: same CSV again → 3 more transactions.
        csv_body_2 = (
            b"date,description,amount\n"
            b"2025-02-01,Electricity,-120.00\n"
            b"2025-02-03,Internet,-60.00\n"
        )
        resp2 = _upload_csv(client_with_auth, csv_body_2, account_id=account_id)
        assert resp2.status_code == 200
        assert resp2.json()["saved_transactions"] == 2

        # Two separate batches.
        batches = (
            db_session.query(ImportBatch)
            .filter(ImportBatch.account_id == account_id)
            .all()
        )
        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"

        # 5 total transactions.
        txns = (
            db_session.query(Transaction)
            .filter(Transaction.account_id == account_id)
            .all()
        )
        assert len(txns) == 5, f"Expected 5 transactions, got {len(txns)}"

        # Balance = 3500 - 4.50 - 87.32 - 120 - 60 = 3228.18
        account = db_session.query(Account).filter(Account.id == account_id).first()
        expected = 3500.0 - 4.50 - 87.32 - 120.0 - 60.0
        assert account.current_balance == pytest.approx(expected), (
            f"Cumulative balance should be {expected}, "
            f"got {account.current_balance}"
        )


class TestUploadRequiresAuth:
    """The /parse/upload endpoint now requires authentication
    (Depends(require_user)) for the user-scoped account lookup.
    """


    def test_upload_without_auth_returns_401(self, client, csv_body):
        """Unauthenticated upload must return 401."""
        response = client.post(
            "/parse/upload",
            files={"file": ("statement.csv", csv_body, "text/csv")},
            data={"account_id": "1"},
        )
        assert response.status_code == 401, (
            f"Unauthenticated upload must return 401, got {response.status_code}"
        )


class TestResponseShapeAfterPersistence:
    """The FinlynqParseResponse shape must be preserved after Phase F5
    persistence changes.
    """


    def test_response_has_all_expected_fields(
        self, client_with_auth, seeded_account, csv_body,
    ):
        """After persistence, the response still carries all
        FinlynqParseResponse fields with correct types.
        """
        account_id, _ = seeded_account
        response = _upload_csv(client_with_auth, csv_body, account_id=account_id)
        assert response.status_code == 200

        body = response.json()
        assert isinstance(body["filename"], str)
        assert isinstance(body["file_type"], str)
        assert isinstance(body["record_count"], int)
        assert isinstance(body["preview"], list)
        assert isinstance(body["batch_id"], int)
        assert isinstance(body["account_id"], int)
        assert isinstance(body["saved_transactions"], int)
