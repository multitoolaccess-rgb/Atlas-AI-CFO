"""SQLAlchemy engine, session factory, and FastAPI dependency.

Lift provenance: essentially verbatim from the legacy WealthIQ database module
in Phase 2 of the merge plan (``docs/wealthiq-merge-plan.md`` §4 — Reuse Map,
item 2). The original filename was ``db.py``; renamed to ``database.py`` per
the new bounded-context map in ``docs/architecture.md`` §3.

One editing pass:

- ``pool_pre_ping=True`` added to ``create_engine``. Postgres in dev frequently
  serves stale TCP-sessions (e.g., laptop sleep + DNS renewal); without
  ``pool_pre_ping`` the first request after resume raises ``OperationalError``
  to the client. ``pool_pre_ping`` issues a cheap ``SELECT 1`` before each
  checkout and transparently reopens a broken connection.

Phase 8 update: extracted the SQLite ``now()`` shim into a public
``register_sqlite_compat(engine)`` helper so ``alembic/env.py`` can call it
on the alembic-built engine too (fresh-DB ``alembic upgrade head`` against
SQLite no longer trips on canonical Postgres defaults). Replaced
``datetime.utcnow()`` with ``datetime.now(timezone.utc)`` + ``.isoformat()``
now carries a ``+00:00`` suffix matching Postgres ``now()`` semantics.
"""
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def register_sqlite_compat(engine) -> None:
    """Register dialect-compat helpers on a SQLite engine.

    Postgres' ``now()`` returns a timestamptz; SQLite has no equivalent.
    Some lifted migrations reference ``now()`` directly (e.g.
    ``server_default=sa.text('now()')`` on ``users.updated_at``). Without
    this shim, dev / CI / e2e runs against SQLite 500 on first write.

    The shim emits a timezone-aware UTC string (``YYYY-MM-DD HH:MM:SS.ffffff+00:00``)
    so Postgres and SQLite rows sort and compare identically.

    Strict-guards on dialect: a non-SQLite ``engine.dialect.name`` short-
    circuits BEFORE registering any listener (Postgres engines therefore
    have no extra connect-listener overhead). Idempotent on the same engine
    via the per-engine ``_fc_sqlite_compat_registered`` sentinel; test
    fixtures that spin the same engine up multiple times don't double-register.
    """
    if engine.dialect.name != "sqlite":
        return
    if getattr(engine, "_fc_sqlite_compat_registered", False):
        return

    @event.listens_for(engine, "connect")
    def _register(dbapi_connection, connection_record):
        # Phase-F5+ concurrency hardening — start.sh runs ``alembic upgrade
        # head`` against the same shared SQLite DB at the same moment
        # Finlynq's ``_recalculate_account_balances`` startup hook is
        # mid-write. Without busy_timeout the SQLite write lock raises
        # ``OperationalError: database is locked`` on cold boot and the
        # user sees a misleading "alembic failed" rather than the real
        # race condition. WAL journal mode lets readers + writers operate
        # concurrently with one writer at a time.
        #
        # BEHAVIOUR NOTES for future operators:
        #   * busy_timeout=30s is intentionally long to absorb the
        #     documented start.sh alembic+recalc race (real contention
        #     is <100ms). A genuine deadlock is more usefully surfaced in
        #     logs by a longer wait than by a fast raise.
        #   * journal_mode=WAL is persistent across connections; a
        #     future ``cp finance.db backup.db`` or
        #     ``os.replace(finance.db, ...)`` will silently produce an
        #     INCONSISTENT snapshot because the -wal and -shm siblings
        #     hold uncommitted deltas. Any future DB-snapshot tooling
        #     MUST run ``PRAGMA wal_checkpoint(TRUNCATE)`` first, or
        #     copy all three files (db + wal + shm) atomically.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
        dbapi_connection.create_function(
            "now",
            0,
            lambda: datetime.now(timezone.utc).isoformat(sep=" "),
        )

    engine._fc_sqlite_compat_registered = True


# Engine. `pool_pre_ping` issues a cheap SELECT 1 before each checkout so that
# stale connections (server-side timeouts, laptop sleep, restart) don't surface
# as 500s to API clients.
engine = create_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

# Register the SQLite `now()` shim on the live app engine. ``alembic/env.py``
# calls this again on the alembic-built engine so migrations on fresh DBs
# succeed the same way.
register_sqlite_compat(engine)

# Session factory.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# New-style DeclarativeBase (SQLAlchemy 2.0+ idiom; supersedes the legacy
# `declarative_base()` factory function lifted from wealthiq's `db.py`).
# Trade-off vs the lift: `class Base(DeclarativeBase): pass` is 5 lines
# instead of 1, but it makes ``issubclass(Base, DeclarativeBase)`` work
# (which the wealthiq legacy factory does not), and it's the API Phase 3
# model files will need anyway.
class Base(DeclarativeBase):
    pass


# Phase 3 critical — ``import app.models`` MUST live AFTER
# ``class Base(DeclarativeBase)`` is defined. Earlier placement (top-of-file
# imports for example) triggers a circular import: ``app.models.user`` does
# ``from app.database import Base``, and Python's partial-module mechanism
# raises ``ImportError: cannot import name 'Base' from partially initialized
# module 'app.database'`` because ``Base`` hasn't been bound in the parent
# module's namespace yet.
#
# Once placed here, the import charges ``Base.metadata`` with every lifted
# SQLAlchemy class. Any importer of ``app.database`` (tests, alembic env.py,
# FastAPI startup, scripts) now sees a fully-populated metadata, and
# ``Base.metadata.tables`` lookups + alembic autogenerate-diff passes work.
#
# The same import also lives in ``alembic/env.py`` as belt-and-braces (env.py
# runs in a subprocess that some future refactor could break away from
# this import being a hard dependency).
import app.models  # noqa: E402,F401


def get_db():
    """FastAPI dependency yielding a SQLAlchemy Session; closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
