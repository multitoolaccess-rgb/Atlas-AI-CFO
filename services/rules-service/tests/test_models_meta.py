"""Verify Phase 3 SQLAlchemy model lift is complete + FKs are correct.

These tests inspect ``Base.metadata`` in-process — no live Postgres required.
Combined with ``tests/test_alembic_migration.py`` (which DOES touch the DB),
they ensure the lift is structural + applied.
"""
import pytest


# Every Phase 3-lifted model table. The set MUST match the inventory verbatim
# (see ``docs/inventory-from-wealthiq.md`` § backend/app/models).
EXPECTED_TABLES = {
    "users",
    "institutions",
    "accounts",
    "categories",
    "transactions",
    "import_batches",
    "budgets",
    "goals",  # Phase 8 Financial Planning lift.
    # Phase 16 — multi-member family grouping of accounts (mirrors
    # the Goal pattern). Lives here so the inventory is the single
    # source of truth the bootstrap + the alembic autogenerate both
    # read against.
    "family_members",
    # Phase 18 — categorizer v2 per-user alias learning.
    # ``merchant_aliases`` is the Pass-1 lookup target; FKs to
    # ``users`` + ``categories``; UNIQUE(user_id, alias_key).
    "merchant_aliases",
    # Phase 24 — DB-backed substring rules. Pairs with the
    # categoriser (Pass 2) and the user-editable Settings surface
    # (routes/merchant_rules.py). Mirrors the merchant_aliases
    # inventory slot above.
    "merchant_rules",
    # Phase 30c — AI assistant conversations + messages.
    "assistant_conversations",
    "assistant_messages",
    # Phase 39 — portfolio holdings (positions import + live pricing).
    "holdings",
    # Phase 4 — recommendation approval workflow audit trail.
    "recommendation_logs",
    # Phase 1 — immutable forecast identity and version history.
    "forecasts",
    "forecast_versions",
    # Phase 2 Slice 1 — deterministic recommendation ledger and
    # append-only decision journal. These models are now part of the
    # merged metadata contract and must remain inside the FK closure.
    "recommendations",
    "decision_journal_entries",
    # Phase 3 — append-only outcome evidence linked to accepted decisions.
    "outcome_evaluations",
}


def test_all_lifted_models_registered_on_metadata():
    """Phase 3 lift assertion: every backend/app/models/* class is registered
    on ``Base.metadata``. Missing ANY here means the lift was incomplete
    (a future alembic autogenerate would silently NOT migrate that table).
    """
    from app.database import Base

    actual = set(Base.metadata.tables.keys())
    missing = EXPECTED_TABLES - actual
    assert not missing, (
        f"Phase 3 lift missed models registered on Base.metadata: {missing}; "
        f"make sure each model file is imported in app/models/__init__.py"
    )
    # And no surprise tables dropped in (catches a Phase 4 feature-creep).
    extra = actual - EXPECTED_TABLES
    assert not extra, f"Unexpected tables in metadata: {extra}"


def test_user_table_email_is_unique_and_indexed():
    """``users.email`` is the only login ingress in single-user mode; it must
    be unique (preventing accidental multi-user collisions) AND indexed (so
    the demo-user-by-email lookup is sub-millisecond)."""
    from app.database import Base

    users = Base.metadata.tables["users"]
    email_col = users.columns["email"]
    # SQLAlchemy's ``ReadOnlyColumnCollection.__contains__`` requires a STRING
    # column name, not a Column object. Caught by Phase 3 diagnostic:
    # ``sqlalchemy.exc.ArgumentError: __contains__ requires a string argument``.
    indexed = any("email" in idx.columns for idx in users.indexes)
    assert email_col.unique is True, "users.email must be UNIQUE"
    assert indexed, "users.email should be index-backed"


def test_account_fks_to_users_and_institutions():
    """Account must FK to user_id, institution_id, AND family_members (lift invariant).

    Phase 16 added a third FK target (``family_members``) — every
    account belongs to a family member (Self / Spouse / Kid) so the
    Accounts page chip + the ``family_member_id`` FK both have
    something to point at. The wire shape is unchanged for the FE;
    the BE just owns one more invariant.
    """
    from app.database import Base

    targets = {
        fk.column.table.name for fk in Base.metadata.tables["accounts"].foreign_keys
    }
    assert targets == {"users", "institutions", "family_members"}, (
        f"Account must FK to {{'users', 'institutions', 'family_members'}}; got {targets}"
    )


def test_transaction_fks_to_accounts_categories_import_batches():
    """Transaction FKs: account (required), category (nullable), import_batch (nullable)."""
    from app.database import Base

    targets = {fk.column.table.name for fk in Base.metadata.tables["transactions"].foreign_keys}
    assert targets == {"accounts", "categories", "import_batches", "transactions"}


def test_import_batches_fks_to_users_and_accounts():
    """ImportBatch is the closure for the statement-upload UX (CSV/PDF/OCR/Plaid)."""
    from app.database import Base

    targets = {fk.column.table.name for fk in Base.metadata.tables["import_batches"].foreign_keys}
    assert targets == {"users", "accounts"}


def test_budget_fks_to_users_and_categories():
    """Budget anchors a spending limit per (category, period) for a user."""
    from app.database import Base

    targets = {fk.column.table.name for fk in Base.metadata.tables["budgets"].foreign_keys}
    assert targets == {"users", "categories"}


def test_no_orphan_fks_in_the_lifted_set():
    """Every FK target MUST point at one of the lifted tables (no dangling FK
    that would make alembic autogenerate produce an unresolvable reference)."""
    from app.database import Base

    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.column.table.name in EXPECTED_TABLES, (
                f"Table {table.name} has FK to {fk.column.table.name} "
                f"— target table is not in the Phase 3 lifted set"
            )
