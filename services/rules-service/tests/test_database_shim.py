"""Regression tests for ``app.database.register_sqlite_compat``.

Phase 8 ship target: pin the SQLite ``now()`` shim so a future refactor
of `app/database.py` or `alembic/env.py` can't silently disable the
fix that made fresh-DB SQLite migrations work.

Covers:

1. **Idempotency** — second call on the same engine does NOT register a
   second ``connect`` listener (per-engine ``_fc_sqlite_compat_registered``
   sentinel short-circuits).
2. **Emitted format** — the registered ``now()`` returns a ``YYYY-MM-DD HH:MM:SS.ffffff+00:00``
   string that round-trips via ``datetime.fromisoformat``.
3. **Postgres non-interference** — calling on a Postgres-dialect engine
   is a no-op (no listener registered at all).
4. **Live-write on a fresh SQLite DB** — a write that triggers
   ``server_default=now()`` lands a parseable timestamp, not the
   raw ``SERVER DEFAULT now()`` text.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text


def _list_connect_listeners(engine) -> list:
    """Snapshot the SQLAlchemy ``connect`` listeners for assertion.

    Not currently used; kept as a reference point for any future test
    that needs to introspect listeners. SQLAlchemy has no public API
    to enumerate all listeners for a target.
    """


def test_register_sqlite_compat_is_idempotent_on_same_engine(tmp_path: Path):
    """Calling twice does NOT register two ``connect`` listeners.

    SQLAlchemy's public API has no ``listener count`` introspection, so
    we assert idempotency via the sentinel short-circuit + behavior check:
    the sentinel stays True on the second call AND ``SELECT now()``
    still returns the shimmed ``+00:00`` form (proving the registered
    listener fired correctly without being inadvertently double-registered).
    """
    from app.database import register_sqlite_compat

    db_path = tmp_path / "idem.db"
    engine = create_engine(f"sqlite:///{db_path}")
    assert not getattr(engine, "_fc_sqlite_compat_registered", False), (
        "fresh engine should not have the idempotency sentinel"
    )
    register_sqlite_compat(engine)
    assert getattr(engine, "_fc_sqlite_compat_registered", False), (
        "first call should set the idempotency sentinel"
    )
    register_sqlite_compat(engine)
    assert getattr(engine, "_fc_sqlite_compat_registered", False), (
        "second call should preserve the idempotency sentinel"
    )
    with engine.connect() as conn:
        v = conn.execute(text("SELECT now()")).scalar()
    assert v.endswith("+00:00"), (
        f"second call must not have broken the listen path; now()={v!r}"
    )


def test_register_sqlite_compat_emits_parseable_utc_string(tmp_path: Path):
    """The registered ``now()`` returns ``datetime.now(timezone.utc).isoformat(sep=' ')``,
    parseable via ``datetime.fromisoformat`` (post-Python 3.11 syntax).
    """
    from app.database import register_sqlite_compat

    db_path = tmp_path / "shim.db"
    engine = create_engine(f"sqlite:///{db_path}")
    register_sqlite_compat(engine)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT now() AS t")).fetchone()
    value = row[0]
    # Format: "{YYYY-MM-DD HH:MM:SS.ffffff}+00:00"
    assert "T" not in value, f"now() should use space separator, got {value!r}"
    assert value.endswith("+00:00"), f"now() should carry +00:00 tz suffix, got {value!r}"
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, "now() must round-trip as a timezone-aware datetime"


def test_register_sqlite_compat_is_noop_on_postgres_dialect():
    """A Postgres engine is left completely unchanged \u2014 no listener registered."""
    from app.database import register_sqlite_compat

    engine = create_engine("postgresql://user:pw@localhost:5432/x")  # never connects
    assert engine.dialect.name == "postgresql"
    register_sqlite_compat(engine)
    assert not getattr(engine, "_fc_sqlite_compat_registered", False), (
        "register_sqlite_compat must NOT set the sentinel on Postgres engines"
    )


def test_server_default_now_yaml_round_trip_on_fresh_sqlite(tmp_path: Path):
    """End-to-end: simulate alembic's CREATE TABLE with ``server_default=now()``
    and confirm an INSERT lands a parseable timestamp literal (not raw text).
    Migrates the shim into the lightweight sqlite3 driver path so we can use
    ``now()`` in default expressions without alembic.
    """
    from app.database import register_sqlite_compat

    db_path = tmp_path / "x.db"
    engine = create_engine(f"sqlite:///{db_path}")
    register_sqlite_compat(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE t_demo (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT (now()))"
        ))
        conn.execute(text("INSERT INTO t_demo (id) VALUES (1)"))
        row = conn.execute(text("SELECT created_at FROM t_demo WHERE id = 1")).fetchone()

    value = row[0]
    # Must parse as timezone-aware datetime (the shim emits "+00:00" suffix).
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None

    # And it must be in a sensible recent window (not "0" or epoch).
    assert parsed.year >= 2024, f"created_at suspiciously old: {parsed}"
