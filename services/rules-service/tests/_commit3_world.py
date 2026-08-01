"""Phase 2 Slice 1 commit-3 test world helper.

Uses :func:`alembic.command.upgrade` (not ``Base.metadata.create_all``) so
the Phase 2 ``recommendations`` + ``decision_journal_entries``
immutability / ownership / format triggers ARE installed.  ``Base.metadata
.create_all`` does NOT install triggers, so any test that relies on
SQL-level UPDATE / DELETE rejection needs the alembic-upgraded engine.

Both commit-3 test modules import the ``world_engine`` and
``world_with_recommendation`` fixtures from here.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


# ``alembic/env.py`` unconditionally runs
#     config.set_main_option("sqlalchemy.url", settings.database_url)
# which would otherwise route every per-test alembic upgrade to the
# conftest-shared ``TEST_DATABASE_URL``.  We monkeypatch that attribute
# for the lifetime of each upgrade so the migrated database really is
# the per-test tmp sqlite file.  Imported lazily so we do not bind the
# helper to a specific Settings instance at module-import time.
from app.config import settings as _app_settings  # noqa: E402
from app.database import register_sqlite_compat  # noqa: E402


ROOT = Path(__file__).parent.parent
PHASE2_REVISION = "T8a1b2c3d4e5"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _upgrade_with_resolved_url(cfg: Config, url: str) -> None:
    """Run ``alembic upgrade head`` with the per-test URL surviving env.py.

    ``alembic/env.py`` calls
    ``config.set_main_option("sqlalchemy.url", settings.database_url)``
    unconditionally, which would otherwise redirect our per-test URL to
    the conftest-shared ``TEST_DATABASE_URL``.  We swap the application
    settings attribute for the duration of the upgrade so env.py hands
    alembic back to the URL we actually want.
    """
    original_url = _app_settings.database_url
    _app_settings.database_url = url
    try:
        command.upgrade(cfg, "head")
    finally:
        _app_settings.database_url = original_url


def _new_committed_world(url: str, *, recommendation_kind: str | None = None) -> Engine:
    """Apply the alembic migration + plant the minimal world rows.

    Inlines raw SQL so the test fixture never relies on the ORM
    ``__table_args__`` redundantly with the migration.  Returns the
    upgraded engine so the caller can attach ``StaticPool`` semantics
    if it needs to reuse a single connection across the test body.
    """
    _upgrade_with_resolved_url(_config(url), url)
    engine = create_engine(url)
    # SQLite needs the ``now()`` Python driver function registered on its
    # connect event so ``users.created_at`` (``server_default='now()')``)
    # and any other Postgres-style ``now()`` ``server_default`` succeeds
    # at INSERT time.  Alembic's pool attaches the shim, but our own
    # ``create_engine(url)`` builds a fresh engine without it.
    register_sqlite_compat(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    yesterday = now - timedelta(days=1)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, local_user_sub, email, hashed_password) "
            "VALUES (1, 'u1', 'u1@example.com', 'x')"
        ))
        conn.execute(text(
            "INSERT INTO users (id, local_user_sub, email, hashed_password) "
            "VALUES (2, 'u2', 'u2@example.com', 'x')"
        ))
        conn.execute(text(
            "INSERT INTO family_members (id, user_id, name, color, is_archived, is_self) "
            "VALUES (1, 1, 'Self', '#000', 0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO institutions (id, name) VALUES (1, 'Inst1')"
        ))
        conn.execute(text(
            "INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) "
            "VALUES (1, 1, 'Goal1', 10000.0, 0, 0)"
        ))
        conn.execute(text(
            "INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) "
            "VALUES (2, 1, 'Archived', 1.0, 0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) "
            "VALUES (3, 2, 'CrossGoal', 1.0, 0, 0)"
        ))
        conn.execute(text(
            "INSERT INTO forecasts (id, user_id, goal_id, forecast_kind, currency, "
            "lifecycle_state, latest_version_number) "
            "VALUES ('00000000-0000-4000-8000-000000000010', 1, 1, 'goal_projection', "
            "'USD', 'active', 0)"
        ))
        conn.execute(text(
            "INSERT INTO forecast_versions (id, forecast_id, version_number, "
            "input_state_hash, idempotency_key_hash, snapshot_schema_version, "
            "hash_schema_version, model_version, calculation_version, currency, "
            "calculated_at, data_as_of, max_data_age_days, data_age_days, "
            "input_snapshot_json, assumption_snapshot_json, output_snapshot_json, "
            "provenance_snapshot_json, ending_balance, target_gap) "
            "VALUES ('00000000-0000-4000-8000-000000000020', "
            "'00000000-0000-4000-8000-000000000010', 1, "
            ":h, :k, 'v1', 'v1', 'm', 'c', 'USD', :now, :yest, 30, 1, "
            "'{}', '{}', '{}', '{}', 0.0, 0.0)"
        ), {"h": "a" * 64, "k": "b" * 64, "now": now, "yest": yesterday})

        if recommendation_kind is not None:
            # Build a deterministic recommendation PK via the import-side helper.
            # NOTE: ``forecast_versions.forecast_id`` MUST match the
            # ``forecasts.id`` literal declared above; SQLite does not always
            # enforce raw-INSERT FKs so a typo here becomes a runtime mystery
            # when ``_authorize_forecast_version_ownership`` tries to walk
            # from ``ForecastVersion`` back to its parent ``Forecast``.
            from app.models.decision_journal_identities import recommendation_id_for
            rec_id = recommendation_id_for(
                user_id=1, goal_id=1,
                forecast_version_id="00000000-0000-4000-8000-000000000020",
                recommendation_kind=recommendation_kind,
                rule_version="v1.0",
                derivation_schema_version="atlas-recommendation/v1",
            )
            conn.execute(text(
                "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                "forecast_input_state_hash, recommendation_kind, rule_version, "
                "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                "expected_impact_max_decimal, confidence_score, assumptions_json, "
                "risks_json, freshness_json, provenance_json, derived_at, data_as_of) "
                "VALUES (:id, 1, 1, '00000000-0000-4000-8000-000000000020', :h, :k, "
                "'v1.0', 'atlas-recommendation/v1', 'USD', 'pre-seeded', 0.0, 0.0, 0.95, "
                "'{}', '[]', '{}', '{}', :now, :now)"
            ), {"id": rec_id, "h": "a" * 64, "k": recommendation_kind, "now": now})
    return engine


@pytest.fixture
def world_engine():
    """Alembic-upgraded SQLite world with users, goals, forecast, forecast_version."""
    tmp_dir = tempfile.mkdtemp(prefix="atlas_p2_commit3_")
    try:
        url = f"sqlite:///{os.path.join(tmp_dir, 'world.db')}"
        _new_committed_world(url, recommendation_kind=None)
        engine = create_engine(url, poolclass=StaticPool)
        register_sqlite_compat(engine)
        yield engine
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def world_with_recommendation():
    """Same as :func:`world_engine` but a recommendation row is pre-seeded."""
    tmp_dir = tempfile.mkdtemp(prefix="atlas_p2s1_commit3_withrec_")
    try:
        url = f"sqlite:///{os.path.join(tmp_dir, 'world.db')}"
        _new_committed_world(url, recommendation_kind="hold")
        engine = create_engine(url, poolclass=StaticPool)
        register_sqlite_compat(engine)
        yield engine
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def raw_idempotency_key():
    """Strong-but-bounded raw Idempotency-Key value used as a test default."""
    return "atlas-test-key-v1"


def recommendation_row_id() -> str:
    """The canonical recommendation id used by :func:`world_with_recommendation`."""
    from app.models.decision_journal_identities import recommendation_id_for
    return recommendation_id_for(
        user_id=1, goal_id=1,
        forecast_version_id="00000000-0000-4000-8000-000000000020",
        recommendation_kind="hold",
        rule_version="v1.0",
        derivation_schema_version="atlas-recommendation/v1",
    )


def forecast_version_id() -> str:
    return "00000000-0000-4000-8000-000000000020"


def cross_user_goal_id() -> int:
    return 3


def archived_goal_id() -> int:
    return 2


def primary_goal_id() -> int:
    return 1


def primary_user_id() -> int:
    return 1


def cross_user_id() -> int:
    return 2


__all__ = [
    "world_engine",
    "world_with_recommendation",
    "raw_idempotency_key",
    "recommendation_row_id",
    "forecast_version_id",
    "primary_goal_id",
    "archived_goal_id",
    "cross_user_goal_id",
    "primary_user_id",
    "cross_user_id",
]
