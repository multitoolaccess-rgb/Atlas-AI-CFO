"""SQLAlchemy engine, session factory, and FastAPI dependency for Finlynq.

Phase-F4 lift — mirrors ``services/rules-service/app/database.py``
verbatim so both services bind to the SAME engine URL per the
`Phase-F2 shared-DB wiring` decision (``docs/finlynq-migration-progress.md``).

Why mirror instead of cross-import: Finlynq and rules-service are
sibling services, not parent/child. Cross-importing between siblings
couples their lifecycle (any change in rules-service's app.database
breaks Finlynq startup). Duplication cost is ~70 lines; cross-import
cost is subtle runtime breakage (the session-pool binding,
``register_sqlite_compat`` timing, and ``import app.models`` ordering
all become cross-service dependencies).

The cross-service invariant is locked by
``tests/test_shared_db_across_services.py`` (Phase-F4 follow-up):
the SAME ``settings.database_url`` resolves to the SAME engine
binding on both services — so a category row written via Finlynq's
``POST /categories`` is queryable from rules-service's
``GET /api/categories/`` (the rules-service forwarder at the
catalog surface re-emits the Finlynq emission; F4 persistence
lands in Finlynq's ``app.models`` and the forwarder round-trips
without DB reads on rules-service's side).

The same engine ``register_sqlite_compat`` shim is registered on
Finlynq's engine as it is on rules-service's: lifted migrations
reference ``now()`` directly and the shim emits a tz-aware UTC
string so Postgres and SQLite rows sort/compare identically.
"""
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def register_sqlite_compat(engine) -> None:
    """Same shim as rules-service — see that file for rationale.

    Postgres' ``now()`` returns a timestamptz; SQLite has no equivalent.
    Some lifted migrations reference ``now()`` directly. Without this
    shim, dev / CI / e2e runs against SQLite 500 on first write.
    """
    if engine.dialect.name != "sqlite":
        return
    if getattr(engine, "_fc_sqlite_compat_registered", False):
        return

    @event.listens_for(engine, "connect")
    def _register(dbapi_connection, connection_record):
        # Phase-F5+ concurrency hardening — mirror of services/rules-service/
        # app/database.py. start.sh runs ``alembic upgrade head`` against
        # the same shared SQLite DB at the same moment Finlynq's
        # ``_recalculate_account_balances`` startup hook is mid-write.
        #
        # BEHAVIOUR NOTES for future operators:
        #   * busy_timeout=30s is intentionally long to absorb the
        #     documented start.sh alembic+recalc race (real contention
        #     is <100ms). A genuine deadlock is more usefully surfaced
        #     in logs by a longer wait than by a fast raise.
        #   * journal_mode=WAL is persistent across connections; any
        #     future ``cp finance.db backup.db`` snapshot tool will
        #     silently produce an INCONSISTENT snapshot because the
        #     -wal and -shm siblings hold uncommitted deltas. Snapshot
        #     tooling MUST run ``PRAGMA wal_checkpoint(TRUNCATE)``
        #     first, or copy all three files (db + wal + shm) atomically.
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


# Engine — same pre-ping hardening as rules-service (laptop sleep +
# DNS renewal cost pytest devs hours before this was added).
engine = create_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)
register_sqlite_compat(engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# Critical — like rules-service/app/database.py: ``import app.models``
# MUST live AFTER ``class Base(DeclarativeBase)`` is defined. Earlier
# placement triggers circular import errors. The import charges
# ``Base.metadata`` with every lifted SQLAlchemy class so alembic's
# ``target_metadata = Base.metadata`` + FastAPI's startup-hook
# ``seed_default_categories`` see a fully-populated metadata.
#
# Phase-F4 first cutoff: import only what's needed for the categorizer
# route (Category). User/Account/Goal/Transaction land in F5.
import app.models  # noqa: E402,F401


def get_db():
    """FastAPI dependency yielding a SQLAlchemy Session; closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
