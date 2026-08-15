"""Add append-only exact-cent authoritative balance evidence.

Revision ID: Z9a1b2c3d4e5
Revises: Y8a1b2c3d4e5

Existing balance-observation audit rows are never backfilled. New assertion and
revocation events are stored separately with NUMERIC(38,2) authority.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "Z9a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "Y8a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "account_balance_evidence"
_REQUIRED_COLUMNS = {
    "id", "user_id", "account_id", "event_type", "source_kind", "actor_category",
    "currency_code", "amount", "observed_at", "recorded_at", "supersedes_event_id",
    "precondition_hash", "state_hash", "observation_intent_hash", "idempotency_key_hash",
}


def _exists() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def _validate_existing() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}
    if _REQUIRED_COLUMNS - columns:
        raise RuntimeError("existing balance evidence table is incompatible")
    invalid = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM {_TABLE}
        WHERE length(id) <> 36 OR id <> lower(id)
           OR event_type NOT IN ('assertion', 'revocation')
           OR source_kind <> 'operator_confirmed'
           OR actor_category <> 'local_operator'
           OR currency_code <> 'USD'
           OR (event_type = 'assertion' AND amount IS NULL)
           OR (event_type = 'revocation' AND amount IS NOT NULL)
           OR (amount IS NOT NULL AND amount <> round(amount, 2))
           OR length(precondition_hash) <> 64 OR precondition_hash <> lower(precondition_hash)
           OR length(state_hash) <> 64 OR state_hash <> lower(state_hash)
           OR length(observation_intent_hash) <> 64 OR observation_intent_hash <> lower(observation_intent_hash)
           OR length(idempotency_key_hash) <> 64 OR idempotency_key_hash <> lower(idempotency_key_hash)
    """)).scalar_one()
    if invalid:
        raise RuntimeError("existing balance evidence rows are incompatible")
    ownership = bind.execute(sa.text(f"""
        SELECT COUNT(*) FROM {_TABLE} e
        LEFT JOIN accounts a ON a.id = e.account_id
        WHERE a.id IS NULL OR a.user_id <> e.user_id
    """)).scalar_one()
    if ownership:
        raise RuntimeError("existing balance evidence ownership is incompatible")


def _sqlite_guards() -> None:
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_evidence_validate_insert
    BEFORE INSERT ON account_balance_evidence
    WHEN length(NEW.id) <> 36 OR NEW.id <> lower(NEW.id)
      OR NEW.event_type NOT IN ('assertion', 'revocation')
      OR NEW.source_kind <> 'operator_confirmed'
      OR NEW.actor_category <> 'local_operator'
      OR NEW.currency_code <> 'USD'
      OR (NEW.event_type = 'assertion' AND NEW.amount IS NULL)
      OR (NEW.event_type = 'revocation' AND NEW.amount IS NOT NULL)
      OR (NEW.amount IS NOT NULL AND NEW.amount != round(NEW.amount, 2))
      OR length(NEW.precondition_hash) <> 64 OR NEW.precondition_hash <> lower(NEW.precondition_hash)
      OR length(NEW.state_hash) <> 64 OR NEW.state_hash <> lower(NEW.state_hash)
      OR length(NEW.observation_intent_hash) <> 64 OR NEW.observation_intent_hash <> lower(NEW.observation_intent_hash)
      OR length(NEW.idempotency_key_hash) <> 64 OR NEW.idempotency_key_hash <> lower(NEW.idempotency_key_hash)
    BEGIN SELECT RAISE(ABORT, 'account balance evidence shape mismatch'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_evidence_owner_insert
    BEFORE INSERT ON account_balance_evidence
    WHEN (SELECT user_id FROM accounts WHERE id = NEW.account_id) IS NULL
      OR (SELECT user_id FROM accounts WHERE id = NEW.account_id) != NEW.user_id
    BEGIN SELECT RAISE(ABORT, 'account balance evidence ownership mismatch'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_evidence_revocation_insert
    BEFORE INSERT ON account_balance_evidence
    WHEN NEW.event_type = 'revocation'
      AND (NEW.supersedes_event_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM account_balance_evidence prior
        WHERE prior.id = NEW.supersedes_event_id
          AND prior.account_id = NEW.account_id
          AND prior.user_id = NEW.user_id
          AND prior.event_type = 'assertion'
      ))
    BEGIN SELECT RAISE(ABORT, 'account balance evidence revocation mismatch'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_evidence_no_update
    BEFORE UPDATE ON account_balance_evidence
    BEGIN SELECT RAISE(ABORT, 'account balance evidence is immutable'); END""")
    op.execute("""CREATE TRIGGER IF NOT EXISTS account_balance_evidence_no_delete
    BEFORE DELETE ON account_balance_evidence
    BEGIN SELECT RAISE(ABORT, 'account balance evidence is immutable'); END""")


def _postgres_guards() -> None:
    op.execute("""CREATE OR REPLACE FUNCTION enforce_account_balance_evidence_owner() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM accounts WHERE id = NEW.account_id AND user_id = NEW.user_id) THEN
        RAISE EXCEPTION 'account balance evidence ownership mismatch';
      END IF;
      IF NEW.event_type = 'revocation' AND NOT EXISTS (
        SELECT 1 FROM account_balance_evidence prior
        WHERE prior.id = NEW.supersedes_event_id AND prior.account_id = NEW.account_id
          AND prior.user_id = NEW.user_id AND prior.event_type = 'assertion'
      ) THEN
        RAISE EXCEPTION 'account balance evidence revocation mismatch';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER account_balance_evidence_owner
      BEFORE INSERT ON account_balance_evidence FOR EACH ROW
      EXECUTE FUNCTION enforce_account_balance_evidence_owner()""")
    op.execute("""CREATE OR REPLACE FUNCTION reject_account_balance_evidence_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'account balance evidence is immutable'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER account_balance_evidence_no_update
      BEFORE UPDATE ON account_balance_evidence FOR EACH ROW
      EXECUTE FUNCTION reject_account_balance_evidence_mutation()""")
    op.execute("""CREATE TRIGGER account_balance_evidence_no_delete
      BEFORE DELETE ON account_balance_evidence FOR EACH ROW
      EXECUTE FUNCTION reject_account_balance_evidence_mutation()""")


def upgrade() -> None:
    if _exists():
        _validate_existing()
    else:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("event_type", sa.String(16), nullable=False),
            sa.Column("source_kind", sa.String(32), nullable=False),
            sa.Column("actor_category", sa.String(32), nullable=False),
            sa.Column("currency_code", sa.String(3), nullable=False),
            sa.Column("amount", sa.Numeric(38, 2, asdecimal=True), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("supersedes_event_id", sa.String(36), sa.ForeignKey(f"{_TABLE}.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("precondition_hash", sa.String(64), nullable=False),
            sa.Column("state_hash", sa.String(64), nullable=False),
            sa.Column("observation_intent_hash", sa.String(64), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
            sa.UniqueConstraint("account_id", "idempotency_key_hash", name="uq_account_balance_evidence_idempotency"),
            sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_account_balance_evidence_id_shape"),
            sa.CheckConstraint("event_type IN ('assertion', 'revocation')", name="ck_account_balance_evidence_event_type"),
            sa.CheckConstraint("source_kind = 'operator_confirmed'", name="ck_account_balance_evidence_source_kind"),
            sa.CheckConstraint("actor_category = 'local_operator'", name="ck_account_balance_evidence_actor_category"),
            sa.CheckConstraint("currency_code = 'USD'", name="ck_account_balance_evidence_currency"),
            sa.CheckConstraint("(event_type = 'assertion' AND amount IS NOT NULL) OR (event_type = 'revocation' AND amount IS NULL)", name="ck_account_balance_evidence_amount_event"),
            sa.CheckConstraint("length(precondition_hash) = 64 AND precondition_hash = lower(precondition_hash)", name="ck_account_balance_evidence_precondition_hash"),
            sa.CheckConstraint("length(state_hash) = 64 AND state_hash = lower(state_hash)", name="ck_account_balance_evidence_state_hash"),
            sa.CheckConstraint("length(observation_intent_hash) = 64 AND observation_intent_hash = lower(observation_intent_hash)", name="ck_account_balance_evidence_intent_hash"),
            sa.CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_account_balance_evidence_idempotency_hash"),
        )
    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(_TABLE)}
    for name, column in (("ix_account_balance_evidence_user_id", "user_id"), ("ix_account_balance_evidence_account_id", "account_id")):
        if name not in existing_indexes:
            op.create_index(name, _TABLE, [column])
    if op.get_bind().dialect.name == "sqlite":
        _sqlite_guards()
    elif op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar_one():
        raise RuntimeError("cannot downgrade while authoritative balance evidence exists")
    if bind.dialect.name == "sqlite":
        for name in (
            "account_balance_evidence_validate_insert",
            "account_balance_evidence_owner_insert",
            "account_balance_evidence_revocation_insert",
            "account_balance_evidence_no_update",
            "account_balance_evidence_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif bind.dialect.name == "postgresql":
        for name in (
            "account_balance_evidence_owner",
            "account_balance_evidence_no_update",
            "account_balance_evidence_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name} ON {_TABLE}")
        op.execute("DROP FUNCTION IF EXISTS enforce_account_balance_evidence_owner()")
        op.execute("DROP FUNCTION IF EXISTS reject_account_balance_evidence_mutation()")
    op.drop_index("ix_account_balance_evidence_account_id", table_name=_TABLE)
    op.drop_index("ix_account_balance_evidence_user_id", table_name=_TABLE)
    op.drop_table(_TABLE)
