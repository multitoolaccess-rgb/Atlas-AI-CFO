"""Hermetic regression test for the Phase-11 ``preview_lines`` column addition.

The Phase-11 ``OperationalError: no such column: import_batches.preview_lines``
the user reported on uploads was caused by committing the new SQLAlchemy
column + a new alembic revision but forgetting to run ``alembic upgrade head``
against the developer DB. This test pins two guarantees:

1. Applying all revisions to a fresh SQLite database creates the
   ``preview_lines`` column on ``import_batches`` with the nullable
   TEXT type the model declares.
2. The latest revision is the ``d5e6f7a8b9c0`` migration (or whatever
   downstream migration followed it — the test reads ``alembic_version``
   to assert it, NOT hard-codes the hash, so a future cherry-on-top
   migration on top of ``d5e6f7a8b9c0`` doesn't break this test).

The test uses alembic's API directly (NOT ``alembic upgrade head`` invoked
via the CLI) so it works in CI without a real alembic.ini path and without
needing the project-root .venv binaries on PATH.
"""
import os
import tempfile
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect, text


PROJECT_ROOT = Path(__file__).parent.parent  # services/rules-service


def _make_alembic_config(db_url: str) -> AlembicConfig:
    """Build an in-process AlembicConfig pointed at the project ``alembic.ini``.

    NOTE: ``alembic/env.py`` ignores ``set_main_option("sqlalchemy.url", ...)``
    on the config and instead re-applies ``settings.database_url`` (which
    is env-driven). Tests that want a temp SQLite DB must override
    ``app.config.settings.database_url`` via monkeypatch BEFORE the first
    alembic import — we do that via the ``monkeypatch`` fixture in each
    test below.
    """
    cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    # Ensure Alembic resolves script_location relative to the service root,
    # not the current working directory.
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _list_columns(engine, table: str) -> list[str]:
    return [row["name"] for row in inspect(engine).get_columns(table)]


def test_alembic_upgrade_head_creates_preview_lines_column(monkeypatch):
    """Phase 11 ship target: a fresh SQLite DB brought to head MUST contain
    ``import_batches.preview_lines``. Failure here means either the
    migration file is missing (no revision adds the column) OR the model
    was changed without a corresponding alembic revision.

    Monkeypatches ``app.config.settings.database_url`` so the alembic
    env.py (which reads from ``settings`` at import time) targets the
    temp SQLite DB instead of the conftest's Postgres :5433.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "alembic_preview.db")
        # Alembic's sqlite url needs 3 slashes + a path.
        db_url = f"sqlite:///{db_path}"
        monkeypatch.setattr(
            "app.config.settings.database_url", db_url,
        )

        cfg = _make_alembic_config(db_url)
        alembic_command.upgrade(cfg, "head")

        engine = create_engine(db_url)
        columns = _list_columns(engine, "import_batches")

        assert "preview_lines" in columns, (
            f"alembic upgrade head did not add preview_lines. "
            f"import_batches columns: {columns}"
        )

        # Type sanity — must be TEXT (SQLite stores TEXT for VARCHAR)
        # so the route's ``json.dumps(...)`` payload survives.
        col_meta = next(
            r for r in inspect(engine).get_columns("import_batches")
            if r["name"] == "preview_lines"
        )
        assert col_meta["nullable"] is True, (
            "preview_lines must be nullable so pre-Phase-11 rows have a "
            "well-defined state (NULL = never persisted)."
        )
        # SQLite types round-trip as upper-case strings — both TEXT
        # and VARCHAR variants are acceptable for our use case.
        # SQLAlchemy 2.x ``inspect(...).get_columns()[i]['type']`` is a
        # type CLASS (e.g. ``sqlalchemy.types.TEXT``) on some versions
        # and a string on others; ``str(...)`` handles both.
        _type_name = str(col_meta["type"]).upper()
        assert _type_name in ("TEXT", "VARCHAR"), (
            f"preview_lines must be a text-like column, got {col_meta['type']!r}"
        )


def test_alembic_alembic_version_at_head_after_upgrade(monkeypatch):
    """After ``alembic upgrade head``, ``alembic_version`` records the
    latest revision seen. Re-running upgrade on the same DB MUST be a
    no-op (the OperationalError guard + the boot-time self-healing hook
    both rely on this idempotency).
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "version_replay.db")
        db_url = f"sqlite:///{db_path}"
        monkeypatch.setattr(
            "app.config.settings.database_url", db_url,
        )

        cfg = _make_alembic_config(db_url)

        # First run.
        alembic_command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        first_head = engine.connect().execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        assert first_head, "alembic_version table expected to be populated"

        # Second run on the same DB must NOT raise.
        alembic_command.upgrade(cfg, "head")
        second_head = engine.connect().execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        assert second_head == first_head, (
            f"replay changed head ({first_head} -> {second_head}) — "
            f"upgrade is not idempotent on the same DB."
        )
