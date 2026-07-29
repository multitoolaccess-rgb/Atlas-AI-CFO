"""Add source-backed account currency and explicit projection-goal config.

Revision ID: S7a1b2c3d4e5
Revises: R6f1g2h3i4j5

No legacy account receives a currency backfill.  Currency is authoritative
only when all provenance fields are supplied together.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "S7a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "R6f1g2h3i4j5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sqlite_currency_guards() -> None:
    for event in ("INSERT", "UPDATE"):
        op.execute(f"""CREATE TRIGGER accounts_currency_{event.lower()} BEFORE {event} ON accounts
        WHEN NOT (
            (NEW.currency_code IS NULL AND NEW.currency_source IS NULL
             AND NEW.currency_observed_at IS NULL AND NEW.currency_source_reference IS NULL)
            OR
            (NEW.currency_code IS NOT NULL AND NEW.currency_source IS NOT NULL
             AND NEW.currency_observed_at IS NOT NULL AND NEW.currency_source_reference IS NOT NULL
             AND length(NEW.currency_code) = 3 AND NEW.currency_code GLOB '[A-Z][A-Z][A-Z]'
             AND NEW.currency_source IN ('provider_reported', 'statement_declared', 'user_confirmed')
             AND length(NEW.currency_source_reference) BETWEEN 1 AND 128
             AND substr(NEW.currency_source_reference, 1, 1) GLOB '[a-z]'
             AND NEW.currency_source_reference NOT GLOB '*[^a-z0-9._:-]*')
        )
        BEGIN SELECT RAISE(ABORT, 'account currency provenance is invalid'); END""")
    op.execute("""CREATE TRIGGER goal_projection_configs_owner_insert BEFORE INSERT ON goal_projection_configs
    WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
    BEGIN SELECT RAISE(ABORT, 'projection config user must own goal'); END""")
    op.execute("""CREATE TRIGGER goal_projection_configs_owner_update BEFORE UPDATE ON goal_projection_configs
    WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
    BEGIN SELECT RAISE(ABORT, 'projection config user must own goal'); END""")
    for event in ("INSERT", "UPDATE"):
        op.execute(f"""CREATE TRIGGER goal_projection_configs_format_{event.lower()} BEFORE {event} ON goal_projection_configs
        WHEN NEW.projection_kind != 'net_worth' OR NEW.currency_code != 'USD'
          OR NEW.monthly_contribution < 0
          OR length(NEW.contribution_source_reference) NOT BETWEEN 1 AND 128
          OR substr(NEW.contribution_source_reference, 1, 1) NOT GLOB '[a-z]'
          OR NEW.contribution_source_reference GLOB '*[^a-z0-9._:-]*'
        BEGIN SELECT RAISE(ABORT, 'projection config is invalid'); END""")


def _drop_sqlite_guards() -> None:
    for name in (
        "accounts_currency_insert", "accounts_currency_update",
        "goal_projection_configs_owner_insert", "goal_projection_configs_owner_update",
        "goal_projection_configs_format_insert", "goal_projection_configs_format_update",
    ):
        op.execute(f"DROP TRIGGER {name}")


def _postgres_currency_guards() -> None:
    op.create_check_constraint(
        "ck_accounts_currency_provenance", "accounts",
        "(currency_code IS NULL AND currency_source IS NULL AND currency_observed_at IS NULL AND currency_source_reference IS NULL) OR "
        "(currency_code IS NOT NULL AND currency_source IS NOT NULL AND currency_observed_at IS NOT NULL AND currency_source_reference IS NOT NULL "
        "AND currency_code ~ '^[A-Z]{3}$' AND currency_source IN ('provider_reported', 'statement_declared', 'user_confirmed') "
        "AND currency_observed_at IS NOT NULL AND currency_source_reference ~ '^[a-z][a-z0-9._:-]{0,127}$')",
    )
    op.create_check_constraint("ck_goal_projection_configs_kind", "goal_projection_configs", "projection_kind = 'net_worth'")
    op.create_check_constraint("ck_goal_projection_configs_currency", "goal_projection_configs", "currency_code = 'USD'")
    op.create_check_constraint("ck_goal_projection_configs_contribution", "goal_projection_configs", "monthly_contribution >= 0")
    op.create_check_constraint("ck_goal_projection_configs_reference", "goal_projection_configs", "contribution_source_reference ~ '^[a-z][a-z0-9._:-]{0,127}$'")
    op.execute("""CREATE FUNCTION enforce_goal_projection_config_owner() RETURNS trigger AS $$
        BEGIN IF NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id) THEN
            RAISE EXCEPTION 'projection config user must own goal'; END IF;
        RETURN NEW; END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER goal_projection_configs_owner BEFORE INSERT OR UPDATE ON goal_projection_configs FOR EACH ROW EXECUTE FUNCTION enforce_goal_projection_config_owner()")


def _drop_postgres_guards() -> None:
    op.execute("DROP TRIGGER goal_projection_configs_owner ON goal_projection_configs")
    op.execute("DROP FUNCTION enforce_goal_projection_config_owner()")
    for name in (
        "ck_goal_projection_configs_reference", "ck_goal_projection_configs_contribution",
        "ck_goal_projection_configs_currency", "ck_goal_projection_configs_kind",
    ):
        op.drop_constraint(name, "goal_projection_configs", type_="check")
    op.drop_constraint("ck_accounts_currency_provenance", "accounts", type_="check")


def upgrade() -> None:
    op.add_column("accounts", sa.Column("currency_code", sa.String(3), nullable=True))
    op.add_column("accounts", sa.Column("currency_source", sa.String(32), nullable=True))
    op.add_column("accounts", sa.Column("currency_observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("currency_source_reference", sa.String(128), nullable=True))
    op.create_table(
        "goal_projection_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("projection_kind", sa.String(32), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("monthly_contribution", sa.Numeric(38, 2), nullable=False),
        sa.Column("contribution_source_reference", sa.String(128), nullable=False),
        sa.Column("contribution_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("goal_id", name="uq_goal_projection_configs_goal"),
    )
    op.create_index("ix_goal_projection_configs_user_id", "goal_projection_configs", ["user_id"])
    op.create_index("ix_goal_projection_configs_goal_id", "goal_projection_configs", ["goal_id"])
    if op.get_bind().dialect.name == "sqlite":
        _sqlite_currency_guards()
    elif op.get_bind().dialect.name == "postgresql":
        _postgres_currency_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM goal_projection_configs")).scalar_one():
        raise RuntimeError("cannot downgrade account currency migration while projection config data exists")
    if bind.execute(sa.text("SELECT COUNT(*) FROM accounts WHERE currency_code IS NOT NULL OR currency_source IS NOT NULL OR currency_observed_at IS NOT NULL OR currency_source_reference IS NOT NULL")).scalar_one():
        raise RuntimeError("cannot downgrade account currency migration while currency provenance exists")
    if bind.dialect.name == "sqlite":
        _drop_sqlite_guards()
    elif bind.dialect.name == "postgresql":
        _drop_postgres_guards()
    op.drop_index("ix_goal_projection_configs_goal_id", table_name="goal_projection_configs")
    op.drop_index("ix_goal_projection_configs_user_id", table_name="goal_projection_configs")
    op.drop_table("goal_projection_configs")
    op.drop_column("accounts", "currency_source_reference")
    op.drop_column("accounts", "currency_observed_at")
    op.drop_column("accounts", "currency_source")
    op.drop_column("accounts", "currency_code")
