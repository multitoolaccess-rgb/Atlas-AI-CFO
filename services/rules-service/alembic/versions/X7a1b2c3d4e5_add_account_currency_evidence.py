"""Add append-only authoritative account-currency evidence events.

Revision ID: X7a1b2c3d4e5
Revises: W6a1b2c3d4e5

Existing account currency columns are compatibility projections. This
migration deliberately creates no evidence rows and therefore cannot
backfill or activate any existing account. Finlynq's compatibility bootstrap
may have created this table before Alembic; a compatible table is adopted only
after its required columns, existing rows, ownership, and uniqueness are
validated. Missing SQLite checks are then enforced by an insert trigger.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "X7a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "W6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "account_currency_evidence"
_REQUIRED_COLUMNS = {
    "id", "user_id", "account_id", "event_type", "source_kind", "currency_code",
    "observed_at", "recorded_at", "actor_category", "source_reference_hash",
    "idempotency_key_hash", "supersedes_event_id", "reason_code",
}


def _table_exists() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def _validate_existing_table() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}
    if _REQUIRED_COLUMNS - columns:
        raise RuntimeError("existing account currency evidence table is incompatible")

    # Existing rows are validated before any trigger/index work. This is a
    # non-disclosing aggregate check: invalid data fails the migration rather
    # than being rewritten, discarded, or silently granted authority.
    invalid_rows = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM {_TABLE} e
        WHERE length(e.id) <> 36 OR e.id <> lower(e.id)
           OR e.event_type NOT IN ('assertion', 'correction', 'revocation')
           OR e.source_kind NOT IN ('structured_provider', 'structured_statement', 'operator_confirmed', 'correction', 'revocation')
           OR length(e.actor_category) NOT BETWEEN 1 AND 32
           OR length(e.source_reference_hash) <> 64 OR e.source_reference_hash <> lower(e.source_reference_hash)
           OR length(e.idempotency_key_hash) <> 64 OR e.idempotency_key_hash <> lower(e.idempotency_key_hash)
           OR (e.reason_code IS NOT NULL AND length(e.reason_code) NOT BETWEEN 1 AND 64)
           OR (e.supersedes_event_id IS NOT NULL AND (length(e.supersedes_event_id) <> 36 OR e.supersedes_event_id <> lower(e.supersedes_event_id)))
           OR (e.event_type = 'assertion' AND (e.source_kind IN ('correction', 'revocation') OR e.currency_code IS NULL OR e.currency_code <> upper(e.currency_code) OR length(e.currency_code) <> 3))
           OR (e.event_type = 'correction' AND (e.source_kind <> 'correction' OR e.currency_code IS NULL OR e.currency_code <> upper(e.currency_code) OR length(e.currency_code) <> 3 OR e.supersedes_event_id IS NULL))
           OR (e.event_type = 'revocation' AND (e.source_kind <> 'revocation' OR e.currency_code IS NOT NULL OR e.supersedes_event_id IS NULL))
           OR (e.event_type NOT IN ('assertion', 'correction', 'revocation'))
    """)).scalar_one()
    if invalid_rows:
        raise RuntimeError("existing account currency evidence rows are incompatible")

    duplicate_keys = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM (
          SELECT account_id, idempotency_key_hash FROM {_TABLE}
          GROUP BY account_id, idempotency_key_hash HAVING COUNT(*) > 1
        )
    """)).scalar_one()
    if duplicate_keys:
        raise RuntimeError("existing account currency evidence idempotency is incompatible")

    ownership_mismatches = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM {_TABLE} e
        LEFT JOIN accounts a ON a.id = e.account_id
        WHERE a.id IS NULL OR a.user_id <> e.user_id
    """)).scalar_one()
    if ownership_mismatches:
        raise RuntimeError("existing account currency evidence ownership is incompatible")


def _sqlite_guards() -> None:
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_currency_evidence_validate_insert
    BEFORE INSERT ON account_currency_evidence
    WHEN length(NEW.id) <> 36 OR NEW.id <> lower(NEW.id)
      OR NEW.event_type NOT IN ('assertion', 'correction', 'revocation')
      OR NEW.source_kind NOT IN ('structured_provider', 'structured_statement', 'operator_confirmed', 'correction', 'revocation')
      OR length(NEW.actor_category) NOT BETWEEN 1 AND 32
      OR length(NEW.source_reference_hash) <> 64 OR NEW.source_reference_hash <> lower(NEW.source_reference_hash)
      OR length(NEW.idempotency_key_hash) <> 64 OR NEW.idempotency_key_hash <> lower(NEW.idempotency_key_hash)
      OR (NEW.reason_code IS NOT NULL AND length(NEW.reason_code) NOT BETWEEN 1 AND 64)
      OR (NEW.event_type = 'assertion' AND (NEW.source_kind IN ('correction', 'revocation') OR NEW.currency_code IS NULL OR NEW.currency_code <> upper(NEW.currency_code) OR length(NEW.currency_code) <> 3))
      OR (NEW.event_type = 'correction' AND (NEW.source_kind <> 'correction' OR NEW.currency_code IS NULL OR NEW.currency_code <> upper(NEW.currency_code) OR length(NEW.currency_code) <> 3 OR NEW.supersedes_event_id IS NULL))
      OR (NEW.event_type = 'revocation' AND (NEW.source_kind <> 'revocation' OR NEW.currency_code IS NOT NULL OR NEW.supersedes_event_id IS NULL))
    BEGIN SELECT RAISE(ABORT, 'account currency evidence shape mismatch'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_currency_evidence_owner_insert
    BEFORE INSERT ON account_currency_evidence
    WHEN (SELECT user_id FROM accounts WHERE id = NEW.account_id) IS NULL
      OR (SELECT user_id FROM accounts WHERE id = NEW.account_id) != NEW.user_id
    BEGIN SELECT RAISE(ABORT, 'account currency evidence ownership mismatch'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_currency_evidence_no_update
    BEFORE UPDATE ON account_currency_evidence
    BEGIN SELECT RAISE(ABORT, 'account currency evidence is immutable'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_currency_evidence_no_delete
    BEFORE DELETE ON account_currency_evidence
    BEGIN SELECT RAISE(ABORT, 'account currency evidence is immutable'); END""")


def _postgres_guards() -> None:
    op.execute("""CREATE OR REPLACE FUNCTION enforce_account_currency_evidence_owner() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM accounts WHERE id = NEW.account_id AND user_id = NEW.user_id) THEN
        RAISE EXCEPTION 'account currency evidence ownership mismatch';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("""DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'account_currency_evidence_owner') THEN
        CREATE TRIGGER account_currency_evidence_owner
        BEFORE INSERT ON account_currency_evidence FOR EACH ROW
        EXECUTE FUNCTION enforce_account_currency_evidence_owner();
      END IF;
    END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION reject_account_currency_evidence_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'account currency evidence is immutable'; END; $$ LANGUAGE plpgsql""")
    op.execute("""DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'account_currency_evidence_no_update') THEN
        CREATE TRIGGER account_currency_evidence_no_update
        BEFORE UPDATE ON account_currency_evidence FOR EACH ROW
        EXECUTE FUNCTION reject_account_currency_evidence_mutation();
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'account_currency_evidence_no_delete') THEN
        CREATE TRIGGER account_currency_evidence_no_delete
        BEFORE DELETE ON account_currency_evidence FOR EACH ROW
        EXECUTE FUNCTION reject_account_currency_evidence_mutation();
      END IF;
    END $$""")


def upgrade() -> None:
    if _table_exists():
        _validate_existing_table()
    else:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("event_type", sa.String(16), nullable=False),
            sa.Column("source_kind", sa.String(32), nullable=False),
            sa.Column("currency_code", sa.String(3), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("actor_category", sa.String(32), nullable=False),
            sa.Column("source_reference_hash", sa.String(64), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
            sa.Column("supersedes_event_id", sa.String(36), sa.ForeignKey(f"{_TABLE}.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("reason_code", sa.String(64), nullable=True),
            sa.UniqueConstraint("account_id", "idempotency_key_hash", name="uq_account_currency_evidence_idempotency"),
            sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_account_currency_evidence_id_shape"),
            sa.CheckConstraint("event_type IN ('assertion', 'correction', 'revocation')", name="ck_account_currency_evidence_event_type"),
            sa.CheckConstraint("source_kind IN ('structured_provider', 'structured_statement', 'operator_confirmed', 'correction', 'revocation')", name="ck_account_currency_evidence_source_kind"),
            sa.CheckConstraint("(event_type = 'revocation' AND source_kind = 'revocation' AND currency_code IS NULL) OR (event_type = 'assertion' AND source_kind NOT IN ('correction', 'revocation') AND currency_code IS NOT NULL AND currency_code = upper(currency_code) AND length(currency_code) = 3) OR (event_type = 'correction' AND source_kind = 'correction' AND currency_code IS NOT NULL AND currency_code = upper(currency_code) AND length(currency_code) = 3)", name="ck_account_currency_evidence_currency_shape"),
            sa.CheckConstraint("length(actor_category) BETWEEN 1 AND 32", name="ck_account_currency_evidence_actor_shape"),
            sa.CheckConstraint("length(source_reference_hash) = 64 AND source_reference_hash = lower(source_reference_hash)", name="ck_account_currency_evidence_source_hash"),
            sa.CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_account_currency_evidence_idempotency_hash"),
            sa.CheckConstraint("supersedes_event_id IS NULL OR (length(supersedes_event_id) = 36 AND supersedes_event_id = lower(supersedes_event_id))", name="ck_account_currency_evidence_supersedes_shape"),
            sa.CheckConstraint("reason_code IS NULL OR length(reason_code) BETWEEN 1 AND 64", name="ck_account_currency_evidence_reason_shape"),
        )
    inspector = sa.inspect(op.get_bind())
    existing_indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    for name, column in (
        ("ix_account_currency_evidence_user_id", "user_id"),
        ("ix_account_currency_evidence_account_id", "account_id"),
    ):
        if name not in existing_indexes:
            op.create_index(name, _TABLE, [column])
    if op.get_bind().dialect.name == "sqlite":
        _sqlite_guards()
    elif op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar_one():
        raise RuntimeError("cannot downgrade while account currency evidence history exists")
    if bind.dialect.name == "sqlite":
        for name in (
            "account_currency_evidence_validate_insert",
            "account_currency_evidence_owner_insert",
            "account_currency_evidence_no_update",
            "account_currency_evidence_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif bind.dialect.name == "postgresql":
        for name in (
            "account_currency_evidence_owner",
            "account_currency_evidence_no_update",
            "account_currency_evidence_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name} ON {_TABLE}")
        op.execute("DROP FUNCTION IF EXISTS enforce_account_currency_evidence_owner()")
        op.execute("DROP FUNCTION IF EXISTS reject_account_currency_evidence_mutation()")
    op.drop_index("ix_account_currency_evidence_account_id", table_name=_TABLE)
    op.drop_index("ix_account_currency_evidence_user_id", table_name=_TABLE)
    op.drop_table(_TABLE)
