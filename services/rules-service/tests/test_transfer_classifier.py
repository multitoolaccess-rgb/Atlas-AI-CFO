# services/rules-service/tests/test_transfer_classifier.py
#
# Phase 30g — transfer detection and classification.
#
# Boundary tests (financial correctness — money movement):
#   1. Internal pairing: outflow on account A + inflow on account B
#      (same amount, near date, DIFFERENT accounts) → both rows get
#      `transfer_pair_id` pointing at each other and are categorised
#      `Transfer`.
#   2. Same-account opposite-sign rows are refunds/reversals → NEVER
#      paired.
#   3. Amount mismatch (> 1 cent) or date gap (> 3 days) → NOT paired.
#   4. Manual / Debt categories are preserved: pairing only LINKS
#      (sets transfer_pair_id), it never re-categorises a loan or
#      credit-card payment to `Transfer`.
#   5. Direction classification: unpaired ZELLE/VENMO/WIRE/ATM rows
#      resolve to `Transfer In` / `Transfer Out`; rows in any other
#      category are never touched.
#   6. Cross-user isolation: another user's rows are never paired,
#      linked, or re-categorised (ownership flows through
#      Account.user_id — the classifier joins through Account).
#   7. One-to-one greedy pairing: an inflow pairs with only one outflow.
import pytest

from app.services.categorizer import seed_default_categories
from app.services.transfer_classifier import (
    classify_external_transfers,
    pair_internal_transfers,
    run_transfer_detection,
)
from app.models import Account, Category


@pytest.fixture
def seeded(db_session):
    """Canonical categories (incl. Transfer / Transfer In / Transfer Out)."""
    seed_default_categories(db_session)
    db_session.commit()
    return db_session


def _category_id(db, name):
    return db.query(Category).filter(Category.name == name).one().id


def _make_accounts(db, make_account, names=("Checking", "Savings")):
    """Two committed accounts for the local user; returns (a, b)."""
    accounts = []
    for n in names:
        acc = make_account(account_name=n)
        db.add(acc)
        accounts.append(acc)
    db.commit()
    return accounts


# ---------------------------------------------------------------
# Internal pairing
# ---------------------------------------------------------------
def test_pairs_internal_transfer_across_accounts(seeded, make_account, make_transaction):
    """$100 out of Checking + $100 into Savings (same day) → ONE pair,
    both halves categorised `Transfer`, both point at each other."""
    db = seeded
    checking, savings = _make_accounts(db, make_account)
    out = make_transaction(
        account_id=checking.id, description="TRANSFER TO SAVINGS",
        merchant_name="CHASE", amount=-100.00,
    )
    inn = make_transaction(
        account_id=savings.id, description="TRANSFER FROM CHECKING",
        merchant_name="CHASE", amount=100.00,
    )
    db.add_all([out, inn])
    db.commit()

    pairs = pair_internal_transfers(db, checking.user_id)
    assert pairs == 1

    # Classifier does not commit — callers own the commit. Persist
    # before re-reading so the assertions verify durable state.
    db.commit()
    db.refresh(out)
    db.refresh(inn)
    assert out.transfer_pair_id == inn.id
    assert inn.transfer_pair_id == out.id
    transfer_id = _category_id(db, "Transfer")
    assert out.category_id == transfer_id
    assert inn.category_id == transfer_id


def test_same_account_opposite_sign_is_not_a_transfer(seeded, make_account, make_transaction):
    """A refund posts as an outflow + inflow on the SAME account — that
    is a reversal, not an internal transfer, and must never pair."""
    db = seeded
    checking, _ = _make_accounts(db, make_account)
    out = make_transaction(account_id=checking.id, description="PURCHASE", amount=-50.00)
    refund = make_transaction(account_id=checking.id, description="REFUND", amount=50.00)
    db.add_all([out, refund])
    db.commit()

    pairs = pair_internal_transfers(db, checking.user_id)
    assert pairs == 0
    db.commit()
    db.refresh(out)
    db.refresh(refund)
    assert out.transfer_pair_id is None
    assert refund.transfer_pair_id is None


def test_amount_mismatch_not_paired(seeded, make_account, make_transaction):
    """$100.01 out vs $100.00 in is a fee or a different movement — the
    cent epsilon rejects the pair."""
    db = seeded
    checking, savings = _make_accounts(db, make_account)
    out = make_transaction(account_id=checking.id, description="TRANSFER", amount=-100.01)
    inn = make_transaction(account_id=savings.id, description="TRANSFER", amount=100.00)
    db.add_all([out, inn])
    db.commit()

    assert pair_internal_transfers(db, checking.user_id) == 0
    db.commit()
    db.refresh(out)
    assert out.transfer_pair_id is None


def test_date_window_rejects_stale_rows(seeded, make_account, make_transaction):
    """Rows more than 3 days apart (ACH float) are unrelated movements."""
    from datetime import datetime, timedelta, timezone

    db = seeded
    checking, savings = _make_accounts(db, make_account)
    out = make_transaction(
        account_id=checking.id, description="TRANSFER", amount=-100.00,
        transaction_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    inn = make_transaction(
        account_id=savings.id, description="TRANSFER", amount=100.00,
        transaction_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )
    db.add_all([out, inn])
    db.commit()

    assert pair_internal_transfers(db, checking.user_id) == 0
    db.commit()
    db.refresh(out)
    assert out.transfer_pair_id is None


def test_pairs_within_three_day_float(seeded, make_account, make_transaction):
    """ACH float: 2 days apart is still the same transfer."""
    from datetime import datetime, timedelta, timezone

    db = seeded
    checking, savings = _make_accounts(db, make_account)
    out = make_transaction(
        account_id=checking.id, description="TRANSFER", amount=-100.00,
        transaction_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    inn = make_transaction(
        account_id=savings.id, description="TRANSFER", amount=100.00,
        transaction_date=datetime(2026, 2, 3, tzinfo=timezone.utc),
    )
    db.add_all([out, inn])
    db.commit()

    assert pair_internal_transfers(db, checking.user_id) == 1
    db.commit()
    db.refresh(inn)
    assert inn.transfer_pair_id == out.id


def test_manual_category_is_linked_but_never_overwritten(seeded, make_account, make_transaction):
    """A row the user hand-categorised (Groceries) can still be LINKED
    to its inverse half, but its manual category survives."""
    db = seeded
    checking, savings = _make_accounts(db, make_account)
    groceries_id = _category_id(db, "Groceries")
    out = make_transaction(
        account_id=checking.id, description="TRANSFER TO SAVINGS",
        amount=-100.00, category_id=groceries_id,
    )
    inn = make_transaction(
        account_id=savings.id, description="TRANSFER FROM CHECKING", amount=100.00,
    )
    db.add_all([out, inn])
    db.commit()

    assert pair_internal_transfers(db, checking.user_id) == 1
    db.commit()
    db.refresh(out)
    db.refresh(inn)
    assert out.transfer_pair_id == inn.id
    assert out.category_id == groceries_id          # manual kept
    assert inn.category_id == _category_id(db, "Transfer")


def test_loan_payment_keeps_debt_category(seeded, make_account, make_transaction):
    """Credit-card payment halves pair (so cash flow math can net them)
    but KEEP their Debt categories — never re-categorised to Transfer."""
    db = seeded
    checking, credit = _make_accounts(db, make_account, names=("Checking", "Credit Card"))
    cc_payments_id = _category_id(db, "Credit Card Payments")
    payment = make_transaction(
        account_id=checking.id, description="CREDIT CARD PAYMENT", amount=-250.00,
        category_id=cc_payments_id,
    )
    credit_txn = make_transaction(
        account_id=credit.id, description="PAYMENT RECEIVED", amount=250.00,
        category_id=cc_payments_id,
    )
    db.add_all([payment, credit_txn])
    db.commit()

    pairs = pair_internal_transfers(db, checking.user_id)
    assert pairs == 1
    db.commit()
    db.refresh(payment)
    db.refresh(credit_txn)
    assert payment.transfer_pair_id == credit_txn.id      # linked
    assert payment.category_id == cc_payments_id          # Debt kept
    assert credit_txn.category_id == cc_payments_id       # Debt kept


def test_greedy_one_to_one_pairing(seeded, make_account, make_transaction):
    """Two outflows on account A, one inflow on account B: only the
    NEAREST-date outflow pairs; the other stays unpaired."""
    from datetime import datetime, timedelta, timezone

    db = seeded
    checking, savings = _make_accounts(db, make_account)
    near = make_transaction(
        account_id=checking.id, description="TRANSFER 1", amount=-100.00,
        transaction_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    far = make_transaction(
        account_id=checking.id, description="TRANSFER 2", amount=-100.00,
        transaction_date=datetime(2026, 3, 5, tzinfo=timezone.utc),
    )
    inn = make_transaction(
        account_id=savings.id, description="TRANSFER", amount=100.00,
        transaction_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
    )
    db.add_all([near, far, inn])
    db.commit()

    pairs = pair_internal_transfers(db, checking.user_id)
    assert pairs == 1
    db.commit()
    db.refresh(near)
    db.refresh(far)
    db.refresh(inn)
    assert near.transfer_pair_id == inn.id
    assert far.transfer_pair_id is None
    assert inn.transfer_pair_id == near.id


# ---------------------------------------------------------------
# Direction classification (external transfers)
# ---------------------------------------------------------------
def test_classifies_unpaired_rows_by_direction(seeded, make_account, make_transaction):
    """Zelle received → Transfer In; wire out → Transfer Out."""
    db = seeded
    checking, _ = _make_accounts(db, make_account)
    incoming = make_transaction(
        account_id=checking.id, description="ZELLE FROM KATIE", amount=40.00,
    )
    outgoing = make_transaction(
        account_id=checking.id, description="WIRE OUT TO BROKER", amount=-1200.00,
    )
    db.add_all([incoming, outgoing])
    db.commit()

    classified = classify_external_transfers(db, checking.user_id)
    assert classified == 2
    db.commit()
    db.refresh(incoming)
    db.refresh(outgoing)
    assert incoming.category_id == _category_id(db, "Transfer In")
    assert outgoing.category_id == _category_id(db, "Transfer Out")


def test_classify_never_touches_manual_or_debt_categories(seeded, make_account, make_transaction):
    """A Groceries row containing 'ZELLE' text is a manual choice — left
    alone even though the keyword would classify it."""
    db = seeded
    checking, _ = _make_accounts(db, make_account)
    groceries_id = _category_id(db, "Groceries")
    manual = make_transaction(
        account_id=checking.id, description="ZELLE FROM KATIE", amount=40.00,
        category_id=groceries_id,
    )
    db.add(manual)
    db.commit()

    assert classify_external_transfers(db, checking.user_id) == 0
    db.commit()
    db.refresh(manual)
    assert manual.category_id == groceries_id


def test_classify_skips_rows_with_no_direction_signal(seeded, make_account, make_transaction):
    """A generic uncategorised row with no in/out keyword stays as-is."""
    db = seeded
    checking, _ = _make_accounts(db, make_account)
    txn = make_transaction(account_id=checking.id, description="TARGET", amount=-23.40)
    db.add(txn)
    db.commit()

    assert classify_external_transfers(db, checking.user_id) == 0
    db.commit()
    db.refresh(txn)
    assert txn.category_id is None


# ---------------------------------------------------------------
# Cross-user isolation + pipeline
# ---------------------------------------------------------------
def test_never_touches_another_users_rows(seeded, make_account, make_transaction):
    """A second user's transfer-looking rows are invisible: no pairing,
    no classification (ownership resolves through Account.user_id)."""
    from app.models import User
    from app.routes.shared import get_or_create_local_user

    db = seeded
    checking, savings = _make_accounts(db, make_account)
    local_out = make_transaction(
        account_id=checking.id, description="TRANSFER TO SAVINGS", amount=-100.00,
    )
    local_in = make_transaction(
        account_id=savings.id, description="TRANSFER FROM CHECKING", amount=100.00,
    )
    db.add_all([local_out, local_in])

    other_user = User(
        local_user_sub="other-transfer-user", email="other@example.com",
        hashed_password="x", is_active=True,
    )
    db.add(other_user)
    db.flush()
    # Direct ORM create: make_account hard-codes the local user's id.
    from app.routes.shared import (
        get_or_create_family_member_self,
        get_or_create_institution,
    )
    other_institution = get_or_create_institution(db, "Other Bank")
    other_family = get_or_create_family_member_self(db, other_user)
    other_acc = Account(
        user_id=other_user.id,
        institution_id=other_institution.id,
        account_name="Other Bank",
        account_type="checking",
        current_balance=0.0,
        is_active=True,
        family_member_id=other_family.id,
    )
    db.add(other_acc)
    db.flush()
    other_out = make_transaction(
        account_id=other_acc.id, description="TRANSFER TO SAVINGS", amount=-100.00,
    )
    other_in = make_transaction(
        account_id=other_acc.id, description="ZELLE FROM STRANGER", amount=100.00,
    )
    db.add_all([other_out, other_in])
    db.commit()

    local_user = get_or_create_local_user(db, "alex")
    result = run_transfer_detection(db, local_user.id)
    assert result == {"pairs": 1, "classified": 0}
    db.commit()

    db.refresh(other_out)
    db.refresh(other_in)
    assert other_out.transfer_pair_id is None
    assert other_in.transfer_pair_id is None
    assert other_in.category_id is None


def test_run_transfer_detection_does_not_commit(seeded, make_account, make_transaction):
    """The pipeline returns counts and leaves the commit to the caller
    (mirrors categorize_transactions' contract)."""
    db = seeded
    checking, savings = _make_accounts(db, make_account)
    out = make_transaction(account_id=checking.id, description="TRANSFER TO SAVINGS", amount=-100.00)
    inn = make_transaction(account_id=savings.id, description="TRANSFER FROM CHECKING", amount=100.00)
    zelle = make_transaction(account_id=checking.id, description="ZELLE FROM KATIE", amount=25.00)
    db.add_all([out, inn, zelle])
    db.commit()

    result = run_transfer_detection(db, checking.user_id)
    assert result == {"pairs": 1, "classified": 1}

    # Nothing committed yet: a rollback reverts the pending edits.
    db.rollback()
    db.refresh(out)
    db.refresh(zelle)
    assert out.transfer_pair_id is None
    assert zelle.category_id is None
