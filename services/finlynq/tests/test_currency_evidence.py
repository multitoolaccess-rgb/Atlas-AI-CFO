"""Wave 2A currency evidence tests use only synthetic in-memory SQLite."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Account, AccountCurrencyEvidence, Institution, User
from app.projection_state.confirm_currency import confirm_currency
from app.projection_state.currency import (
    CurrencyEvidenceConflict,
    CurrencyEvidenceError,
    derive_effective_currency,
    effective_currency_for_account,
    record_currency_evidence,
)


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _account(db, *, user_id=1, active=True):
    user = db.get(User, user_id)
    if user is None:
        user = User(id=user_id, local_user_sub=f"synthetic-{user_id}", email=f"synthetic-{user_id}@example.com", hashed_password="x")
        db.add(user)
        db.flush()
    institution = Institution(name=f"Synthetic Institution {user_id}")
    db.add(institution)
    db.flush()
    account = Account(user_id=user.id, institution_id=institution.id, account_name="Synthetic Account", account_type="checking", is_active=active, current_balance=Decimal("10"))
    db.add(account)
    db.commit()
    return user, account


def _record(db, account, *, code="USD", key="evidence-1", event_type="assertion", source_kind="structured_provider", supersedes=None, observed=None, reference="provider-structured-1"):
    return record_currency_evidence(
        db, account=account, event_type=event_type, source_kind=source_kind, code=code,
        observed_at=observed or datetime(2026, 8, 1, tzinfo=timezone.utc), source_reference=reference,
        actor_category="synthetic_test", idempotency_key=key, supersedes_event_id=supersedes,
    )


def test_authoritative_assertion_is_append_only_and_idempotent_without_raw_reference():
    db = _db(); user, account = _account(db)
    first = _record(db, account)
    replay = _record(db, account, observed=datetime(2026, 8, 2, tzinfo=timezone.utc))
    assert replay["status"] == "idempotent_replay"
    assert db.query(AccountCurrencyEvidence).count() == 1
    event = db.query(AccountCurrencyEvidence).one()
    assert event.source_reference_hash != "provider-structured-1"
    assert effective_currency_for_account(db, account_id=account.id, user_id=user.id, now=datetime(2026, 8, 2, tzinfo=timezone.utc)).reason_code == "currency_authority_ready"
    assert first["event_id"] == event.id


def test_same_idempotency_key_with_divergent_payload_is_rejected():
    db = _db(); _, account = _account(db)
    _record(db, account)
    with pytest.raises(CurrencyEvidenceConflict, match="currency_evidence_conflict"):
        _record(db, account, code="EUR", key="evidence-1")


def test_correction_and_revocation_are_new_events_and_never_mutate_history():
    db = _db(); user, account = _account(db)
    first = _record(db, account)
    correction = _record(db, account, code="EUR", key="correction-1", event_type="correction", source_kind="correction", supersedes=first["event_id"], reference="operator-correction-1")
    assert effective_currency_for_account(db, account_id=account.id, user_id=user.id, now=datetime(2026, 8, 2, tzinfo=timezone.utc)).reason_code == "currency_unsupported"
    revoked = _record(db, account, code=None, key="revocation-1", event_type="revocation", source_kind="revocation", supersedes=correction["event_id"], reference="operator-revocation-1")
    assert effective_currency_for_account(db, account_id=account.id, user_id=user.id, now=datetime(2026, 8, 2, tzinfo=timezone.utc)).reason_code == "currency_revoked"
    assert db.query(AccountCurrencyEvidence).count() == 3
    assert db.get(AccountCurrencyEvidence, first["event_id"]).currency_code == "USD"
    assert revoked["event_type"] == "revocation"


def test_aggregate_fails_closed_for_unknown_mixed_stale_and_inactive_accounts():
    db = _db(); user, account = _account(db)
    assert derive_effective_currency(db, user_id=user.id).reason_code == "currency_unknown"
    _, second = _account(db, user_id=2)
    second.user_id = user.id
    db.commit()
    _record(db, account, key="usd-1")
    _record(db, second, code="EUR", key="eur-1", reference="provider-structured-2")
    assert derive_effective_currency(db, user_id=user.id, now=datetime(2026, 8, 2, tzinfo=timezone.utc)).reason_code == "currency_mixed"
    second.is_active = False
    db.commit()
    assert derive_effective_currency(db, user_id=user.id, now=datetime(2026, 8, 2, tzinfo=timezone.utc)).reason_code == "currency_authority_ready"
    account.currency_observed_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    db.commit()
    # The event timestamp, not the mutable compatibility cache, controls freshness.
    assert derive_effective_currency(db, user_id=user.id, now=datetime(2026, 8, 2, tzinfo=timezone.utc)).reason_code == "currency_authority_ready"
    stale = _record(db, account, key="stale-assertion", observed=datetime(2026, 7, 1, tzinfo=timezone.utc), reference="provider-stale-1")
    assert stale["status"] == "recorded"
    # A same-currency assertion is allowed, but its observed timestamp is now effective.
    assert derive_effective_currency(db, user_id=user.id, now=datetime(2026, 8, 10, tzinfo=timezone.utc)).reason_code == "currency_stale"


def test_invalid_authority_sources_codes_and_sensitive_references_fail_closed():
    db = _db(); _, account = _account(db)
    with pytest.raises(CurrencyEvidenceError, match="invalid_currency_source"):
        _record(db, account, source_kind="csv_symbol")
    with pytest.raises(CurrencyEvidenceError, match="invalid_currency_code"):
        _record(db, account, code="usd", key="lowercase")
    with pytest.raises(CurrencyEvidenceError, match="invalid_currency_source_reference"):
        _record(db, account, key="bad-reference", reference="account name")
    assert db.query(AccountCurrencyEvidence).count() == 0


def test_inactive_accounts_are_excluded_but_cross_owner_rows_are_not_accepted():
    db = _db(); user, account = _account(db)
    account.is_active = False
    db.commit()
    assert derive_effective_currency(db, user_id=user.id).reason_code == "currency_evidence_incomplete"
    _, other_account = _account(db, user_id=2)
    with pytest.raises(ValueError, match="unknown_or_unowned_account"):
        confirm_currency(db, user_id=user.id, account_ids=[other_account.id], currency="USD", apply=False)


def test_legacy_account_currency_cache_never_authorizes_projection_state():
    db = _db(); user, account = _account(db)
    account.currency_code = "USD"
    account.currency_source = "user_confirmed"
    account.currency_observed_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    account.currency_source_reference = "legacy-cache-only"
    db.commit()
    assert effective_currency_for_account(db, account_id=account.id, user_id=user.id, now=datetime(2026, 8, 2, tzinfo=timezone.utc)).reason_code == "currency_unknown"
