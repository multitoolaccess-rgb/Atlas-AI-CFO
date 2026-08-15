"""Synthetic exact-cent authoritative balance evidence tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Account, AccountBalanceEvidence, AccountBalanceObservation, Institution, User
from app.projection_state.balance_evidence import (
    BalanceEvidenceError,
    account_balance_evidence_state,
    confirmed_balance,
    evidence_state_hash,
    exact_balance,
)
from app.projection_state.confirm_balance_observations import confirm_all_active_balances_current
from app.projection_state.observation import BalanceObservationError


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(local_user_sub="exact-balance-user", email="exact@example.com", hashed_password="x", is_active=True)
    institution = Institution(name="Synthetic Exact Institution")
    session.add_all([user, institution]); session.flush()
    for index in range(4):
        session.add(Account(
            user_id=user.id, institution_id=institution.id, account_name=f"Synthetic Exact {index}",
            account_type="checking", current_balance=Decimal("100.25") + index, is_active=True,
        ))
    session.commit()
    try:
        yield session, user
    finally:
        session.close()


def _preview(db, user, observed):
    return confirm_all_active_balances_current(
        db, user_sub=user.local_user_sub, observed_at=observed, now=observed,
    )


def _apply(db, user, observed, intent):
    return confirm_all_active_balances_current(
        db, user_sub=user.local_user_sub, observed_at=observed, now=observed,
        apply=True, confirm_all_active=True, expected_intent_hash=intent,
    )


def test_new_confirmation_stores_exact_numeric_evidence_and_keeps_compatibility_audit(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    before = {account.id: repr(account.current_balance) for account in session.scalars(select(Account)).all()}
    preview = _preview(session, user, observed)
    _apply(session, user, observed, preview["intent_hash"])
    events = list(session.scalars(select(AccountBalanceEvidence).order_by(AccountBalanceEvidence.account_id)))
    assert len(events) == 4
    assert all(event.event_type == "assertion" and event.currency_code == "USD" for event in events)
    assert all(isinstance(event.amount, Decimal) and event.amount.as_tuple().exponent >= -2 for event in events)
    assert session.query(AccountBalanceObservation).count() == 4
    assert {account.id: repr(account.current_balance) for account in session.scalars(select(Account)).all()} == before
    assert all(account_balance_evidence_state(session, account, now=observed).state == "ready" for account in session.scalars(select(Account)).all())


def test_same_intent_is_idempotent_and_divergent_replay_is_rejected(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    intent = _preview(session, user, observed)["intent_hash"]
    _apply(session, user, observed, intent)
    replay = _apply(session, user, observed, intent)
    assert all(item["status"] == "idempotent_replay" for item in replay["accounts"])
    assert session.query(AccountBalanceEvidence).count() == 4
    with pytest.raises(BalanceObservationError, match="observation_intent_mismatch"):
        _apply(session, user, observed + timedelta(minutes=1), intent)


def test_authorized_half_even_confirmation_rounds_without_mutating_legacy_balance(db):
    session, user = db
    account = session.scalars(select(Account).order_by(Account.id)).first()
    account.current_balance = Decimal("100.255")
    session.commit()
    before = repr(account.current_balance)
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    preview = _preview(session, user, observed)
    _apply(session, user, observed, preview["intent_hash"])
    evidence = session.scalar(select(AccountBalanceEvidence).where(AccountBalanceEvidence.account_id == account.id))
    assert evidence is not None
    assert evidence.amount == Decimal("100.26")
    assert repr(account.current_balance) == before


def test_current_state_divergence_blocks_authority_until_reconfirmed(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    _apply(session, user, observed, _preview(session, user, observed)["intent_hash"])
    account = session.scalars(select(Account).order_by(Account.id)).first()
    account.current_balance = Decimal("101.25")
    session.commit()
    state = account_balance_evidence_state(session, account, now=observed)
    assert state.state == "blocked"
    assert state.reason_code == "balance_evidence_changed"


def test_revocation_blocks_latest_authority_without_deleting_history(db):
    session, user = db
    observed = datetime(2026, 8, 15, tzinfo=timezone.utc)
    _apply(session, user, observed, _preview(session, user, observed)["intent_hash"])
    account = session.scalars(select(Account).order_by(Account.id)).first()
    assertion = session.scalar(select(AccountBalanceEvidence).where(AccountBalanceEvidence.account_id == account.id))
    assert assertion is not None
    session.add(AccountBalanceEvidence(
        id="00000000-0000-4000-8000-000000000099", user_id=user.id, account_id=account.id,
        event_type="revocation", source_kind="operator_confirmed", actor_category="local_operator",
        currency_code="USD", amount=None, observed_at=observed, supersedes_event_id=assertion.id,
        precondition_hash=assertion.precondition_hash, state_hash="c" * 64,
        observation_intent_hash="d" * 64, idempotency_key_hash="e" * 64,
    ))
    session.commit()
    state = account_balance_evidence_state(session, account, now=observed)
    assert state.state == "blocked"
    assert state.reason_code == "balance_evidence_revoked"
    assert session.query(AccountBalanceEvidence).count() == 5


def test_exact_source_is_preserved_and_authorized_confirmation_uses_half_even():
    assert exact_balance(Decimal("100.25")).canonical == "100.25"
    assert exact_balance(Decimal("100.2")).canonical == "100.2"
    assert confirmed_balance(Decimal("100.255")).confirmed_canonical == "100.26"
    assert confirmed_balance(Decimal("100.245")).confirmed_canonical == "100.24"
    with pytest.raises(BalanceEvidenceError, match="balance_amount_precision_unavailable"):
        confirmed_balance(Decimal("1E+40"))
