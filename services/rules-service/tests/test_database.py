"""Tests for ``app.database.engine`` / ``SessionLocal`` / ``get_db``.

These tests verify the lift contract WITHOUT requiring a live Postgres
connection:

- The module-level ``engine`` is configured with ``pool_pre_ping=True`` (the
  one edit I added vs wealthiq's ``db.py``). We check the internal flag that
  SQLAlchemy exposes for this.
- ``SessionLocal()`` is constructible without raising — we never call any
  method that actually contacts Postgres (SessionLocal is lazy).
- ``get_db()`` is a sync generator that yields exactly one session and then
  raises ``StopIteration`` on the second ``next()``.
"""
import pytest

from app.database import Base, SessionLocal, engine, get_db


def test_engine_is_configured_with_pool_pre_ping():
    """Lift invariant: engine enables ``pool_pre_ping`` (stale-connection safety)."""
    # SQLAlchemy's ``create_engine(pool_pre_ping=True)`` sets this private flag.
    assert engine.pool._pre_ping is True, (
        "engine.pool._pre_ping must be True; "
        "Phase 2 lifted db.py from wealthiq with pool_pre_ping added"
    )


def test_engine_url_matches_settings(monkeypatch):
    """Engine URL matches :data:`app.config.settings.database_url`.

    SQLAlchemy's ``URL`` repr masks passwords (``wealthiq:***``) and the
    default ``database_url`` (``postgresql://wealthiq:wealthiq@…``) contains
    a literal ``:`` in what *looks* like the password slot, so a string-level
    comparison is fragile. We instead compare each parseable component.
    """
    from sqlalchemy.engine.url import make_url

    from app.config import settings as live_settings

    expected = make_url(live_settings.database_url)
    assert engine.url.drivername == expected.drivername
    assert engine.url.host == expected.host
    assert engine.url.port == expected.port
    assert engine.url.database == expected.database
    assert engine.url.username == expected.username


def test_sessionlocal_can_be_constructed():
    """SessionLocal opens a session; lazy connection means no DB required."""
    sess = SessionLocal()
    try:
        # Bind to our engine (proves factory was wired).
        assert sess.bind is engine
    finally:
        sess.close()


def test_basemetadata_is_declarative_base():
    """``Base`` is a SQLAlchemy DeclarativeBase subclass lifted from db.py."""
    from sqlalchemy.orm import DeclarativeBase

    assert isinstance(Base, type) and issubclass(Base, DeclarativeBase)


def test_get_db_dependency_yields_then_closes():
    """``get_db()`` yields once, then exits cleanly (closes the session)."""
    gen = get_db()
    sess = next(gen)
    assert sess is not None
    assert sess.bind is engine
    with pytest.raises(StopIteration):
        next(gen)  # generator exit; ``finally: db.close()`` already ran
