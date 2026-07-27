import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# This file (`services/rules-service/alembic/env.py`) was lifted essentially verbatim
# from the legacy WealthIQ Alembic environment
# in Phase 2 of the merge (pre-stage for Phase 3 — see `docs/wealthiq-merge-plan.md`
# §4 Reuse Map item 4). Two trivial adaptations:

# IMPORTANT: this script is NOT yet runnable — it needs `alembic.ini` at
# `services/rules-service/`. ``fileConfig(config.config_file_name)`` raises
# ``AttributeError`` if ``config_file_name`` is None. Phase 3 will lift
# the ini file as part of the migration set-up; until then DON'T invoke
# ``alembic`` from this directory.
#
#   1. The lift's cwd-prefix path computation resolves to `services/rules-service/`
#      (the destination), so `app.config`/`app.db` are importable once you invoke
#      `alembic` from this directory (or once `services/rules-service/` is on
#      `PYTHONPATH`).
#   2. The lift's `from app.db import Base` is updated to `app.database.Base`
#      to match the new bounded-context layout in `docs/architecture.md` §3.

# cd into services/rules-service so `from app.config import settings` resolves.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings        # noqa: E402
from app.database import Base, register_sqlite_compat  # noqa: E402

# Phase 3 critical — `autogenerate` needs EVERY model class registered on
# `Base.metadata` BEFORE it can diff against the live DB schema. Without
# this import, `Base.metadata` is empty and the resulting migration file is
# a near-empty stub (saw this fail in initial Phase 3 run: 666 bytes,
# 0 references to lifted tables). Importing the `models` package is enough
# because `app/models/__init__.py` re-exports all 7 lifted model classes.
import app.models  # noqa: E402,F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# set the SQLAlchemy URL from settings
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    Phase 8: alembic builds its own engine via ``engine_from_config``;
    that engine is a *separate* object from the one in ``app.database``,
    so the ``now()`` SQLite shim must be re-applied here. Without this
    re-registration, fresh-DB ``alembic upgrade head`` against an empty
    SQLite file trips on canonical Postgres defaults like
    ``server_default=sa.text('now()')``.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    register_sqlite_compat(connectable)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
