"""Add append-only authoritative account-currency evidence events.

Revision ID: X7a1b2c3d4e5
Revises: W6a1b2c3d4e5

Existing account currency columns are compatibility projections.  This
migration deliberately creates no evidence rows and therefore cannot
backfill or activate any existing account.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "X7a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "W6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sqlite_guards() -> None:
    op.execute("""CREATE TRIGGER account_currency_evidence_owner_insert
    BEFORE INSERT ON account_currency_evidence
    WHEN (SELECT user_id FROM accounts WHERE id = NEW.account_id) IS NULL
      OR (SELECT user_id FROM accounts WHERE id = NEW.account_id) != NEW.user_id
    BEGIN SELECT RAISE(ABORT, 'account currency evidence ownership mismatch'); END""")
    op.execute("""CREATE TRIGGER account_currency_evidence_no_update
    BEFORE UPDATE ON account_currency_evidence
    BEGIN SELECT RAISE(ABORT, 'account currency evidence is immutable'); END""")
    op.execute("""CREATE TRIGGER account_currency_evidence_no_delete
    BEFORE DELETE ON account_currency_evidence
    BEGIN SELECT RAISE(ABORT, 'account currency evidence is immutable'); END""")


def _postgres_guards() -> None:
    op.execute("""CREATE FUNCTION enforce_account_currency_evidence_owner() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM accounts WHERE id = NEW.account_id AND user_id = NEW.user_id) THEN
        RAISE EXCEPTION 'account currency evidence ownership mismatch';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER account_currency_evidence_owner
    BEFORE INSERT ON account_currency_evidence FOR EACH ROW
    EXECUTE FUNCTION enforce_account_currency_evidence_owner()""")
    op.execute("""CREATE FUNCTION reject_account_currency_evidence_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'account currency evidence is immutable'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER account_currency_evidence_no_update
    BEFORE UPDATE ON account_currency_evidence FOR EACH ROW
    EXECUTE FUNCTION reject_account_currency_evidence_mutation()""")
    op.execute("""CREATE TRIGGER account_currency_evidence_no_delete
    BEFORE DELETE ON account_currency_evidence FOR EACH ROW
    EXECUTE FUNCTION reject_account_currency_evidence_mutation()""")


def upgrade() -> None:
    op.create_table(
        "account_currency_evidence",
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
        sa.Column("supersedes_event_id", sa.String(36), sa.ForeignKey("account_currency_evidence.id", ondelete="RESTRICT"), nullable=True),
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
    op.create_index("ix_account_currency_evidence_user_id", "account_currency_evidence", ["user_id"])
    op.create_index("ix_account_currency_evidence_account_id", "account_currency_evidence", ["account_id"])
    if op.get_bind().dialect.name == "sqlite":
        _sqlite_guards()
    elif op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM account_currency_evidence")).scalar_one():
        raise RuntimeError("cannot downgrade while account currency evidence history exists")
    if bind.dialect.name == "sqlite":
        for name in (
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
            op.execute(f"DROP TRIGGER IF EXISTS {name} ON account_currency_evidence")
        op.execute("DROP FUNCTION IF EXISTS enforce_account_currency_evidence_owner()")
        op.execute("DROP FUNCTION IF EXISTS reject_account_currency_evidence_mutation()")
    op.drop_index("ix_account_currency_evidence_account_id", table_name="account_currency_evidence")
    op.drop_index("ix_account_currency_evidence_user_id", table_name="account_currency_evidence")
    op.drop_table("account_currency_evidence")
