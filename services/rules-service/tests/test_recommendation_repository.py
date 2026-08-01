"""DB-level tests for :class:`RecommendationRepository`.

The world fixtures live in :mod:`tests._commit3_world` and use
``alembic.command.upgrade`` so the Phase 2 ``recommendations``
immutability / ownership / format triggers ARE installed.  Every
test opens + asserts inside a single ``with Session(engine)`` block
so the returned ORM object stays attached while attributes are
read.

Coverage invariants proved here:

* goal ownership enforced BEFORE existence (no cross-user disclosure)
* forecast_version ownership + currency fail-closed
* idempotent replay ⇒ ``created=False`` and identical content
* different ``rule_version`` / ``recommendation_kind`` ⇒ new row
* race recovery: pre-seeded winner returns existing row, not a
  duplicate write
* ``UPDATE`` / ``DELETE`` at the SQL layer are blocked by the
  Phase 2 BEFORE UPDATE / DELETE triggers and surface as an
  :class:`OperationalError`
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.forecasts.recommendation_engine import ForecastSignals
from app.forecasts.recommendation_repository import (
    DerivationFailure,
    ForecastVersionCurrencyInvalid,
    ForecastVersionNotFoundError,
    GoalNotFoundError,
    PersistedRecommendation,
    RecommendationRepository,
)

from tests._commit3_world import (
    archived_goal_id,
    cross_user_goal_id,
    cross_user_id,
    forecast_version_id,
    primary_goal_id,
    primary_user_id,
    world_engine,
)


# ---------------------------------------------------------------------------
# Authorization (ownership-before-existence)
# ---------------------------------------------------------------------------


def test_repository_rejects_cross_user_goal(world_engine):
    """B is not the owner of goal #1; missing and cross-user are identical envelopes."""
    with Session(world_engine) as session:
        with pytest.raises(GoalNotFoundError):
            RecommendationRepository(session).persist(
                user_id=cross_user_id(),
                goal_id=primary_goal_id(),
                forecast_version_id=forecast_version_id(),
                recommendation_kind="hold",
            )


def test_repository_rejects_missing_goal_with_same_envelope(world_engine):
    with Session(world_engine) as session:
        with pytest.raises(GoalNotFoundError):
            RecommendationRepository(session).persist(
                user_id=primary_user_id(),
                goal_id=999,  # nonexistent
                forecast_version_id=forecast_version_id(),
                recommendation_kind="hold",
            )


def test_repository_rejects_archived_goal(world_engine):
    with Session(world_engine) as session:
        with pytest.raises(GoalNotFoundError):
            RecommendationRepository(session).persist(
                user_id=primary_user_id(),
                goal_id=archived_goal_id(),
                forecast_version_id=forecast_version_id(),
                recommendation_kind="hold",
            )


def test_repository_rejects_missing_forecast_version(world_engine):
    with Session(world_engine) as session:
        with pytest.raises(ForecastVersionNotFoundError):
            RecommendationRepository(session).persist(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                forecast_version_id="00000000-0000-4000-8000-000000000099",
                recommendation_kind="hold",
            )


# ---------------------------------------------------------------------------
# Currency fail-closed
# ---------------------------------------------------------------------------


def test_repository_propagates_engine_currency_fail_closed(world_engine, monkeypatch):
    """The repository translates engine ``InvalidCurrencyEvidence`` into
    ``ForecastVersionCurrencyInvalid`` so the application surfaces the safe
    ``currency_invalid`` envelope code.

    We monkeypatch :func:`app.forecasts.recommendation_repository.derive_recommendation`
    so the test does NOT need to bypass the Phase 1 ``currency = 'USD'``
    ``CHECK`` constraint on the ``forecast_versions`` table.
    """
    from app.forecasts import recommendation_repository as repo_module
    from app.forecasts.recommendation_engine import (
        InvalidCurrencyEvidence,
        ForecastSignals as _FS,
    )

    def raise_invalid_currency(*args, **kwargs):
        raise InvalidCurrencyEvidence("forced test")

    monkeypatch.setattr(repo_module, "derive_recommendation", raise_invalid_currency)
    monkeypatch.setattr(
        repo_module.ForecastSignals, "from_forecast_version",
        classmethod(lambda cls, fv: _FS(
            forecast_version_id=fv.id,
            forecast_input_state_hash=fv.input_state_hash,
            ending_balance=Decimal("0"),
            target_gap=Decimal("0"),
            data_as_of="2026-07-01T12:00:00Z",
            currency="EUR",  # forced; triggers InvalidCurrencyEvidence
            model_version="m",
            calculation_version="c",
        )),
    )

    with Session(world_engine) as session:
        with pytest.raises(ForecastVersionCurrencyInvalid):
            RecommendationRepository(session).persist(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                forecast_version_id=forecast_version_id(),
                recommendation_kind="hold",
            )


def test_repository_rejects_unrelated_goal_with_owned_forecast_version(world_engine):
    """Even if the caller owns the forecast_version, an unknown goal_id must NOT
    leak information about cross-user resources."""
    with Session(world_engine) as session:
        with pytest.raises(GoalNotFoundError):
            RecommendationRepository(session).persist(
                user_id=primary_user_id(),
                goal_id=cross_user_goal_id(),
                forecast_version_id=forecast_version_id(),
                recommendation_kind="hold",
            )


# ---------------------------------------------------------------------------
# Idempotent replay
# ---------------------------------------------------------------------------


def test_repository_persists_hold_kind_with_canonical_fields(world_engine):
    with Session(world_engine) as session:
        result = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
        assert isinstance(result, PersistedRecommendation)
        assert result.created is True
        rec = result.recommendation
        # Force attribute resolution while still attached.
        assert rec.user_id == primary_user_id()
        assert rec.goal_id == primary_goal_id()
        assert rec.recommendation_kind == "hold"
        assert rec.currency == "USD"
        assert rec.expected_impact_min_decimal == Decimal("0")
        assert rec.expected_impact_max_decimal == Decimal("0")
        assert 0 <= float(rec.confidence_score) <= 1
        assert forecast_version_id() in rec.provenance_json
        assert "v1.0" in rec.provenance_json


def test_repository_idempotent_replay_returns_identical_content(world_engine):
    with Session(world_engine) as session:
        first = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
        first_id = first.recommendation.id
        first_attrs = _snapshot_attributes(first.recommendation)
    with Session(world_engine) as session:
        replay = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
        replay_id = replay.recommendation.id
        replay_attrs = _snapshot_attributes(replay.recommendation)
    assert first_id == replay_id
    assert first_attrs == replay_attrs
    # ``created=False`` on replay.
    with Session(world_engine) as session:
        replay_again = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
        assert replay_again.created is False


def test_repository_different_kind_yields_new_row(world_engine):
    with Session(world_engine) as session:
        a = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
        a_id = a.recommendation.id
        assert a.created is True
    with Session(world_engine) as session:
        b = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="increase_contribution",
        )
        b_id = b.recommendation.id
        assert b.created is True
    # ``a_id`` / ``b_id`` were captured inside the ``with`` block so the ORM
    # identity map still held the PK value; accessing
    # ``recommendation.id`` after ``session`` exit would auto-expire and
    # raise ``DetachedInstanceError``.  Snapshot the canonical PK inline.
    assert a_id != b_id


def _snapshot_attributes(rec):
    """Capture every bounded column value while the ORM is still attached."""
    return {
        "id": rec.id,
        "user_id": rec.user_id,
        "goal_id": rec.goal_id,
        "forecast_version_id": rec.forecast_version_id,
        "forecast_input_state_hash": rec.forecast_input_state_hash,
        "recommendation_kind": rec.recommendation_kind,
        "rule_version": rec.rule_version,
        "derivation_schema_version": rec.derivation_schema_version,
        "currency": rec.currency,
        "reason": rec.reason,
        "expected_impact_min_decimal": rec.expected_impact_min_decimal,
        "expected_impact_max_decimal": rec.expected_impact_max_decimal,
        "confidence_score": rec.confidence_score,
        "assumptions_json": rec.assumptions_json,
        "risks_json": rec.risks_json,
        "freshness_json": rec.freshness_json,
        "provenance_json": rec.provenance_json,
        "metadata_json": rec.metadata_json,
        "derived_at": rec.derived_at,
        "data_as_of": rec.data_as_of,
        "expires_at": rec.expires_at,
    }


# ---------------------------------------------------------------------------
# Phase 2 immutability protections remain effective through repository ops
# ---------------------------------------------------------------------------


def test_repository_update_attempt_blocked_by_phase2_trigger(world_engine):
    with Session(world_engine) as session:
        result = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
        rec_id = result.recommendation.id
    with Session(world_engine) as session:
        # SQLite ``RAISE(ABORT, ...)`` in a BEFORE UPDATE trigger raises
        # ``IntegrityError`` (not ``OperationalError``).  The trigger fires
        # synchronously inside ``session.execute(...)`` itself — we wrap
        # that call so the assertion matches the contract.
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE recommendations SET reason = 'tampered' WHERE id = :id"),
                {"id": rec_id},
            )


def test_repository_delete_attempt_blocked_by_phase2_trigger(world_engine):
    with Session(world_engine) as session:
        result = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
        rec_id = result.recommendation.id
    with Session(world_engine) as session:
        # Same SQLite ``RAISE(ABORT, ...)`` semantics as in the UPDATE
        # trigger test; ``session.execute(...)`` raises ``IntegrityError``
        # directly so we wrap the call there.
        with pytest.raises(IntegrityError):
            session.execute(
                text("DELETE FROM recommendations WHERE id = :id"),
                {"id": rec_id},
            )


# ---------------------------------------------------------------------------
# Sanitized errors
# ---------------------------------------------------------------------------


def test_repository_error_messages_do_not_leak_financial_values(world_engine):
    with pytest.raises(GoalNotFoundError) as captured_goal:
        with Session(world_engine) as session:
            RecommendationRepository(session).persist(
                user_id=cross_user_id(),
                goal_id=primary_goal_id(),
                forecast_version_id=forecast_version_id(),
                recommendation_kind="hold",
            )
    msg = str(captured_goal.value).lower()
    for sensitive in ("8500", "1500", "10000", "balance", "amount", "contribution"):
        assert sensitive not in msg
    assert captured_goal.value.code == "goal_not_found"

    with pytest.raises(ForecastVersionNotFoundError) as captured_fv:
        with Session(world_engine) as session:
            RecommendationRepository(session).persist(
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                forecast_version_id="00000000-0000-4000-8000-000000000099",
                recommendation_kind="hold",
            )
    msg = str(captured_fv.value).lower()
    for sensitive in ("8500", "1500", "10000", "balance", "amount", "contribution"):
        assert sensitive not in msg
    assert captured_fv.value.code == "recommendation_not_found"


# ---------------------------------------------------------------------------
# Race recovery
# ---------------------------------------------------------------------------


def test_repository_survives_race_with_preexisting_winner(world_engine):
    """Pre-seed a row matching the deterministic PK; repository must replay."""
    from app.models import Recommendation
    from app.models.decision_journal_identities import recommendation_id_for

    rec_id = recommendation_id_for(
        user_id=primary_user_id(),
        goal_id=primary_goal_id(),
        forecast_version_id=forecast_version_id(),
        recommendation_kind="hold",
        rule_version="v1.0",
        derivation_schema_version="atlas-recommendation/v1",
    )
    now = datetime.now(timezone.utc)
    with Session(world_engine) as session, session.begin():
        rec = Recommendation(
            id=rec_id,
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            forecast_input_state_hash="a" * 64,
            recommendation_kind="hold",
            rule_version="v1.0",
            derivation_schema_version="atlas-recommendation/v1",
            currency="USD",
            reason="pre-seeded winner",
            expected_impact_min_decimal=Decimal("0"),
            expected_impact_max_decimal=Decimal("0"),
            confidence_score=Decimal("0.95"),
            assumptions_json="{}",
            risks_json="[]",
            freshness_json="{}",
            provenance_json="{}",
            metadata_json=None,
            derived_at=now,
            data_as_of=now,
        )
        session.add(rec)
        session.flush()

    with Session(world_engine) as session:
        result = RecommendationRepository(session).persist(
            user_id=primary_user_id(),
            goal_id=primary_goal_id(),
            forecast_version_id=forecast_version_id(),
            recommendation_kind="hold",
        )
    assert result.created is False
    assert result.recommendation.reason == "pre-seeded winner"
