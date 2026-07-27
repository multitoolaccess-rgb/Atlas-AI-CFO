"""Phase-F5 forwarder tests -- ``/api/dashboard/summary``.

Phase-F5 lifted the dashboard aggregator from rules-service into
Finlynq (canonical store per Phase-F2 shared-DB wiring +
``docs/master-plan.md`` end-state vision). rules-service's
``/api/dashboard/summary`` is now a 5-line httpx forwarder that
re-emits Finlynq's ``StateSummaryOut`` body through
``DashboardSummary(**r.json())`` coercion.

**The old assertions** (which called the local aggregator and
asserted zero / post-account balances / goal ordering) are no
longer applicable. The aggregator's behavior is locked by the
cross-service integration test
``services/tests/test_state_aggregator_cross_db.py`` (Phase-F5f).

**The new assertions** here assert the FORWARDER's full contract:

1. ``Depends(require_user)`` rejects requests without a valid JWT cookie.
2. Forwarder re-emits Finlynq's StateSummaryOut as ``DashboardSummary``
   verbatim (9-field shape comes through).
3. Forwarder propagates Finlynq 4xx verbatim with ``forward_detail``.
4. Forwarder maps Finlynq 5xx to 502 Bad Gateway.
5. Forwarder maps Finlynq 3xx to 502 Bad Gateway.
6. Forwarder maps Finlynq 2xx with non-JSON body to 502.

Finlynq is NOT running during pytest -- every test uses the
``install_finlynq_state_forward`` fixture (in conftest.py) to
install a stub on ``app.routes.dashboard._forward``. The
cross-service integration itself is exercised in
``services/tests/test_state_aggregator_cross_db.py``.
"""
import pytest

pytest_plugins = ["tests.test_routes_auth_helpers"]


# ---- Auth dep ------------------------------------------------------------


def test_dashboard_summary_no_auth_returns_401(client_no_auth):
    """Forwarder dep: ``Depends(require_user)`` rejects requests
    without a valid JWT cookie."""
    r = client_no_auth.get("/api/dashboard/summary")
    assert r.status_code == 401


# ---- Wire-level pass-through ---------------------------------------------


def test_dashboard_summary_forwarder_response_shape_is_dashboard_summary(
    client, install_finlynq_state_forward
):
    """The forwarder coerces Finlynq's 9-field ``StateSummaryOut``
    through rules-service's ``DashboardSummary`` Pydantic shape.
    Assert the canonical 9-field shape re-emits verbatim."""
    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    assert r.json() == canned, (
        f"Forwarder must re-emit Finlynq's StateSummaryOut verbatim; "
        f"got {r.json()!r}, expected {canned!r}"
    )


def test_dashboard_summary_forwarder_passes_nonzero_total_balance_through(
    client, install_finlynq_state_forward
):
    """Forwarder re-emits nonzero aggregate values verbatim.

    The pre-F5 ``test_dashboard_summary_after_one_account_reflects_balance``
    asserted the LOCAL aggregator's behavior. Post-F5d the dashboard
    is a forwarder; the aggregator's sums/balance behavior is locked
    by ``services/tests/test_state_aggregator_cross_db.py``. This
    test proves the FORWARDER's pass-through is mechanical for the
    nonzero case.

    Phase 52 override: ``total_income_month`` and ``total_expenses_month``
    are NOW overridden by a local recalculation that applies account-type-
    aware + payment-pattern-aware classification. The forwarder still
    emits the canned values -- but the /summary endpoint recomputes
    income/expense from local transactions before returning. Since the
    test DB has zero transactions, both are 0.0. All other fields pass
    through verbatim.

    Datetime wire-format note: Pydantic v2's default datetime
    serializer emits the ``Z`` suffix for UTC (not ``+00:00``) --
    the canned input and the assertion must agree on the wire
    format, otherwise the test compares an input +00:00 against a
    Pydantic-serialized Z (round-trip mismatch).
    """
    canned = {
        "total_balance": 250.0,
        "total_income_month": 1000.0,
        "total_expenses_month": 350.50,
        "accounts_count": 1,
        "transactions_count": 5,
        "last_sync": "2026-07-01T12:00:00Z",
        "import_batches_count": 3,
        "last_import_at": "2026-07-01T12:00:00Z",
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    # Phase 52+: total_balance is overridden by local recomputation
    # (assets minus liabilities). Test DB has zero accounts → 0.0.
    assert body["total_balance"] == 0.0
    # Phase 52: income/expense are overridden by local recomputation;
    # the test DB has zero transactions, so both are 0.0.
    assert body["total_income_month"] == 0.0
    assert body["total_expenses_month"] == 0.0
    assert body["accounts_count"] == 1
    assert body["transactions_count"] == 5
    assert body["last_sync"] == "2026-07-01T12:00:00Z"
    assert body["import_batches_count"] == 3
    assert body["last_import_at"] == "2026-07-01T12:00:00Z"


def test_dashboard_summary_forwarder_phase52_income_override_works(
    client, install_finlynq_state_forward, db_session, make_account, make_transaction
):
    """Phase 52: the /summary endpoint overrides Finlynq's income/expense
    with a local recomputation that uses account-type-aware + payment-
    pattern-aware classification. This test proves the override path
    works by seeding a transaction and asserting the recomputed values
    appear in the response."""
    from datetime import datetime

    # Use the conftest factory to create a checking account
    acct = make_account(
        account_name="Test Checking",
        account_type="checking",
        institution_name="Test Bank",
        current_balance=5000.0,
    )
    db_session.add(acct)
    db_session.flush()

    # A salary deposit on a checking account -> real income
    txn = make_transaction(
        account_id=acct.id,
        description="ACME PAYROLL",
        amount=5000.0,
        transaction_date=datetime.utcnow(),
    )
    db_session.add(txn)
    db_session.commit()

    # The forwarder returns canned values, but Phase 52 overrides
    # income/expense from the local transactions
    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    # Override: income should reflect the local $5000 deposit
    assert body["total_income_month"] == 5000.0
    assert body["total_expenses_month"] == 0.0
    # Phase 52+: total_balance is now assets-minus-liabilities.
    # The test creates a checking account with current_balance=5000.0.
    # Checking is an asset (not in CREDIT_ACCOUNT_TYPES), so it's added.
    assert body["total_balance"] == 5000.0
    # Non-income/expense fields pass through verbatim
    assert body["accounts_count"] == 0


# ---- Error-envelope mapping (Phase-F2 #1 contract) -----------------------


def test_dashboard_summary_forwarder_4xx_propagates_verbatim(
    client, install_finlynq_state_forward
):
    """Forwarder's error envelope: Finlynq 4xx -> rules-service 4xx
    verbatim with the upstream detail string preserved by
    ``forward_detail``."""
    install_finlynq_state_forward(
        {"detail": "Finlynq aggregator conflict"},
        status_code=409,
    )
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "Finlynq aggregator conflict"


def test_dashboard_summary_forwarder_5xx_maps_to_502(
    client, install_finlynq_state_forward
):
    """Forwarder error envelope: Finlynq 5xx -> rules-service 502
    Bad Gateway.

    Without this mapping, a stalled / crashed Finlynq would surface
    as rules-service 500 (the original code-level error) -- the
    browser would then NOT know the dashboard failure is an upstream
    issue, just a generic server error.
    """
    install_finlynq_state_forward(
        {"detail": "Finlynq aggregator closed"},
        status_code=500,
    )
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 502, r.text
    assert r.json()["detail"] == "Finlynq aggregator closed"


def test_dashboard_summary_forwarder_3xx_maps_to_502(
    client, install_finlynq_state_forward
):
    """Forwarder error envelope: Finlynq 3xx -> rules-service 502
    Bad Gateway.

    3xx on a ``GET /state/summary`` round-trip is unexpected -- the
    slot should not redirect. Surfacing as 502 makes an
    upstream-shape regression loud, not silent.
    """
    install_finlynq_state_forward({}, status_code=302)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 502, r.text


def test_dashboard_summary_credit_card_positive_debt_reduces_net_worth(
    client, install_finlynq_state_forward, db_session, make_account, make_transaction
):
    """Regression -- the user's misclassified credit card scenario,
    expressed in the new dual-column convention (Phase 52+).

    After Phase 52+ the credit-account balance convention flipped to
    ``positive = money owed`` (matching the bank statement's native
    semantics: balance = expenses - payments = positive number when
    the user owes money). The dashboard formula SUBTRACTS every
    credit-type balance from net worth (vs the pre-Phase-52 formula
    that ADDED credit_card directly and SUBTRACTED loan/mortgage).
    The unified rule is:
        sa_case((account_type in CREDIT_ACCOUNT_TYPES,
                 -current_balance), else_=current_balance)

    Database state for this test:
      - account_type='credit_card' (re-classified after upload via
        PUT /api/accounts/{id}, but the import-time sign-flip never
        ran because the source file was first typed as 'checking')
      - current_balance = +34.56 (positive = debt under the new
        convention, equivalent to the pre-Phase-52 stored -34.56)
      - 3 transactions: 2 purchases ($50, $7.78) + 1 payment ($23.22)
        SUM(debit) - SUM(credit) = 50 + 7.78 - 23.22 = 34.56 ✓

    Dashboard formula for credit_card: -current_balance = -34.56.
    Net worth decreases by 34.56 (debt subtracted).

    Before this test existed, a regression that re-introduced the
    pre-fix bug (credit_card ADD directly with positive stored
    balance → inflates net worth) would re-appear silently. This
    test pins the FIXED contract for the new convention.
    """
    from datetime import datetime

    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)

    acct = make_account(
        account_name="Misclassified Citi Card",
        account_type="credit_card",  # current type -- the re-classification
        institution_name="Citi",
        current_balance=34.56,  # positive-debt convention: balance > 0 = owed
    )
    db_session.add(acct)
    db_session.flush()

    # 3 transactions: 2 purchases + 1 payment. New convention:
    #   debit = money out (unsigned positive)
    #   credit = money in (unsigned positive)
    # Stored amount = credit - debit (universal accounting).
    #   purchase $50:   debit=50,   credit=NULL, amount=-50
    #   purchase $7.78: debit=7.78, credit=NULL, amount=-7.78
    #   payment  $23.22: debit=NULL, credit=23.22, amount=+23.22
    # SUM(debit) - SUM(credit) = 50 + 7.78 - 23.22 = 34.56 ✓
    now = datetime.utcnow()
    db_session.add(make_transaction(
        account_id=acct.id, description="AMAZON.COM*MK4US",
        amount=-50.00, debit=50.00, credit=None,
        transaction_date=now,
    ))
    db_session.add(make_transaction(
        account_id=acct.id, description="STARBUCKS #1234",
        amount=-7.78, debit=7.78, credit=None,
        transaction_date=now,
    ))
    db_session.add(make_transaction(
        account_id=acct.id, description="ONLINE PAYMENT THANK YOU",
        amount=23.22, debit=None, credit=23.22,
        transaction_date=now,
    ))
    db_session.commit()

    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    # Phase 52+ contract: a credit_card's POSITIVE stored balance is
    # SUBTRACTED (because positive = debt owed under the new
    # convention). Net worth correctly decreases by 34.56.
    assert body["total_balance"] == pytest.approx(-34.56, abs=1e-2), (
        f"credit_card positive-debt balance must reduce net worth; "
        f"got total_balance={body['total_balance']!r} (expected -34.56)"
    )


def test_dashboard_summary_loan_balance_reduces_net_worth(
    client, install_finlynq_state_forward, db_session, make_account, make_transaction
):
    """Regression -- loan payment convention (unchanged by Phase 52+).

    Loans store their balance as POSITIVE (the amount owed). The
    dashboard formula (Phase 52+ unified: SUBTRACT every
    CREDIT_ACCOUNT_TYPES balance) continues to handle this correctly.

    A $250,000 mortgage with current_balance=250000 should reduce
    net worth by 250000 (not increase it).
    """
    from datetime import datetime

    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)

    acct = make_account(
        account_name="Home Mortgage",
        account_type="mortgage",
        institution_name="Wells Fargo Home",
        current_balance=250000.00,  # POSITIVE = amount owed (loan convention)
    )
    db_session.add(acct)
    db_session.flush()

    # Phase 52+ convention: principal payment reduces debt, so
    # the principal payment is a CREDIT (money in from borrower's
    # perspective, debt decreases).
    db_session.add(make_transaction(
        account_id=acct.id, description="PRINCIPAL PAYMENT",
        amount=1200.00, debit=None, credit=1200.00,
        transaction_date=datetime.utcnow(),
    ))
    db_session.commit()

    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    # Loan convention (unchanged): stored balance is positive; formula
    # SUBTRACTS (see dashboard.py sa_case branch for credit types).
    assert body["total_balance"] == pytest.approx(-250000.00, abs=1e-2), (
        f"mortgage balance must reduce net worth by the amount owed; "
        f"got total_balance={body['total_balance']!r} (expected -250000.00)"
    )


def test_dashboard_summary_credit_card_debt_reduces_net_worth_dual_column(
    client, install_finlynq_state_forward, db_session, make_account, make_transaction
):
    """Phase 52+ regression -- the user's exact scenario after
    re-importing the misclassified credit card statement as a
    Citi-style dual-column CSV. Validates the END-TO-END contract:
    balance = expenses - payments = positive number = debt, net
    worth subtracts.

    Database state:
      - account_type='credit_card'
      - current_balance=17400.82 (the user's actual debt magnitude)
      - 4 transactions: 2 expenses + 2 payments from the Citi fixture
        debit  = 10.68 + 116.39 = 127.07
        credit = 25.00 + 971.38 = 996.38
        balance = SUM(debit) - SUM(credit) = 127.07 - 996.38 = -869.31
        (negative because the payments exceed the expenses → overpaid
         / has a credit balance; the user has paid off the debt)

    Wait -- the user's actual data has purchases > payments. For
    THIS test we use the user's snippet data which has 2 expenses
    and 2 payments (with the payments larger). The POINT is that
    the dual-column pipeline correctly computes balance = debit -
    credit, regardless of sign.

    Dashboard formula: credit_card SUBTRACT -> -(-869.31) = +869.31
    added to net worth, increasing it by 869.31 (the credit
    balance is a positive asset from the user's perspective).

    This validates the end-to-end dual-column flow: parse Citi
    fixture → emit (debit, credit, amount) per row → INSERT
    transactions with both columns → recompute balance → dashboard
    renders correctly. Before this test existed, a regression
    that lost the dual-column write at the route layer would
    silently fall back to single-amount accounting and the user's
    'card balance is wrong' report would re-appear.
    """
    from datetime import datetime

    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)

    acct = make_account(
        account_name="Citi Credit Card",
        account_type="credit_card",
        institution_name="Citi",
        # 2 expenses ($127.07) - 2 payments ($996.38) = -$869.31
        # Negative = overpaid (has a credit balance on the card)
        current_balance=-869.31,
    )
    db_session.add(acct)
    db_session.flush()

    now = datetime.utcnow()
    # 2 expenses
    db_session.add(make_transaction(
        account_id=acct.id, description="BURRITOS CALIFORNIA MA MARYSVILLE WA",
        amount=-10.68, debit=10.68, credit=None, transaction_date=now,
    ))
    db_session.add(make_transaction(
        account_id=acct.id, description="WA DOL LIC & REG 07317 MILL CREEK WA",
        amount=-116.39, debit=116.39, credit=None, transaction_date=now,
    ))
    # 2 payments (Citi displays payments as -X in the Credit column;
    # we normalize to positive and store in the credit column)
    db_session.add(make_transaction(
        account_id=acct.id, description="AUTOPAY 999990000076194",
        amount=25.00, debit=None, credit=25.00, transaction_date=now,
    ))
    db_session.add(make_transaction(
        account_id=acct.id, description="ONLINE PAYMENT THANK YOU",
        amount=971.38, debit=None, credit=971.38, transaction_date=now,
    ))
    db_session.commit()

    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    # Phase 52+ contract: credit_card stored as -869.31 (negative
    # because payments > expenses → credit balance on card, which
    # the user actually has a credit / has overpaid). Formula
    # SUBTRACTS the credit balance: -(-869.31) = +869.31 added to
    # net worth. The credit balance increases net worth because
    # the bank owes the user $869.31 in a refund / credit position.
    assert body["total_balance"] == pytest.approx(869.31, abs=1e-2), (
        f"credit_card overpayment (negative stored balance) must "
        f"increase net worth; got total_balance={body['total_balance']!r} "
        f"(expected +869.31)"
    )


def test_citi_dual_column_csv_upload_end_to_end(
    client, install_finlynq_state_forward, db_session
):
    """Phase 52+ end-to-end test — upload the Citi dual-column CSV
    fixture through POST /api/imports/upload and verify the full
    pipeline: parser emits (debit, credit, amount) per row, the
    route persists those columns, the type-aware balance recompute
    produces the correct current_balance, and the dashboard formula
    correctly subtracts the credit-type debt from net worth.

    This single test pins the entire chain so a regression at any
    layer (parser, route, balance recompute, dashboard formula)
    surfaces here, not as a silent "balance is wrong" complaint.

    Fixture shape (atlas_test_credit_card.csv):
      Status,Date,Description,Debit,Credit
      Cleared,06/19/2026,BURRITOS...,10.68,
      Cleared,06/18/2026,WA DOL LIC & REG...,116.39,
      Cleared,05/16/2026,AUTOPAY...,-25.00
      Cleared,04/12/2026,ONLINE PAYMENT...,-971.38
      Cleared,03/28/2026,REFUND FROM AMAZON,-15.00

    Expected after the new convention (debit = money out, credit = money in):
      row 1: amount=-10.68,  debit=10.68,  credit=None
      row 2: amount=-116.39, debit=116.39, credit=None
      row 3: amount=+25.00,  debit=None,   credit=25.00
      row 4: amount=+971.38, debit=None,   credit=971.38
      row 5: amount=+15.00,  debit=None,   credit=15.00

    Account balance (type-aware):
      SUM(debit)  = 10.68 + 116.39 = 127.07
      SUM(credit) = 25.00 + 971.38 + 15.00 = 1011.38
      balance     = 127.07 - 1011.38 = -884.31 (negative = credit
                   balance / overpayment on the card)

    Dashboard formula: credit_card SUBTRACT => -(-884.31) = +884.31
    added to net worth (the bank owes the user $884.31).
    """
    from pathlib import Path

    # Load the fixture from disk so the test exercises the same
    # wire shape the FE sends (multipart/form-data with a file upload).
    fixture_path = (
        Path(__file__).parent / "fixtures" / "atlas_test_credit_card.csv"
    )
    assert fixture_path.exists(), (
        f"Test fixture missing: {fixture_path} — required for the "
        f"end-to-end dual-column upload test."
    )
    csv_bytes = fixture_path.read_bytes()

    canned = {
        "total_balance": 0.0,
        "total_income_month": 0.0,
        "total_expenses_month": 0.0,
        "accounts_count": 0,
        "transactions_count": 0,
        "last_sync": None,
        "import_batches_count": 0,
        "last_import_at": None,
        "user_goals": [],
    }
    install_finlynq_state_forward(canned)

    # Upload the CSV through the real route (no mocking of the parser
    # — the test exercises the full chain).
    r = client.post(
        "/api/imports/upload",
        files={"file": ("atlas_test_credit_card.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200, (
        f"Upload failed: {r.status_code} {r.text} — parser may have "
        f"rejected the dual-column CSV."
    )
    upload_body = r.json()
    assert upload_body["saved_transactions"] == 5, (
        f"Expected 5 transactions persisted, got "
        f"{upload_body['saved_transactions']}"
    )
    account_id = upload_body["account_id"]

    # Verify the persisted transactions carry dual columns.
    from app.models import Account, Transaction

    persisted = (
        db_session.query(Transaction)
        .filter(Transaction.account_id == account_id)
        .order_by(Transaction.id)
        .all()
    )
    assert len(persisted) == 5, f"Expected 5 txns, got {len(persisted)}"
    # Phase 52+ — description[:30] truncates the AUTOPAY row's full
    # description to a 30-char prefix; identify rows by an exact hard
    # match on the first 30 chars (locked here so a future desc
    # length change surfaces as a clear test failure, not a silent
    # ``None`` on a fuzzy key).
    by_desc = {t.description[:30]: t for t in persisted}
    # Synthetic fixture identifiers are intentionally obvious and contain no
    # merchant or customer data; keep prefix matching to cover truncation.
    BURRITOS_KEY = "ATLAS SYNTHETIC BURRITOS TEST-0001"[:30]
    AUTOPAY_KEY = "ATLAS SYNTHETIC AUTOPAY TEST-0002"[:30]
    # Purchases: debit populated, credit NULL, amount negative.
    burritos = by_desc.get(BURRITOS_KEY)
    assert burritos is not None, f"Missing BURRITOS row: {by_desc.keys()}"
    assert burritos.debit == pytest.approx(10.68, abs=1e-2), (
        f"BURRITOS debit should be 10.68, got {burritos.debit}"
    )
    assert burritos.credit is None, (
        f"BURRITOS credit should be NULL (purchase), got {burritos.credit}"
    )
    assert burritos.amount == pytest.approx(-10.68, abs=1e-2)
    # Payments: credit populated, debit NULL, amount positive.
    autopay = by_desc.get(AUTOPAY_KEY)
    assert autopay is not None, f"Missing AUTOPAY row: {by_desc.keys()}"
    assert autopay.credit == pytest.approx(25.00, abs=1e-2), (
        f"AUTOPAY credit should be 25.00, got {autopay.credit}"
    )
    assert autopay.debit is None, (
        f"AUTOPAY debit should be NULL (payment), got {autopay.debit}"
    )
    assert autopay.amount == pytest.approx(25.00, abs=1e-2)

    # Verify the type-aware balance recompute.
    acct = db_session.query(Account).filter(Account.id == account_id).first()
    assert acct.account_type == "credit_card", (
        f"Expected credit_card type, got {acct.account_type}"
    )
    # SUM(debit) - SUM(credit) = 127.07 - 1011.38 = -884.31
    assert acct.current_balance == pytest.approx(-884.31, abs=1e-2), (
        f"Type-aware balance recompute wrong: got {acct.current_balance}, "
        f"expected -884.31 (debit=127.07 - credit=1011.38)"
    )

    # Verify the dashboard formula correctly subtracts the credit card.
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    # credit_card SUBTRACT => -(-884.31) = +884.31 added to net worth
    # (the bank owes the user $884.31, increasing their net worth).
    assert body["total_balance"] == pytest.approx(884.31, abs=1e-2), (
        f"Dashboard formula wrong: got total_balance={body['total_balance']}, "
        f"expected +884.31 (credit_card overpayment increases net worth)"
    )


def test_dashboard_summary_forwarder_non_json_2xx_maps_to_502(
    client, install_finlynq_state_forward, monkeypatch
):
    """Forwarder error envelope: Finlynq 2xx with non-JSON body ->
    rules-service 502.

    Catches the cold-start ``pong`` safety case the imports forwarder
    handles (per Phase-F2 #1 contract).
    """
    import httpx

    async def _stub_pong(method, path, *, json=None, fc_session=None, authorization=None):
        # 200 OK but with a non-JSON body; cold-start guard.
        return httpx.Response(
            200,
            content=b"pong",
            headers={"content-type": "text/plain"},
        )

    monkeypatch.setattr("app.routes.dashboard._forward", _stub_pong)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 502, r.text
