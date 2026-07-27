"""Phase-F2 task #1 — originally held the dialect-aware hermetic test
fixtures for rules-service (client / auth_cookie / app_with_test_db /
user_b_client / db_session / make_account / make_transaction /
make_goal). Phase-F2 task #1 round-up MOVED those definitions to
``conftest.py`` so pytest's auto-discovery resolves them for every
test file (the 8 ``pytest_plugins = ["tests.test_routes_auth_helpers"]``
imports in test_routes_{accounts,goals,dashboard,transactions,users,plaid,
analyst_ratings}.py + test_auth_routes.py are now harmless no-op loads
because this module defines no fixtures).

The historical notes below are preserved for grep-archeology only —
they describe the dialect-aware reset logic that lived here
pre-F2-task-#1-round-up.

Historical dialect notes (kept here for the grep trail)
======================================================

Per Phase-F2 task #0 (services/rules-service/tests/conftest.py), the
TEST_DATABASE_URL env var resolves BEFORE any ``from app.config import
settings`` runs, so :data:`app.database.engine` binds to whatever
``settings.database_url`` evaluates to — by default
``sqlite:///:memory:`` (hermetic dev-laptop) or whatever
``TEST_DATABASE_URL`` says otherwise.

The original fixture file BRANCHED on the resolved dialect so it worked
under both the wealthiq-baseline :5433 Postgres AND the conftest's
hermetic SQLite default:

- **Postgres** (``engine.dialect.name == 'postgresql'``):
  keep the wealthiq-owned ``DROP DATABASE ... WITH (FORCE)`` flow +
  ``alembic upgrade head`` + per-test ``TRUNCATE ... RESTART IDENTITY
  CASCADE``. The Postgres :5433 dev sidecar comes up via
  docker-compose in CI.
- **SQLite** (the conftest default — hermetic on dev laptop):
  ``DROP DATABASE`` is invalid SQL on SQLite. Use
  ``Base.metadata.drop_all`` + ``create_all`` instead. Per-test reset
  uses ``DELETE FROM {table}`` + ``DELETE FROM sqlite_sequence`` to
  mimic ``RESTART IDENTITY`` so id assertions stay predictable.

Those dialect branches now live in ``conftest.py``. This file is a
historical-only placeholder so the 8 ``pytest_plugins`` imports keep
working without raising ``fixture already defined`` errors.
"""
