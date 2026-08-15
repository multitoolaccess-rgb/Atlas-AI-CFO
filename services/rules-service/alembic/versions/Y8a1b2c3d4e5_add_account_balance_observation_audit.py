"""Add append-only account-balance observation provenance.

Revision ID: Y8a1b2c3d4e5
Revises: X7a1b2c3d4e5

The table stores no balance amount. It binds a timestamp to a hash of the
server-read account state and is empty by default; no historical last_sync
backfill occurs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "Y8a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "X7a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "account_balance_observations"
_REQUIRED_COLUMNS = {
    "id", "user_id", "account_id", "source_kind", "actor_category", "observed_at",
    "recorded_at", "precondition_hash", "observation_intent_hash", "idempotency_key_hash",
}


def _table_exists() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def _validate_existing_table() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}
    if _REQUIRED_COLUMNS - columns:
        raise RuntimeError("existing balance observation table is incompatible")
    invalid = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM {_TABLE}
        WHERE length(id) <> 36 OR id <> lower(id)
           OR source_kind <> 'operator_confirmed'
           OR actor_category <> 'local_operator'
           OR length(precondition_hash) <> 64 OR precondition_hash <> lower(precondition_hash)
           OR length(observation_intent_hash) <> 64 OR observation_intent_hash <> lower(observation_intent_hash)
           OR length(idempotency_key_hash) <> 64 OR idempotency_key_hash <> lower(idempotency_key_hash)
    """)).scalar_one()
    if invalid:
        raise RuntimeError("existing balance observation rows are incompatible")
    duplicate_keys = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM (
          SELECT account_id, idempotency_key_hash FROM {_TABLE}
          GROUP BY account_id, idempotency_key_hash HAVING COUNT(*) > 1
        )
    """)).scalar_one()
    if duplicate_keys:
        raise RuntimeError("existing balance observation idempotency is incompatible")
    ownership = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM {_TABLE} o
        LEFT JOIN accounts a ON a.id = o.account_id
        WHERE a.id IS NULL OR a.user_id <> o.user_id
    """)).scalar_one()
    if ownership:
        raise RuntimeError("existing balance observation ownership is incompatible")


def _sqlite_guards() -> None:
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_observations_validate_insert
    BEFORE INSERT ON account_balance_observations
    WHEN length(NEW.id) <> 36 OR NEW.id <> lower(NEW.id)
      OR NEW.source_kind <> 'operator_confirmed'
      OR NEW.actor_category <> 'local_operator'
      OR length(NEW.precondition_hash) <> 64 OR NEW.precondition_hash <> lower(NEW.precondition_hash)
      OR length(NEW.observation_intent_hash) <> 64 OR NEW.observation_intent_hash <> lower(NEW.observation_intent_hash)
      OR length(NEW.idempotency_key_hash) <> 64 OR NEW.idempotency_key_hash <> lower(NEW.idempotency_key_hash)
    BEGIN SELECT RAISE(ABORT, 'account balance observation shape mismatch'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_observations_owner_insert
    BEFORE INSERT ON account_balance_observations
    WHEN (SELECT user_id FROM accounts WHERE id = NEW.account_id) IS NULL
      OR (SELECT user_id FROM accounts WHERE id = NEW.account_id) != NEW.user_id
    BEGIN SELECT RAISE(ABORT, 'account balance observation ownership mismatch'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_observations_no_update
    BEFORE UPDATE ON account_balance_observations
    BEGIN SELECT RAISE(ABORT, 'account balance observations are immutable'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_observations_no_delete
    BEFORE DELETE ON account_balance_observations
    BEGIN SELECT RAISE(ABORT, 'account balance observations are immutable'); END""")


def _postgres_guards() -> None:
    op.execute("""CREATE OR REPLACE FUNCTION enforce_account_balance_observation_owner() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM accounts WHERE id = NEW.account_id AND user_id = NEW.user_id) THEN
        RAISE EXCEPTION 'account balance observation ownership mismatch';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER account_balance_observations_owner
      BEFORE INSERT ON account_balance_observations FOR EACH ROW
      EXECUTE FUNCTION enforce_account_balance_observation_owner()""")
    op.execute("""CREATE OR REPLACE FUNCTION reject_account_balance_observation_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'account balance observations are immutable'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER account_balance_observations_no_update
      BEFORE UPDATE ON account_balance_observations FOR EACH ROW
      EXECUTE FUNCTION reject_account_balance_observation_mutation()""")
    op.execute("""CREATE TRIGGER account_balance_observations_no_delete
      BEFORE DELETE ON account_balance_observations FOR EACH ROW
      EXECUTE FUNCTION reject_account_balance_observation_mutation()""")


def upgrade() -> None:
    if _table_exists():
        _validate_existing_table()
    else:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("source_kind", sa.String(32), nullable=False),
            sa.Column("actor_category", sa.String(32), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("precondition_hash", sa.String(64), nullable=False),
            sa.Column("observation_intent_hash", sa.String(64), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
            sa.UniqueConstraint("account_id", "idempotency_key_hash", name="uq_account_balance_observations_idempotency"),
            sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_account_balance_observations_id_shape"),
            sa.CheckConstraint("source_kind = 'operator_confirmed'", name="ck_account_balance_observations_source_kind"),
            sa.CheckConstraint("actor_category = 'local_operator'", name="ck_account_balance_observations_actor_category"),
            sa.CheckConstraint("length(precondition_hash) = 64 AND precondition_hash = lower(precondition_hash)", name="ck_account_balance_observations_precondition_hash"),
            sa.CheckConstraint("length(observation_intent_hash) = 64 AND observation_intent_hash = lower(observation_intent_hash)", name="ck_account_balance_observations_intent_hash"),
            sa.CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_account_balance_observations_idempotency_hash"),
        )
    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(_TABLE)}
    for name, column in (("ix_account_balance_observations_user_id", "user_id"), ("ix_account_balance_observations_account_id", "account_id")):
        if name not in existing_indexes:
            op.create_index(name, _TABLE, [column])
    if op.get_bind().dialect.name == "sqlite":
        _sqlite_guards()
    elif op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar_one():
        raise RuntimeError("cannot downgrade while balance observation history exists")
    if bind.dialect.name == "sqlite":
        for name in (
            "account_balance_observations_validate_insert",
            "account_balance_observations_owner_insert",
            "account_balance_observations_no_update",
            "account_balance_observations_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif bind.dialect.name == "postgresql":
        for name in (
            "account_balance_observations_owner",
            "account_balance_observations_no_update",
            "account_balance_observations_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name} ON {_TABLE}")
        op.execute("DROP FUNCTION IF EXISTS enforce_account_balance_observation_owner()")
        op.execute("DROP FUNCTION IF EXISTS reject_account_balance_observation_mutation()")
    op.drop_index("ix_account_balance_observations_account_id", table_name=_TABLE)
    op.drop_index("ix_account_balance_observations_user_id", table_name=_TABLE)
    op.drop_table(_TABLE)
