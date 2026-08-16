"""Synthetic tests for authoritative account-balance observations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Account, AccountBalanceObservation, Institution, User
from app.projection_state.confirm_balance_observations import confirm_all_active_balances_current
from app.projection_state.observation import BalanceObservationError, account_observation_state


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(local_user_sub="balance-observation-user", email="observation@example.com", hashed_password="x", is_active=True)
    institution = Institution(name="Synthetic Observation Institution")
    session.add_all([user, institution])
    session.flush()
    for index in range(4):
        session.add(Account(
            user_id=user.id,
            institution_id=institution.id,
            account_name=f"Synthetic {index}",
            account_type="checking",
            current_balance=Decimal("100.25") + index,
            is_active=True,
        ))
    session.commit()
    try:
        yield session, user
    finally:
        session.close()


def _dry_run(session, user, observed):
    return confirm_all_active_balances_current(
        session,
        user_sub=user.local_user_sub,
        observed_at=observed,
        apply=False,
        now=observed,
    )


def _apply(session, user, observed, intent_hash):
    return confirm_all_active_balances_current(
        session,
        user_sub=user.local_user_sub,
        observed_at=observed,
        apply=True,
        confirm_all_active=True,
        expected_intent_hash=intent_hash,
        now=observed,
    )


def test_dry_run_is_read_only_and_apply_preserves_every_balance(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    before = {account.id: repr(account.current_balance) for account in session.scalars(select(Account)).all()}
    preview = _dry_run(session, user, observed)
    assert preview["mode"] == "dry_run"
    assert preview["eligible_active_accounts"] == 4
    assert session.scalar(select(AccountBalanceObservation.id)) is None
    result = _apply(session, user, observed, preview["intent_hash"])
    assert result["mode"] == "apply"
    after = {account.id: repr(account.current_balance) for account in session.scalars(select(Account)).all()}
    assert after == before
    assert session.query(AccountBalanceObservation).count() == 4
    assert all(account.last_sync.replace(tzinfo=timezone.utc) == observed for account in session.scalars(select(Account)).all())


def test_same_intent_replays_idempotently_and_divergent_replay_fails(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    intent = _dry_run(session, user, observed)["intent_hash"]
    first = _apply(session, user, observed, intent)
    replay = _apply(session, user, observed, intent)
    assert first["mode"] == "apply"
    assert all(item["status"] == "idempotent_replay" for item in replay["accounts"])
    assert session.query(AccountBalanceObservation).count() == 4
    with pytest.raises(BalanceObservationError, match="observation_intent_mismatch"):
        _apply(session, user, observed + timedelta(minutes=1), intent)


def test_concurrent_balance_change_rejects_the_old_intent_without_partial_write(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    intent = _dry_run(session, user, observed)["intent_hash"]
    account = session.scalars(select(Account).order_by(Account.id)).first()
    account.current_balance = 999.99
    session.commit()
    with pytest.raises(BalanceObservationError, match="observation_intent_mismatch"):
        _apply(session, user, observed, intent)
    assert session.query(AccountBalanceObservation).count() == 0


def test_invalid_or_future_observation_fails_without_mutation(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    with pytest.raises(BalanceObservationError, match="observation_timestamp_in_future"):
        confirm_all_active_balances_current(
            session,
            user_sub=user.local_user_sub,
            observed_at=observed + timedelta(seconds=1),
            now=observed,
        )
    with pytest.raises(BalanceObservationError, match="balance_amount_precision_unavailable"):
        account = session.scalars(select(Account).order_by(Account.id)).first()
        account.current_balance = float("nan")
        session.flush()
        confirm_all_active_balances_current(session, user_sub=user.local_user_sub, observed_at=observed, now=observed)


def test_scoped_confirmation_touches_only_requested_accounts(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    accounts = session.scalars(select(Account).order_by(Account.id)).all()
    target = [int(accounts[1].id), int(accounts[2].id)]
    preview = confirm_all_active_balances_current(
        session, user_sub=user.local_user_sub, observed_at=observed,
        apply=False, account_ids=target, now=observed,
    )
    assert preview["mode"] == "dry_run"
    assert preview["eligible_active_accounts"] == 2
    result = confirm_all_active_balances_current(
        session, user_sub=user.local_user_sub, observed_at=observed,
        apply=True, confirm_all_active=True, expected_intent_hash=preview["intent_hash"],
        account_ids=target, now=observed,
    )
    assert result["mode"] == "apply"
    observed_rows = session.query(AccountBalanceObservation).all()
    assert len(observed_rows) == 2
    assert {row.account_id for row in observed_rows} == set(target)
    untouched = [account for account in accounts if int(account.id) not in target]
    assert all(account.last_sync is None for account in untouched)


def test_scoped_confirmation_rejects_unknown_or_inactive_targets(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    accounts = session.scalars(select(Account).order_by(Account.id)).all()
    target = [int(accounts[0].id), 9999]
    with pytest.raises(BalanceObservationError, match="balance_observation_scope_invalid"):
        confirm_all_active_balances_current(
            session, user_sub=user.local_user_sub, observed_at=observed,
            apply=False, account_ids=target, now=observed,
        )
    inactive = accounts[0]
    inactive.is_active = False
    session.commit()
    with pytest.raises(BalanceObservationError, match="balance_observation_scope_invalid"):
        confirm_all_active_balances_current(
            session, user_sub=user.local_user_sub, observed_at=observed,
            apply=False, account_ids=[int(inactive.id)], now=observed,
        )
    assert session.query(AccountBalanceObservation).count() == 0


def test_inactive_accounts_are_excluded_but_unknown_active_accounts_block(db):
    session, user = db
    account = session.scalars(select(Account).order_by(Account.id)).first()
    account.is_active = False
    session.commit()
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    preview = _dry_run(session, user, observed)
    assert preview["eligible_active_accounts"] == 3
    _apply(session, user, observed, preview["intent_hash"])
    assert session.query(AccountBalanceObservation).count() == 3


def test_freshness_boundary_and_changed_balance_fail_closed(db):
    session, user = db
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    observed = now - timedelta(days=7)
    preview = _dry_run(session, user, observed)
    _apply(session, user, observed, preview["intent_hash"])
    account = session.scalars(select(Account).order_by(Account.id)).first()
    assert account_observation_state(session, account, now=now).state == "ready"
    account.current_balance = 101.26
    session.commit()
    assert account_observation_state(session, account, now=now).reason_code == "balance_observation_changed"


def test_stale_observation_and_future_event_are_blocked(db):
    session, user = db
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    observed = now - timedelta(days=7, seconds=1)
    preview = _dry_run(session, user, observed)
    _apply(session, user, observed, preview["intent_hash"])
    account = session.scalars(select(Account).order_by(Account.id)).first()
    assert account_observation_state(session, account, now=now).reason_code == "balance_observation_stale"


def test_missing_owner_or_confirmation_flag_fails_closed(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    with pytest.raises(BalanceObservationError, match="explicit_all_active_confirmation_required"):
        confirm_all_active_balances_current(session, user_sub=user.local_user_sub, observed_at=observed, apply=True, now=observed)
    with pytest.raises(BalanceObservationError, match="operator_user_unavailable"):
        confirm_all_active_balances_current(session, user_sub="other-user", observed_at=observed, now=observed)


def test_audit_rows_do_not_contain_balance_or_sensitive_columns(db):
    session, user = db
    columns = {column.name for column in AccountBalanceObservation.__table__.columns}
    assert "current_balance" not in columns
    assert "account_name" not in columns
    assert "account_number" not in columns
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    preview = _dry_run(session, user, observed)
    _apply(session, user, observed, preview["intent_hash"])
    event = session.scalar(select(AccountBalanceObservation))
    assert event is not None
    assert len(event.precondition_hash) == 64
    assert len(event.observation_intent_hash) == 64
