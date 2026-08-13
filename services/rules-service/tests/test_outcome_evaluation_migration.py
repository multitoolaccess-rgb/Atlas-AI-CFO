"""Migration and dialect-parity tests for the outcome evaluation substrate.

Mirrors :mod:`tests.test_forecast_migration` and
:mod:`tests.test_decision_journal_parity` so the hermetic SQLite bootstrap
protocol applies out-of-the-box: every test boots a tempfile SQLite database,
runs ``alembic upgrade`` to ``U9a1b2c3d4e5``, plants a deterministic world, and
asserts the migration's triggers + CHECK constraints behave.

Coverage:

* Upgrade creates the table with all constraints; downgrade refuses once any
  row exists (immutable history).
* Immutability triggers block UPDATE and DELETE (SQLite + structural Postgres
  parity).
* Ownership triggers enforce ``user_id`` matches the owner of the goal,
  recommendation, and decision journal entry.
* Format triggers reject canonical-shape violations (allowlisted enums,
  lowercase SHA-256 hex, lifecycle states).
* Lifecycle-state evidence contract: ``measured`` requires all evidence fields,
  ``pending``/``not_yet_measurable`` forbid them.
* Privacy contract: ``evidence_source_kind`` allowlist + hash-only
  ``evidence_reference_hash`` (a raw URL is rejected).
* Idempotent replay: same idempotency_key_hash collapses onto one row.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import register_sqlite_compat
from app.models import (
    DecisionJournalEntry,
    Forecast,
    ForecastVersion,
    Goal,
    OutcomeEvaluation,
    Recommendation,
    User,
)
from app.models.decision_journal_identities import (
    canonical_idempotency_key_hash,
    decision_journal_id_for,
    outcome_evaluation_id_for,
    recommendation_id_for,
)


ROOT = Path(__file__).resolve().parent.parent
PHASE2_REVISION = "T8a1b2c3d4e5"  # decision-journal substrate
OUTCOME_REVISION = "U9a1b2c3d4e5"  # this slice (head)


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def engine(monkeypatch):
    """Hermetic SQLite database upgraded to the outcome-evaluation head."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'outcome_evaluation.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        command.upgrade(_config(url), OUTCOME_REVISION)
        eng = create_engine(url)
        register_sqlite_compat(eng)
        yield eng


# ---------------------------------------------------------------------------
# World + outcome builders (deterministic; local to this file)
# ---------------------------------------------------------------------------


def _plant_world(session: Session, *, local_user_sub: str, email: str) -> dict[str, int | str]:
    """Plant one user + goal + forecast + version + recommendation + accepted decision.

    Returns the planted ids as ``{"user", "goal", "recommendation", "decision"}``
    so test bodies can pin against the deterministic canonical identities.
    """
    user = User(
        local_user_sub=local_user_sub,
        email=email,
        hashed_password="x",
        full_name="Outcome User",
    )
    session.add(user)
    session.flush()

    goal = Goal(user_id=user.id, name="Outcome Goal", target_amount=10000.0, priority=0)
    session.add(goal)
    session.flush()

    forecast = Forecast(
        id="00000000-0000-4000-8000-000000000001",
        user_id=user.id,
        goal_id=goal.id,
        forecast_kind="goal_projection",
        currency="USD",
        lifecycle_state="active",
        latest_version_number=1,
    )
    session.add(forecast)
    session.flush()

    fv = ForecastVersion(
        id="00000000-0000-4000-8000-000000000002",
        forecast_id=forecast.id,
        version_number=1,
        input_state_hash="a" * 64,
        idempotency_key_hash="b" * 64,
        snapshot_schema_version="forecast/v1",
        hash_schema_version="forecast/v1",
        model_version="model/v1",
        calculation_version="calc/v1",
        currency="USD",
        calculated_at=datetime.now(timezone.utc),
        data_as_of=datetime.now(timezone.utc),
        max_data_age_days=30,
        data_age_days=0,
        input_snapshot_json="{}",
        assumption_snapshot_json="{}",
        output_snapshot_json="{}",
        provenance_snapshot_json="{}",
        ending_balance=Decimal("10000.00"),
        target_gap=Decimal("0.00"),
    )
    session.add(fv)
    session.flush()

    rec_id = recommendation_id_for(
        user_id=user.id,
        goal_id=goal.id,
        forecast_version_id=fv.id,
        recommendation_kind="increase_savings",
        rule_version="v1",
        derivation_schema_version="recommendation/v1",
    )
    rec = Recommendation(
        id=rec_id,
        user_id=user.id,
        goal_id=goal.id,
        forecast_version_id=fv.id,
        forecast_input_state_hash=fv.input_state_hash,
        recommendation_kind="increase_savings",
        rule_version="v1",
        derivation_schema_version="recommendation/v1",
        currency="USD",
        reason="Test recommendation",
        expected_impact_min_decimal=Decimal("100.00"),
        expected_impact_max_decimal=Decimal("200.00"),
        confidence_score=Decimal("0.75"),
        assumptions_json="{}",
        risks_json="{}",
        freshness_json="{}",
        provenance_json="{}",
        derived_at=datetime.now(timezone.utc),
        data_as_of=datetime.now(timezone.utc),
    )
    session.add(rec)
    session.flush()

    idem = canonical_idempotency_key_hash("test-decision-accept-001")
    decision_id = decision_journal_id_for(
        user_id=user.id,
        goal_id=goal.id,
        recommendation_id=rec.id,
        decision_action="accept",
        idempotency_key_hash=idem,
        schema_version="decision/v1",
    )
    decision = DecisionJournalEntry(
        id=decision_id,
        recommendation_id=rec.id,
        user_id=user.id,
        goal_id=goal.id,
        decision_action="accept",
        schema_version="decision/v1",
        idempotency_key_hash=idem,
        currency="USD",
        decided_at=datetime.now(timezone.utc),
    )
    session.add(decision)

    return {"user": user.id, "goal": goal.id, "recommendation": rec.id, "decision": decision.id}


@pytest.fixture
def world(engine) -> dict[str, int | str]:
    with Session(engine) as session, session.begin():
        return _plant_world(session, local_user_sub="outcome-user", email="outcome@example.com")


def _new_outcome(
    session: Session,
    *,
    world: dict[str, int | str],
    lifecycle: str,
    idempotency_key_hash: str,
    evidence_source_kind: str | None = None,
    evidence_reference_hash: str | None = None,
    measurement_window_start=None,
    measurement_window_end=None,
    result_json: str | None = None,
    confidence: str | None = None,
    explanation: str | None = None,
    flush: bool = True,
) -> OutcomeEvaluation:
    """Build + add an ``OutcomeEvaluation`` with a deterministic canonical id."""
    eval_id = outcome_evaluation_id_for(
        user_id=world["user"],
        goal_id=world["goal"],
        recommendation_id=world["recommendation"],
        decision_journal_entry_id=world["decision"],
        lifecycle=lifecycle,
        idempotency_key_hash=idempotency_key_hash,
        schema_version="outcome-evaluation/v1",
    )
    ev = OutcomeEvaluation(
        id=eval_id,
        recommendation_id=world["recommendation"],
        decision_journal_entry_id=world["decision"],
        user_id=world["user"],
        goal_id=world["goal"],
        lifecycle=lifecycle,
        schema_version="outcome-evaluation/v1",
        idempotency_key_hash=idempotency_key_hash,
        currency="USD",
        evidence_source_kind=evidence_source_kind,
        evidence_reference_hash=evidence_reference_hash,
        measurement_window_start=measurement_window_start,
        measurement_window_end=measurement_window_end,
        result_json=result_json,
        confidence=confidence,
        explanation=explanation,
        recorded_at=datetime.now(timezone.utc),
    )
    session.add(ev)
    if flush:
        session.flush()
    return ev


# ---------------------------------------------------------------------------
# Lifecycle-state evidence contract
# ---------------------------------------------------------------------------


def test_pending_outcome_accepts_no_evidence_fields(engine, world):
    with Session(engine) as session, session.begin():
        ev = _new_outcome(
            session,
            world=world,
            lifecycle="pending",
            idempotency_key_hash=canonical_idempotency_key_hash("pending-001"),
        )
        assert ev.lifecycle == "pending"
        assert ev.evidence_source_kind is None
        assert ev.evidence_reference_hash is None
        assert ev.measurement_window_start is None
        assert ev.measurement_window_end is None
        assert ev.result_json is None
        assert ev.confidence is None
        assert ev.explanation is None


def test_measured_outcome_requires_all_evidence_fields(engine, world):
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        ev = _new_outcome(
            session,
            world=world,
            lifecycle="measured",
            idempotency_key_hash=canonical_idempotency_key_hash("measured-001"),
            evidence_source_kind="account_balance_delta",
            evidence_reference_hash="a" * 64,
            measurement_window_start=now,
            measurement_window_end=now,
            result_json='{"delta_usd": "150.00"}',
            confidence="high",
            explanation="Account balance increased by $150 in measurement window",
        )
        assert ev.lifecycle == "measured"
        assert ev.evidence_source_kind == "account_balance_delta"
        assert ev.evidence_reference_hash == "a" * 64
        assert ev.measurement_window_start is not None
        assert ev.measurement_window_end is not None
        assert ev.result_json is not None
        assert ev.confidence == "high"
        assert ev.explanation is not None


def test_measured_without_evidence_source_kind_rejects(engine, world):
    """Measured outcome missing ``evidence_source_kind`` violates the lifecycle contract."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        _new_outcome(
            session,
            world=world,
            lifecycle="measured",
            idempotency_key_hash=canonical_idempotency_key_hash("bad-measured-001"),
            evidence_source_kind=None,
            evidence_reference_hash="a" * 64,
            measurement_window_start=now,
            measurement_window_end=now,
            result_json='{"delta_usd": "150.00"}',
            confidence="high",
            explanation="Test",
            flush=False,
        )
        with pytest.raises(IntegrityError, match="lifecycle_evidence"):
            session.flush()


def test_pending_with_evidence_fields_rejects(engine, world):
    """Pending outcome carrying evidence fields violates the lifecycle contract."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        _new_outcome(
            session,
            world=world,
            lifecycle="pending",
            idempotency_key_hash=canonical_idempotency_key_hash("bad-pending-001"),
            evidence_source_kind="account_balance_delta",
            evidence_reference_hash="a" * 64,
            measurement_window_start=now,
            measurement_window_end=now,
            result_json='{"delta_usd": "150.00"}',
            confidence="high",
            explanation="Test",
            flush=False,
        )
        with pytest.raises(IntegrityError, match="lifecycle_evidence"):
            session.flush()


# ---------------------------------------------------------------------------
# Privacy contract: evidence_source_kind allowlist + hash-only reference
# ---------------------------------------------------------------------------


def test_invalid_evidence_source_kind_rejects(engine, world):
    """Non-allowlisted ``evidence_source_kind`` violates the privacy contract."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        _new_outcome(
            session,
            world=world,
            lifecycle="measured",
            idempotency_key_hash=canonical_idempotency_key_hash("bad-source-001"),
            evidence_source_kind="raw_transaction_url",  # not allowlisted
            evidence_reference_hash="a" * 64,
            measurement_window_start=now,
            measurement_window_end=now,
            result_json='{"delta_usd": "150.00"}',
            confidence="high",
            explanation="Test",
            flush=False,
        )
        with pytest.raises(IntegrityError, match="evidence_source_kind"):
            session.flush()


def test_non_hash_evidence_reference_rejects(engine, world):
    """Non-hash ``evidence_reference_hash`` (e.g. a raw URL) violates the privacy contract."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        _new_outcome(
            session,
            world=world,
            lifecycle="measured",
            idempotency_key_hash=canonical_idempotency_key_hash("bad-ref-001"),
            evidence_source_kind="account_balance_delta",
            evidence_reference_hash="https://example.com/transaction/123",  # not a hash
            measurement_window_start=now,
            measurement_window_end=now,
            result_json='{"delta_usd": "150.00"}',
            confidence="high",
            explanation="Test",
            flush=False,
        )
        with pytest.raises(IntegrityError, match="evidence_reference_hash"):
            session.flush()


# ---------------------------------------------------------------------------
# Immutability + ownership triggers
# ---------------------------------------------------------------------------


def test_immutability_blocks_update(engine, world):
    with Session(engine) as session, session.begin():
        ev = _new_outcome(
            session,
            world=world,
            lifecycle="pending",
            idempotency_key_hash=canonical_idempotency_key_hash("immutable-update"),
        )
        eval_id = ev.id
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match="immutable"):
            conn.execute(
                text(
                    "UPDATE outcome_evaluations SET lifecycle = 'not_yet_measurable' "
                    "WHERE id = :id"
                ),
                {"id": eval_id},
            )


def test_immutability_blocks_delete(engine, world):
    with Session(engine) as session, session.begin():
        ev = _new_outcome(
            session,
            world=world,
            lifecycle="pending",
            idempotency_key_hash=canonical_idempotency_key_hash("immutable-delete"),
        )
        eval_id = ev.id
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match="immutable"):
            conn.execute(text("DELETE FROM outcome_evaluations WHERE id = :id"), {"id": eval_id})


def test_outcome_evaluation_ownership_trigger_rejects_cross_user_insert(engine):
    """Cross-user insert must fail at the trigger level, not just the route layer."""
    with Session(engine) as session, session.begin():
        world = _plant_world(session, local_user_sub="owner-a", email="a@example.com")
        other = User(local_user_sub="owner-b", email="b@example.com", hashed_password="x")
        session.add(other)
        session.flush()
        other_id = other.id

    idem = canonical_idempotency_key_hash("cross-user-attempt")
    eval_id = outcome_evaluation_id_for(
        user_id=other_id,
        goal_id=world["goal"],
        recommendation_id=world["recommendation"],
        decision_journal_entry_id=world["decision"],
        lifecycle="pending",
        idempotency_key_hash=idem,
        schema_version="outcome-evaluation/v1",
    )
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match="own"):
            conn.execute(
                text(
                    "INSERT INTO outcome_evaluations "
                    "(id, recommendation_id, decision_journal_entry_id, user_id, goal_id, "
                    "lifecycle, schema_version, idempotency_key_hash, currency, recorded_at) "
                    "VALUES (:id, :rec, :decision, :user, :goal, 'pending', "
                    "'outcome-evaluation/v1', :idem, 'USD', CURRENT_TIMESTAMP)"
                ),
                {
                    "id": eval_id,
                    "rec": world["recommendation"],
                    "decision": world["decision"],
                    "user": other_id,
                    "goal": world["goal"],
                    "idem": idem,
                },
            )


# ---------------------------------------------------------------------------
# Idempotent replay semantics
# ---------------------------------------------------------------------------


def test_idempotency_replay_returns_existing_row(engine, world):
    """Same idempotency_key_hash + identical inputs resolve to the same row."""
    idem = canonical_idempotency_key_hash("test-replay-001")
    with Session(engine) as session, session.begin():
        _new_outcome(session, world=world, lifecycle="pending", idempotency_key_hash=idem)

    eval_id_1 = outcome_evaluation_id_for(
        user_id=world["user"],
        goal_id=world["goal"],
        recommendation_id=world["recommendation"],
        decision_journal_entry_id=world["decision"],
        lifecycle="pending",
        idempotency_key_hash=idem,
        schema_version="outcome-evaluation/v1",
    )
    eval_id_2 = outcome_evaluation_id_for(
        user_id=world["user"],
        goal_id=world["goal"],
        recommendation_id=world["recommendation"],
        decision_journal_entry_id=world["decision"],
        lifecycle="pending",
        idempotency_key_hash=idem,
        schema_version="outcome-evaluation/v1",
    )
    assert eval_id_1 == eval_id_2

    # Duplicate INSERT of the same deterministic PK violates the UNIQUE constraint.
    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            _new_outcome(session, world=world, lifecycle="pending", idempotency_key_hash=idem)
        session.rollback()


# ---------------------------------------------------------------------------
# Migration round-trip + supported-dialect parity (structural)
# ---------------------------------------------------------------------------


def test_outcome_evaluation_migration_upgrade_creates_table(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'outcome_create.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        command.upgrade(_config(url), OUTCOME_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        names = set(inspect(engine).get_table_names())
        assert "outcome_evaluations" in names
        assert (
            engine.connect()
            .execute(text("SELECT version_num FROM alembic_version"))
            .scalar_one()
            == OUTCOME_REVISION
        )
        cols = {c["name"] for c in inspect(engine).get_columns("outcome_evaluations")}
        assert {
            "evidence_source_kind",
            "evidence_reference_hash",
            "lifecycle",
            "idempotency_key_hash",
            "recorded_at",
        } <= cols


def test_outcome_evaluation_downgrade_refuses_when_rows_exist(monkeypatch):
    """Downgrade must refuse once immutable history exists."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'outcome_downgrade.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        command.upgrade(_config(url), OUTCOME_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with Session(engine) as session, session.begin():
            world = _plant_world(session, local_user_sub="downgrade-user", email="downgrade@example.com")
            _new_outcome(
                session,
                world=world,
                lifecycle="pending",
                idempotency_key_hash=canonical_idempotency_key_hash("downgrade-row"),
            )
        with pytest.raises(RuntimeError, match="Downgrade refused"):
            command.downgrade(_config(url), PHASE2_REVISION)


def test_outcome_evaluation_migration_postgres_branches_explicitly_present():
    """The migration must independently guard Postgres (Phase 1 protocol)."""
    migration = (
        ROOT / f"alembic/versions/{OUTCOME_REVISION}_add_outcome_evaluations.py"
    ).read_text(encoding="utf-8")
    assert "def upgrade" in migration
    assert "def downgrade" in migration
    # SQLite immutability triggers
    assert "CREATE TRIGGER outcome_evaluations_no_update" in migration
    assert "CREATE TRIGGER outcome_evaluations_no_delete" in migration
    # Postgres immutability function + triggers
    assert "reject_outcome_evaluation_mutation" in migration
    assert 'dialect.name == "postgresql"' in migration
    assert "LANGUAGE plpgsql" in migration
    # Ownership triggers on both dialects
    assert "outcome_evaluations_owner_insert" in migration
    assert "enforce_outcome_evaluation_owners" in migration
    # Format guards on both dialects (UUID + lowercase SHA-256)
    assert "GLOB" in migration  # SQLite branch
    assert "~ '^[0-9a-f]" in migration  # Postgres positive-match POSIX regex
    # Allowlisted enums + fail-closed currency
    assert "'forecast_projection'" in migration
    assert "'account_balance_delta'" in migration
    assert "'transaction_pattern'" in migration
    assert "'USD'" in migration
    # Immutable-history downgrade refusal
    assert "Downgrade refused" in migration
