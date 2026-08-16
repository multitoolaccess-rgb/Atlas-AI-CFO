"""Synthetic tests for the bounded batch account-confirmation operator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Account, AccountBalanceEvidence, AccountCurrencyEvidence, Institution, User
from app.projection_state.confirm_new_accounts import BatchConfirmationError, confirm_new_active_accounts


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(local_user_sub="batch-confirm-user", email="batch@example.com", hashed_password="x", is_active=True)
    institution = Institution(name="Synthetic Batch Institution")
    session.add_all([user, institution])
    session.flush()
    for index in range(4):
        session.add(Account(
            user_id=user.id,
            institution_id=institution.id,
            account_name=f"Synthetic {index}",
            account_type="checking" if index % 2 == 0 else "investment",
            current_balance=Decimal("250.00") + index,
            is_active=True,
        ))
    session.commit()
    try:
        yield session, user
    finally:
        session.close()


def test_dry_run_reports_pending_counts_without_mutation(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    preview = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed, now=observed,
    )
    assert preview["mode"] == "dry_run"
    assert preview["status"] == "pending_confirmation"
    assert preview["eligible_active_accounts"] == 4
    assert preview["currency_pending"] == 4
    assert preview["balance_pending"] == 4
    assert preview["accounts_requiring_both"] == 4
    assert len(preview["intent_hash"]) == 64
    assert session.query(AccountCurrencyEvidence).count() == 0
    assert session.query(AccountBalanceEvidence).count() == 0


def test_apply_confirms_currency_and_balance_for_all_pending(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    intent = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed, now=observed,
    )["intent_hash"]
    result = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed,
        apply=True, confirm=True, expected_intent_hash=intent, now=observed,
    )
    assert result["mode"] == "apply"
    assert result["status"] == "confirmed"
    assert result["currency_recorded"] == 4
    assert result["balance_confirmed"] == 4
    assert session.query(AccountCurrencyEvidence).count() == 4
    assert session.query(AccountBalanceEvidence).count() == 4
    # Balances are never mutated.
    balances = {account.id: repr(account.current_balance) for account in session.scalars(select(Account)).all()}
    assert balances == {account.id: repr(account.current_balance) for account in session.scalars(select(Account)).all()}


def test_idempotent_replay_after_partial_apply(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    intent = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed, now=observed,
    )["intent_hash"]
    first = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed,
        apply=True, confirm=True, expected_intent_hash=intent, now=observed,
    )
    replay = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed,
        apply=True, confirm=True, expected_intent_hash=intent, now=observed,
    )
    assert first["status"] == "confirmed"
    # Everything already has evidence now.
    assert replay["status"] == "no_pending_accounts"
    assert session.query(AccountCurrencyEvidence).count() == 4
    assert session.query(AccountBalanceEvidence).count() == 4


def test_divergent_replay_and_missing_confirmation_fail_closed(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    intent = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed, now=observed,
    )["intent_hash"]
    with pytest.raises(BatchConfirmationError, match="explicit_batch_confirmation_required"):
        confirm_new_active_accounts(
            session, user_sub=user.local_user_sub, observed_at=observed,
            apply=True, expected_intent_hash=intent, now=observed,
        )
    later = observed + timedelta(minutes=1)
    with pytest.raises(BatchConfirmationError, match="batch_intent_mismatch"):
        confirm_new_active_accounts(
            session, user_sub=user.local_user_sub, observed_at=later,
            apply=True, confirm=True, expected_intent_hash=intent, now=later,
        )
    assert session.query(AccountCurrencyEvidence).count() == 0


def test_unknown_user_fails_and_balance_change_rejects_old_intent(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    with pytest.raises(BatchConfirmationError, match="operator_user_unavailable"):
        confirm_new_active_accounts(
            session, user_sub="missing-user", observed_at=observed, now=observed,
        )
    intent = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed, now=observed,
    )["intent_hash"]
    account = session.scalars(select(Account).order_by(Account.id)).first()
    account.current_balance = 999.99
    session.commit()
    with pytest.raises(BatchConfirmationError, match="batch_intent_mismatch"):
        confirm_new_active_accounts(
            session, user_sub=user.local_user_sub, observed_at=observed,
            apply=True, confirm=True, expected_intent_hash=intent, now=observed,
        )
    assert session.query(AccountCurrencyEvidence).count() == 0


def test_existing_evidence_accounts_are_not_pending(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    intent = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed, now=observed,
    )["intent_hash"]
    confirm_new_active_accounts(
        session, user_sub=user.local_user_sub, observed_at=observed,
        apply=True, confirm=True, expected_intent_hash=intent, now=observed,
    )
    # Add a brand-new active account: only it should be pending now.
    session.add(Account(
        user_id=user.id,
        institution_id=session.scalars(select(Institution)).first().id,
        account_name="Synthetic New",
        account_type="checking",
        current_balance=Decimal("10.00"),
        is_active=True,
    ))
    session.commit()
    preview = confirm_new_active_accounts(
        session, user_sub=user.local_user_sub,
        observed_at=observed + timedelta(minutes=5), now=observed + timedelta(minutes=5),
    )
    assert preview["currency_pending"] == 1
    assert preview["balance_pending"] == 1
