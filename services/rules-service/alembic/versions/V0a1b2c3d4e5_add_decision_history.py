"""Add immutable decision history and audit records.

Revision ID: V0a1b2c3d4e5
Revises: U9a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "V0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "U9a1b2c3d4e5"
branch_labels = None
depends_on = None


def _guards() -> None:
    bind = op.get_bind()
    tables = ("decision_history_entries", "decision_audit_events")
    if bind.dialect.name == "sqlite":
        for table in tables:
            op.execute(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, '{table} are immutable'); END")
            op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, '{table} are immutable'); END")
        op.execute("""CREATE TRIGGER decision_history_entries_owner BEFORE INSERT ON decision_history_entries
        WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id=NEW.goal_id)
          OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id=NEW.recommendation_id) OR NEW.goal_id != (SELECT goal_id FROM recommendations WHERE id=NEW.recommendation_id)
          OR NEW.user_id != (SELECT user_id FROM decision_journal_entries WHERE id=NEW.decision_journal_entry_id) OR NEW.goal_id != (SELECT goal_id FROM decision_journal_entries WHERE id=NEW.decision_journal_entry_id) OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_journal_entries WHERE id=NEW.decision_journal_entry_id)
          OR (NEW.supersedes_history_entry_id IS NOT NULL AND (NEW.user_id != (SELECT user_id FROM decision_history_entries WHERE id=NEW.supersedes_history_entry_id) OR NEW.goal_id != (SELECT goal_id FROM decision_history_entries WHERE id=NEW.supersedes_history_entry_id) OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_history_entries WHERE id=NEW.supersedes_history_entry_id)))
        BEGIN SELECT RAISE(ABORT, 'decision history owner mismatch'); END""")
        op.execute("""CREATE TRIGGER decision_audit_events_owner BEFORE INSERT ON decision_audit_events
        WHEN NEW.user_id != (SELECT user_id FROM decision_history_entries WHERE id=NEW.history_entry_id)
          OR NEW.goal_id != (SELECT goal_id FROM decision_history_entries WHERE id=NEW.history_entry_id)
          OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_history_entries WHERE id=NEW.history_entry_id)
          OR NEW.decision_journal_entry_id != (SELECT decision_journal_entry_id FROM decision_history_entries WHERE id=NEW.history_entry_id)
          OR (NEW.outcome_evaluation_id IS NOT NULL AND (NEW.user_id != (SELECT user_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id) OR NEW.goal_id != (SELECT goal_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id) OR NEW.recommendation_id != (SELECT recommendation_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id) OR NEW.decision_journal_entry_id != (SELECT decision_journal_entry_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id)))
        BEGIN SELECT RAISE(ABORT, 'decision audit owner mismatch'); END""")
        op.execute("""CREATE TRIGGER decision_history_entries_format BEFORE INSERT ON decision_history_entries
        WHEN length(NEW.id)!=36 OR NEW.id!=lower(NEW.id) OR NEW.id NOT GLOB '????????-????-????-????-????????????'
          OR length(NEW.recommendation_id)!=36 OR NEW.recommendation_id!=lower(NEW.recommendation_id)
          OR length(NEW.decision_journal_entry_id)!=36 OR NEW.decision_journal_entry_id!=lower(NEW.decision_journal_entry_id)
          OR NEW.idempotency_key_hash GLOB '*[^0-9a-f]*' OR length(NEW.idempotency_key_hash)!=64
          OR NEW.decision_action NOT IN ('accept','reject','defer') OR NEW.currency!='USD'
          OR length(NEW.schema_version)<1 OR length(NEW.schema_version)>64 OR length(NEW.rationale)<1 OR length(NEW.rationale)>2048 OR length(NEW.alternatives_json)<2 OR length(NEW.alternatives_json)>4096
        BEGIN SELECT RAISE(ABORT, 'decision history values must be canonical'); END""")
        op.execute("""CREATE TRIGGER decision_audit_events_format BEFORE INSERT ON decision_audit_events
        WHEN length(NEW.id)!=36 OR NEW.id!=lower(NEW.id) OR NEW.id NOT GLOB '????????-????-????-????-????????????'
          OR NEW.correlation_hash GLOB '*[^0-9a-f]*' OR length(NEW.correlation_hash)!=64
          OR NEW.event_action NOT IN ('recorded','corrected','evaluated') OR NEW.actor_scope!='owner' OR NEW.policy_result!='recorded'
        BEGIN SELECT RAISE(ABORT, 'decision audit values must be canonical'); END""")
    elif bind.dialect.name == "postgresql":
        for table in tables:
            op.execute(f"CREATE FUNCTION reject_{table}_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION '{table} are immutable'; END; $$ LANGUAGE plpgsql")
            op.execute(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_{table}_mutation()")
            op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_{table}_mutation()")
        op.execute("""CREATE FUNCTION enforce_decision_history_owners() RETURNS trigger AS $$ BEGIN
        IF NEW.user_id != (SELECT user_id FROM goals WHERE id=NEW.goal_id) OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id=NEW.recommendation_id) OR NEW.goal_id != (SELECT goal_id FROM recommendations WHERE id=NEW.recommendation_id) OR NEW.user_id != (SELECT user_id FROM decision_journal_entries WHERE id=NEW.decision_journal_entry_id) OR NEW.goal_id != (SELECT goal_id FROM decision_journal_entries WHERE id=NEW.decision_journal_entry_id) OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_journal_entries WHERE id=NEW.decision_journal_entry_id) OR (NEW.supersedes_history_entry_id IS NOT NULL AND (NEW.user_id != (SELECT user_id FROM decision_history_entries WHERE id=NEW.supersedes_history_entry_id) OR NEW.goal_id != (SELECT goal_id FROM decision_history_entries WHERE id=NEW.supersedes_history_entry_id) OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_history_entries WHERE id=NEW.supersedes_history_entry_id))) THEN RAISE EXCEPTION 'decision history owner mismatch'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER decision_history_entries_owner BEFORE INSERT ON decision_history_entries FOR EACH ROW EXECUTE FUNCTION enforce_decision_history_owners()")
        op.execute("""CREATE FUNCTION enforce_decision_audit_owners() RETURNS trigger AS $$ BEGIN
        IF NEW.user_id != (SELECT user_id FROM decision_history_entries WHERE id=NEW.history_entry_id) OR NEW.goal_id != (SELECT goal_id FROM decision_history_entries WHERE id=NEW.history_entry_id) OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_history_entries WHERE id=NEW.history_entry_id) OR NEW.decision_journal_entry_id != (SELECT decision_journal_entry_id FROM decision_history_entries WHERE id=NEW.history_entry_id) OR (NEW.outcome_evaluation_id IS NOT NULL AND (NEW.user_id != (SELECT user_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id) OR NEW.goal_id != (SELECT goal_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id) OR NEW.recommendation_id != (SELECT recommendation_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id) OR NEW.decision_journal_entry_id != (SELECT decision_journal_entry_id FROM outcome_evaluations WHERE id=NEW.outcome_evaluation_id))) THEN RAISE EXCEPTION 'decision audit owner mismatch'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER decision_audit_events_owner BEFORE INSERT ON decision_audit_events FOR EACH ROW EXECUTE FUNCTION enforce_decision_audit_owners()")
        op.execute("""CREATE FUNCTION enforce_decision_history_format() RETURNS trigger AS $$ BEGIN
        IF length(NEW.id)!=36 OR NEW.id!=lower(NEW.id) OR NEW.id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' OR length(NEW.recommendation_id)!=36 OR NEW.recommendation_id!=lower(NEW.recommendation_id) OR length(NEW.decision_journal_entry_id)!=36 OR NEW.decision_journal_entry_id!=lower(NEW.decision_journal_entry_id) OR NEW.idempotency_key_hash !~ '^[0-9a-f]{64}$' OR NEW.decision_action NOT IN ('accept','reject','defer') OR NEW.currency!='USD' OR length(NEW.schema_version)<1 OR length(NEW.schema_version)>64 OR length(NEW.rationale)<1 OR length(NEW.rationale)>2048 OR length(NEW.alternatives_json)<2 OR length(NEW.alternatives_json)>4096 THEN RAISE EXCEPTION 'decision history values must be canonical'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER decision_history_entries_format BEFORE INSERT ON decision_history_entries FOR EACH ROW EXECUTE FUNCTION enforce_decision_history_format()")
        op.execute("""CREATE FUNCTION enforce_decision_audit_format() RETURNS trigger AS $$ BEGIN
        IF length(NEW.id)!=36 OR NEW.id!=lower(NEW.id) OR NEW.id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' OR NEW.correlation_hash !~ '^[0-9a-f]{64}$' OR NEW.event_action NOT IN ('recorded','corrected','evaluated') OR NEW.actor_scope!='owner' OR NEW.policy_result!='recorded' THEN RAISE EXCEPTION 'decision audit values must be canonical'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER decision_audit_events_format BEFORE INSERT ON decision_audit_events FOR EACH ROW EXECUTE FUNCTION enforce_decision_audit_format()")


def upgrade() -> None:
    op.create_table("decision_history_entries",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.Integer, nullable=False), sa.Column("goal_id", sa.Integer, nullable=False),
        sa.Column("recommendation_id", sa.String(36), nullable=False), sa.Column("decision_journal_entry_id", sa.String(36), nullable=False),
        sa.Column("supersedes_history_entry_id", sa.String(36), nullable=True), sa.Column("decision_action", sa.String(16), nullable=False),
        sa.Column("alternatives_json", sa.Text, nullable=False), sa.Column("rationale", sa.String(2048), nullable=False), sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False), sa.Column("currency", sa.String(3), nullable=False, server_default="USD"), sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["decision_journal_entry_id"], ["decision_journal_entries.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["supersedes_history_entry_id"], ["decision_history_entries.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "recommendation_id", "decision_journal_entry_id", "idempotency_key_hash", name="uq_decision_history_idempotency"),
        sa.CheckConstraint("length(id)=36 AND id=lower(id)", name="ck_decision_history_id_shape"), sa.CheckConstraint("length(idempotency_key_hash)=64 AND idempotency_key_hash=lower(idempotency_key_hash)", name="ck_decision_history_idempotency_hash"), sa.CheckConstraint("decision_action IN ('accept','reject','defer')", name="ck_decision_history_action"), sa.CheckConstraint("currency='USD'", name="ck_decision_history_currency"), sa.CheckConstraint("length(rationale) BETWEEN 1 AND 2048", name="ck_decision_history_rationale"), sa.CheckConstraint("length(alternatives_json) BETWEEN 2 AND 4096", name="ck_decision_history_alternatives"), sa.CheckConstraint("length(schema_version) BETWEEN 1 AND 64", name="ck_decision_history_schema"))
    for name in ("user_id", "goal_id", "recommendation_id", "decision_journal_entry_id", "supersedes_history_entry_id"):
        op.create_index(f"ix_decision_history_entries_{name}", "decision_history_entries", [name])
    op.create_table("decision_audit_events",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("history_entry_id", sa.String(36), nullable=False), sa.Column("user_id", sa.Integer, nullable=False), sa.Column("goal_id", sa.Integer, nullable=False), sa.Column("recommendation_id", sa.String(36), nullable=False), sa.Column("decision_journal_entry_id", sa.String(36), nullable=False), sa.Column("outcome_evaluation_id", sa.String(36), nullable=True), sa.Column("event_action", sa.String(16), nullable=False), sa.Column("actor_scope", sa.String(16), nullable=False, server_default="owner"), sa.Column("correlation_hash", sa.String(64), nullable=False), sa.Column("policy_result", sa.String(16), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["history_entry_id"], ["decision_history_entries.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["decision_journal_entry_id"], ["decision_journal_entries.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["outcome_evaluation_id"], ["outcome_evaluations.id"], ondelete="RESTRICT"), sa.UniqueConstraint("history_entry_id", "event_action", name="uq_decision_audit_history_action"), sa.CheckConstraint("length(id)=36 AND id=lower(id)", name="ck_decision_audit_id_shape"), sa.CheckConstraint("event_action IN ('recorded','corrected','evaluated')", name="ck_decision_audit_action"), sa.CheckConstraint("actor_scope='owner'", name="ck_decision_audit_actor_scope"), sa.CheckConstraint("policy_result='recorded'", name="ck_decision_audit_policy"), sa.CheckConstraint("length(correlation_hash)=64 AND correlation_hash=lower(correlation_hash)", name="ck_decision_audit_correlation_hash"))
    for name in ("history_entry_id", "user_id", "goal_id", "recommendation_id", "decision_journal_entry_id", "outcome_evaluation_id"):
        op.create_index(f"ix_decision_audit_events_{name}", "decision_audit_events", [name])
    _guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM decision_history_entries")).scalar_one() or bind.execute(sa.text("SELECT COUNT(*) FROM decision_audit_events")).scalar_one():
        raise RuntimeError("Downgrade refused: decision history contains immutable audit records.")
    if bind.dialect.name == "sqlite":
        for table in ("decision_audit_events", "decision_history_entries"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update"); op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
        op.execute("DROP TRIGGER IF EXISTS decision_history_entries_owner"); op.execute("DROP TRIGGER IF EXISTS decision_audit_events_owner"); op.execute("DROP TRIGGER IF EXISTS decision_history_entries_format"); op.execute("DROP TRIGGER IF EXISTS decision_audit_events_format")
    elif bind.dialect.name == "postgresql":
        for table in ("decision_audit_events", "decision_history_entries"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update ON {table}"); op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}"); op.execute(f"DROP FUNCTION IF EXISTS reject_{table}_mutation()")
        op.execute("DROP TRIGGER IF EXISTS decision_history_entries_owner ON decision_history_entries"); op.execute("DROP TRIGGER IF EXISTS decision_audit_events_owner ON decision_audit_events"); op.execute("DROP TRIGGER IF EXISTS decision_history_entries_format ON decision_history_entries"); op.execute("DROP TRIGGER IF EXISTS decision_audit_events_format ON decision_audit_events"); op.execute("DROP FUNCTION IF EXISTS enforce_decision_history_owners()"); op.execute("DROP FUNCTION IF EXISTS enforce_decision_audit_owners()"); op.execute("DROP FUNCTION IF EXISTS enforce_decision_history_format()"); op.execute("DROP FUNCTION IF EXISTS enforce_decision_audit_format()")
    op.drop_table("decision_audit_events"); op.drop_table("decision_history_entries")
