"""B0 provider tests use only synthetic, isolated in-memory state."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Account, AccountBalanceEvidence, Goal, GoalProjectionConfig, Institution, User
from app.projection_state.confirm_balance_observations import confirm_all_active_balances_current
from app.projection_state.confirm_currency import confirm_currency
from app.projection_state.currency import CurrencyEvidenceConflict, effective_currency_for_account, record_currency_evidence
from app.projection_state.provider import ProjectionStateUnavailable, build_projection_state
from app.services.ofx_parser import _declared_currency


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db, *, currencies=("USD",), stale=False, contribution=True):
    now = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
    user = User(local_user_sub="atlas-test-user", email="atlas@example.com", hashed_password="x")
    institution = Institution(name="Atlas Test Institution")
    db.add_all([user, institution]); db.flush()
    goal = Goal(user_id=user.id, name="Atlas Test Goal", target_amount=1234.56, is_archived=False)
    db.add(goal); db.flush()
    for index, currency in enumerate(currencies, 1):
        observed = now - timedelta(days=8) if stale else now
        values = {
            "user_id": user.id, "institution_id": institution.id, "account_name": f"Synthetic {index}",
            "account_type": "checking" if index == 1 else "credit_card", "current_balance": 100.25,
            "is_active": True, "last_sync": observed,
        }
        if currency is not None:
            values.update({
                "currency_code": currency, "currency_source": "provider_reported",
                "currency_observed_at": observed, "currency_source_reference": f"provider-account-{index}",
            })
        account = Account(**values)
        db.add(account)
        db.flush()
        if currency is not None:
            record_currency_evidence(
                db, account=account, event_type="assertion", source_kind="structured_provider",
                code=currency, observed_at=observed, source_reference=f"provider-account-{index}",
                actor_category="synthetic_provider", idempotency_key=f"provider-currency-{index}",
            )
    if contribution:
        db.flush()
        db.add(GoalProjectionConfig(
            user_id=user.id, goal_id=goal.id, projection_kind="net_worth", currency_code="USD",
            monthly_contribution=Decimal("456.78"), contribution_source_reference="operator-plan-1",
            contribution_observed_at=now,
        ))
    db.commit()
    confirm_all_active_balances_current(
        db,
        user_sub=user.local_user_sub,
        observed_at=now,
        apply=True,
        confirm_all_active=True,
        expected_intent_hash=confirm_all_active_balances_current(
            db,
            user_sub=user.local_user_sub,
            observed_at=now,
            apply=False,
            now=now,
        )["intent_hash"],
        now=now,
    )
    return user, goal, now


def test_provider_emits_deterministic_private_usd_envelope():
    db = _session(); user, goal, now = _seed(db)
    first = build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)
    second = build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)
    assert first == second
    assert first["currency"] == "USD"
    assert first["current_value_components"][0]["amount"] == "100.25"
    assert first["missing_data_codes"] == []
    assert first["reconciliation_state"] == "reconciled"
    serialized = str(first)
    assert "Synthetic" not in serialized and "Atlas Test Institution" not in serialized
    assert first["provenance"][0]["source_state_hash"] != ""


def test_provider_applies_assets_minus_liabilities_and_hashes_currency_provenance():
    db = _session(); user, goal, now = _seed(db, currencies=("USD", "USD"))
    state = build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)
    assert [item["amount"] for item in state["current_value_components"]] == ["100.25", "-100.25"]
    original_hash = state["provenance"][0]["source_state_hash"]
    account = db.query(Account).filter(Account.account_type == "credit_card").one()
    correction = effective_currency_for_account(db, account_id=account.id, user_id=user.id, now=now)
    record_currency_evidence(
        db, account=account, event_type="correction", source_kind="correction", code="USD",
        observed_at=now, source_reference="provider-reconciled-2", actor_category="synthetic_provider",
        idempotency_key="provider-currency-correction-2", supersedes_event_id=correction.evidence_event_id,
    )
    db.commit()
    changed = build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)
    assert changed["provenance"][0]["source_state_hash"] != original_hash


@pytest.mark.parametrize("currencies,stale,contribution,reason", [
    ((None,), False, True, "currency_unknown"), (("EUR",), False, True, "currency_unsupported"),
    (("USD", "EUR"), False, True, "currency_mixed"), (("USD",), True, True, "currency_stale"),
    (("USD",), False, False, "projection_state_unavailable"),
])
def test_provider_fails_closed_for_missing_or_unsupported_authority(currencies, stale, contribution, reason):
    db = _session(); user, goal, now = _seed(db, currencies=currencies, stale=stale, contribution=contribution)
    with pytest.raises(ProjectionStateUnavailable) as exc:
        build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)
    assert str(exc.value) == reason


def test_provider_hides_cross_user_goal_existence():
    db = _session(); user, goal, now = _seed(db)
    with pytest.raises(ProjectionStateUnavailable) as exc:
        build_projection_state(db, user_sub="other-user", goal_id=goal.id, now=now)
    assert str(exc.value) == "projection_state_unavailable"


def test_provider_fails_closed_when_authoritative_decimal_balance_evidence_is_missing():
    db = _session(); user, goal, now = _seed(db)
    db.query(AccountBalanceEvidence).delete()
    db.commit()
    with pytest.raises(ProjectionStateUnavailable, match="balance_evidence_unknown"):
        build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)


def test_provider_rejects_legacy_float_that_exceeds_v1_decimal_scale():
    db = _session(); user, goal, now = _seed(db)
    account = db.query(Account).one()
    account.current_balance = 1e-19
    db.commit()
    with pytest.raises(ProjectionStateUnavailable, match="balance_amount_precision_unavailable"):
        build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)


def test_currency_confirmation_is_dry_run_then_atomic_apply_and_refuses_conflicts():
    db = _session(); user, goal, now = _seed(db, currencies=(None,))
    account = db.query(Account).one()
    dry = confirm_currency(db, user_id=user.id, account_ids=[account.id], currency="USD", apply=False, observed_at=now)
    assert dry["mode"] == "dry_run" and account.currency_code is None
    applied = confirm_currency(db, user_id=user.id, account_ids=[account.id], currency="USD", apply=True, observed_at=now)
    assert applied["mode"] == "apply" and account.currency_code == "USD"
    with pytest.raises(ValueError, match="currency_evidence_conflict"):
        confirm_currency(db, user_id=user.id, account_ids=[account.id], currency="EUR", apply=True, observed_at=now)
    assert account.currency_code == "USD"


def test_currency_confirmation_rejects_cross_user_oversized_and_rolls_back_the_batch():
    db = _session(); user, goal, now = _seed(db, currencies=(None, None))
    accounts = db.query(Account).order_by(Account.id).all()
    record_currency_evidence(
        db, account=accounts[1], event_type="assertion", source_kind="structured_provider",
        code="EUR", observed_at=now, source_reference="provider-account-eur",
        actor_category="synthetic_provider", idempotency_key="provider-currency-eur",
    )
    db.commit()
    with pytest.raises(ValueError, match="currency_evidence_conflict"):
        confirm_currency(db, user_id=user.id, account_ids=[a.id for a in accounts], currency="USD", apply=True, observed_at=now)
    assert accounts[0].currency_code is None
    with pytest.raises(ValueError, match="unknown_or_unowned_account"):
        confirm_currency(db, user_id=user.id + 1, account_ids=[accounts[0].id], currency="USD", apply=False, observed_at=now)
    with pytest.raises(ValueError, match="invalid_account_batch"):
        confirm_currency(db, user_id=user.id, account_ids=list(range(1, 12)), currency="USD", apply=False, observed_at=now)


def test_currency_evidence_rejects_partial_or_invalid_values_without_preference_fallback():
    db = _session(); user, goal, now = _seed(db, currencies=(None,))
    account = db.query(Account).one()
    with pytest.raises(Exception):
        record_currency_evidence(
            db, account=account, event_type="assertion", source_kind="structured_provider",
            code="usd", observed_at=now, source_reference="provider-1",
            actor_category="synthetic_provider", idempotency_key="invalid-lowercase",
        )
    assert account.currency_code is None
    user.currency_preference = "USD"; db.commit()
    with pytest.raises(ProjectionStateUnavailable):
        build_projection_state(db, user_sub=user.local_user_sub, goal_id=goal.id, now=now)


def test_explicit_provider_and_structured_statement_currency_are_accepted_without_symbol_inference():
    db = _session(); user, goal, now = _seed(db, currencies=(None,))
    account = db.query(Account).one()
    result = record_currency_evidence(
        db, account=account, event_type="assertion", source_kind="structured_provider",
        code="USD", observed_at=now, source_reference="provider-currency-1",
        actor_category="synthetic_provider", idempotency_key="provider-currency-1",
    )
    assert result["status"] == "recorded"
    assert account.currency_code == "USD"

    class _Statement: currency = "USD"
    class _Account: statement = _Statement()
    class _Ofx: accounts = [_Account()]
    assert _declared_currency(_Ofx()) == "USD"
    _Statement.currency = "$"
    assert _declared_currency(_Ofx()) is None
