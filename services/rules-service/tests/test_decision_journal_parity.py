"""Cross-dialect parity coverage for the Phase 2 decision-journal substrate.

Goals:

* Lock the SQLite + PostgreSQL trigger × CHECK × FK parity in the additive
  Alembic migration (``T8a1b2c3d4e5``): both dialects must reject illegal
  mutations, accept the canonical shapes, and refuse downgrade once any
  Phase 2 substrate row exists.
* Lock the Round-trip / existing-data preservation guarantees so the
  Phase 1 immutable forecast history, the new ``recommendations`` table,
  and the new ``decision_journal_entries`` table all coexist following
  a single forward and reverse cycle.
* Lock the supported-dialect parity: assert that the migration source
  explicitly contains the PostgreSQL counterpart branches even when the
  test runner has no live PostgreSQL sidecar.

Mirrors :mod:`tests.test_forecast_migration` so the existing
``alembic upgrade`` + ``register_sqlite_compat`` patterns apply
out-of-the-box.
"""
from __future__ import annotations

import os
import tempfile
import uuid as _uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.database import register_sqlite_compat


ROOT = Path(__file__).parent.parent
PHASE1_PARENT = "S7a1b2c3d4e5"  # last head before this slice
PHASE2_REVISION = "T8a1b2c3d4e5"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _new_uuid(seed: int) -> str:
    # canonical lowercase format usable as forecast_version_id surrogate
    return str(_uuid.UUID(int=seed))


def _plant_world(engine, *, user_id: int = 1, goal_id: int = 1, fv_seed: int = 0x0000000140008000000000001) -> dict[str, str]:
    """Plant a User + Goal + Recommendations + DecisionJournalEntry world.

    Returns a dict of canonical UUIDs the test bodies can pin against.
    Mirrors the Phase 1 ``test_forecast_migration`` setup pattern.
    """
    fv_id = _new_uuid(fv_seed)
    rec_seed = (fv_seed << 4) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
    rec_id = _new_uuid(rec_seed + 0x10)
    journal_id = _new_uuid(rec_seed + 0x20)
    inputs = {
        "user": user_id,
        "goal": goal_id,
        "fv": fv_id,
        "rec": rec_id,
        "journal": journal_id,
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, local_user_sub, email, hashed_password) "
                "VALUES (:id, 'decision-journal-user', 'decision@example.com', 'x')"
            ),
            {"id": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) "
                "VALUES (:id, :user, 'Decision Goal', 1, 0, 0)"
            ),
            {"id": goal_id, "user": user_id},
        )
        rec_id_value = inputs["rec"]
        fv_id_value = inputs["fv"]
        journal_id_value = inputs["journal"]
        conn.execute(
            text(
                "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                "forecast_input_state_hash, recommendation_kind, rule_version, "
                "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                "expected_impact_max_decimal, confidence_score, assumptions_json, risks_json, "
                "freshness_json, provenance_json, derived_at, data_as_of) VALUES "
                "(:id, :user, :goal, :fv, :ish, 'increase_contribution', 'v1.0', "
                "'atlas-recommendation/v1', 'USD', 'increase monthly contribution', "
                "0, 100, 0.50, '{}', '{}', '{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": rec_id_value,
                "user": user_id,
                "goal": goal_id,
                "fv": fv_id_value,
                "ish": "a" * 64,
            },
        )
        conn.execute(
            text(
                "INSERT INTO decision_journal_entries (id, recommendation_id, user_id, goal_id, "
                "decision_action, schema_version, idempotency_key_hash, currency, note, decided_at) "
                "VALUES (:id, :rec, :user, :goal, 'accept', 'atlas-decision-journal/v1', "
                ":idem, 'USD', 'looking good', CURRENT_TIMESTAMP)"
            ),
            {
                "id": journal_id_value,
                "rec": rec_id_value,
                "user": user_id,
                "goal": goal_id,
                "idem": "b" * 64,
            },
        )
    return inputs


# ---------------------------------------------------------------------------
# SQLite migration round-trip + data preservation
# ---------------------------------------------------------------------------


def test_decision_journal_migration_upgrade_then_clean_downgrade_round_trip(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'decision_journal_roundtrip.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PHASE2_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        names = set(inspect(engine).get_table_names())
        assert {"recommendations", "decision_journal_entries"} <= names
        assert {"recommendations", "decision_journal_entries"}.issubset(names - {"alembic_version"})
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PHASE2_REVISION
        # clean downgrade must succeed because no Phase 2 rows exist
        command.downgrade(cfg, PHASE1_PARENT)
        names_after = set(inspect(engine).get_table_names())
        assert "recommendations" not in names_after
        assert "decision_journal_entries" not in names_after
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PHASE1_PARENT
        # re-upgrade should be a no-op data reset
        command.upgrade(cfg, PHASE2_REVISION)
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PHASE2_REVISION


def test_decision_journal_migration_preserves_phase_one_forecast_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'decision_journal_preserve.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PHASE1_PARENT)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (id, local_user_sub, email, hashed_password) "
                "VALUES (1, 'p1-user', 'p1@example.com', 'x')"
            ))
            conn.execute(text(
                "INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) "
                "VALUES (1, 1, 'P1 Goal', 1, 0, 0)"
            ))
            conn.execute(text(
                "INSERT INTO forecasts (id, user_id, goal_id) VALUES "
                "('00000000-0000-4000-8000-000000000001', 1, 1)"
            ))
        command.upgrade(cfg, PHASE2_REVISION)
        with engine.begin() as conn:
            # Phase 1 forecast row must survive
            assert conn.execute(text(
                "SELECT count(*) FROM forecasts WHERE id = '00000000-0000-4000-8000-000000000001'"
            )).scalar_one() == 1
            # Phase 2 tables exist
            assert conn.execute(text(
                "SELECT count(*) FROM recommendations"
            )).scalar_one() == 0
            assert conn.execute(text(
                "SELECT count(*) FROM decision_journal_entries"
            )).scalar_one() == 0


def test_decision_journal_downgrade_refuses_when_rows_exist(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'decision_journal_downgrade.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PHASE2_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        _plant_world(engine)
        with pytest.raises(RuntimeError, match="decision.journal substrate"):
            command.downgrade(cfg, PHASE1_PARENT)


# ---------------------------------------------------------------------------
# SQLite immutability / ownership / format triggers
# ---------------------------------------------------------------------------


def test_decision_journal_immutability_triggers_reject_update_and_delete(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'decision_journal_immutable.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PHASE2_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        ids = _plant_world(engine)
        with engine.begin() as conn:
            with pytest.raises(Exception):
                conn.execute(text(
                    "UPDATE recommendations SET reason = 'tampered' WHERE id = :id"
                ), {"id": ids["rec"]})
            with pytest.raises(Exception):
                conn.execute(text(
                    "DELETE FROM recommendations WHERE id = :id"
                ), {"id": ids["rec"]})
            with pytest.raises(Exception):
                conn.execute(text(
                    "UPDATE decision_journal_entries SET note = 'tampered' WHERE id = :id"
                ), {"id": ids["journal"]})
            with pytest.raises(Exception):
                conn.execute(text(
                    "DELETE FROM decision_journal_entries WHERE id = :id"
                ), {"id": ids["journal"]})


def test_decision_journal_ownership_trigger_rejects_cross_user_insert(monkeypatch):
    """Cross-user inserts against ``recommendations`` and ``decision_journal_entries``
    must fail closed at the trigger level even though the orchestrator-route
    layer also enforces it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'decision_journal_ownership.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PHASE2_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (id, local_user_sub, email, hashed_password) "
                "VALUES (1, 'owner-one', 'one@example.com', 'x')"
            ))
            conn.execute(text(
                "INSERT INTO users (id, local_user_sub, email, hashed_password) "
                "VALUES (2, 'owner-two', 'two@example.com', 'x')"
            ))
            conn.execute(text(
                "INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) "
                "VALUES (1, 1, 'Owner-one Goal', 1, 0, 0)"
            ))
            cross_user_rec = _new_uuid(0x0000000140008000000000099)
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                        "forecast_input_state_hash, recommendation_kind, rule_version, "
                        "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                        "expected_impact_max_decimal, confidence_score, assumptions_json, risks_json, "
                        "freshness_json, provenance_json, derived_at, data_as_of) VALUES "
                        "(:id, 2, 1, :fv, :ish, 'increase_contribution', 'v1.0', "
                        "'atlas-recommendation/v1', 'USD', 'tamper', 0, 100, 0.5, '{}', '{}', "
                        "'{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"id": cross_user_rec, "fv": _new_uuid(0x0000000140008000000000098), "ish": "c" * 64},
                )
            # plant a legitimate owner-one recommendation, then reject journal
            # insert from owner-two
            legit_rec = _new_uuid(0x0000000140008000000000100)
            conn.execute(
                text(
                    "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                    "forecast_input_state_hash, recommendation_kind, rule_version, "
                    "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                    "expected_impact_max_decimal, confidence_score, assumptions_json, risks_json, "
                    "freshness_json, provenance_json, derived_at, data_as_of) VALUES "
                    "(:id, 1, 1, :fv, :ish, 'increase_contribution', 'v1.0', "
                    "'atlas-recommendation/v1', 'USD', 'legit', 0, 100, 0.5, '{}', '{}', "
                    "'{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": legit_rec, "fv": _new_uuid(0x0000000140008000000000101), "ish": "d" * 64},
            )
            cross_user_journal = _new_uuid(0x0000000140008000000000200)
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO decision_journal_entries (id, recommendation_id, user_id, "
                        "goal_id, decision_action, schema_version, idempotency_key_hash, currency, "
                        "note, decided_at) VALUES (:id, :rec, 2, 1, 'accept', "
                        "'atlas-decision-journal/v1', :idem, 'USD', 'tamper', CURRENT_TIMESTAMP)"
                    ),
                    {"id": cross_user_journal, "rec": legit_rec, "idem": "e" * 64},
                )


def test_decision_journal_format_trigger_rejects_malformed_canonical_values(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'decision_journal_format.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PHASE2_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (id, local_user_sub, email, hashed_password) "
                "VALUES (1, 'fmt-user', 'fmt@example.com', 'x')"
            ))
            conn.execute(text(
                "INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) "
                "VALUES (1, 1, 'Format Goal', 1, 0, 0)"
            ))
            fv = _new_uuid(0x0000000140008000000000300)
            # bad UUID on recommendation.id is rejected
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                        "forecast_input_state_hash, recommendation_kind, rule_version, "
                        "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                        "expected_impact_max_decimal, confidence_score, assumptions_json, risks_json, "
                        "freshness_json, provenance_json, derived_at, data_as_of) VALUES "
                        "('not-a-uuid', 1, 1, :fv, :ish, 'increase_contribution', 'v1.0', "
                        "'atlas-recommendation/v1', 'USD', 'r', 0, 100, 0.5, '{}', '{}', "
                        "'{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"fv": fv, "ish": "f" * 64},
                )
            # uppercase SHA-256 hex on forecast_input_state_hash is rejected
            bad_id = _new_uuid(0x0000000140008000000000301)
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                        "forecast_input_state_hash, recommendation_kind, rule_version, "
                        "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                        "expected_impact_max_decimal, confidence_score, assumptions_json, risks_json, "
                        "freshness_json, provenance_json, derived_at, data_as_of) VALUES "
                        "(:id, 1, 1, :fv, :ish, 'increase_contribution', 'v1.0', "
                        "'atlas-recommendation/v1', 'USD', 'r', 0, 100, 0.5, '{}', '{}', "
                        "'{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"id": bad_id, "fv": fv, "ish": "F" * 64},
                )


# ---------------------------------------------------------------------------
# Supported-dialect parity: structural assertions on the migration source
# ---------------------------------------------------------------------------


def test_decision_journal_migration_postgres_branches_explicitly_present():
    """The migration must independently guard Postgres because Phase 1
    established the same protocol (``test_postgresql_currency_constraint_explicitly_rejects_partial_null_provenance``).
    """
    migration = (ROOT / f"alembic/versions/{PHASE2_REVISION}_add_decision_journal_substrate.py").read_text(encoding="utf-8")
    assert "def upgrade" in migration
    assert "def downgrade" in migration
    # SQLite immutability triggers
    assert "CREATE TRIGGER recommendations_no_update" in migration
    assert "CREATE TRIGGER recommendations_no_delete" in migration
    assert "CREATE TRIGGER decision_journal_entries_no_update" in migration
    assert "CREATE TRIGGER decision_journal_entries_no_delete" in migration
    # Postgres immutability function + triggers
    assert "reject_recommendation_mutation" in migration
    assert "reject_decision_journal_mutation" in migration
    assert 'dialect.name == "postgresql"' in migration
    assert "LANGUAGE plpgsql" in migration
    # Ownership triggers on both dialects
    assert "forecasts_goal_owner" in migration or "enforce_recommendation_goal_owner" in migration
    # Format guards on both dialects (UUID + lowercase SHA-256)
    assert "GLOB" in migration  # SQLite branch
    # Postgres CHECK constraints use the ``~`` POSIX-regex positive-match
    # operator (not ``!~``) for canonical-shape validation.
    assert "~ '^[0-9a-f]" in migration
    # Format guard canonical-shape asserts
    assert "0123456789abcdef" in migration or "0-9a-f" in migration
    # Currency check: fail-closed to USD
    assert "'USD'" in migration
    # Idempotency: refuse downgrade with data
    assert "decision.journal substrate" in migration.lower()


def test_decision_journal_models_registered_in_app_models_init():
    init_text = (ROOT / "app" / "models" / "__init__.py").read_text(encoding="utf-8")
    assert "Recommendation" in init_text
    assert "DecisionJournalEntry" in init_text
    assert "from app.models.recommendation import Recommendation" in init_text
    assert "from app.models.decision_journal_entry import DecisionJournalEntry" in init_text
