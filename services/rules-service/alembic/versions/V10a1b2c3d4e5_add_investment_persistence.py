"""Add INV-PERSIST-01 investment application records.

Revision ID: V10a1b2c3d4e5
Revises: U9a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "V10a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "U9a1b2c3d4e5"
branch_labels = None
depends_on = None


def _immutable(table: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, '{table} are immutable'); END")
        op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, '{table} are immutable'); END")
    elif bind.dialect.name == "postgresql":
        fn = f"reject_{table}_mutation"
        op.execute(f"CREATE FUNCTION {fn}() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION '{table} are immutable'; END; $$ LANGUAGE plpgsql")
        op.execute(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION {fn}()")
        op.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {fn}()")


def _drop_immutable(table: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS reject_{table}_mutation()")


def upgrade() -> None:
    op.create_table(
        "investment_committee_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_scope", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("security_id", sa.String(128), nullable=False),
        sa.Column("analysis_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology_version", sa.String(64), nullable=False),
        sa.Column("evidence_packet_id", sa.String(128)),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("run_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("owner_id", "run_id", name="uq_investment_committee_runs_owner_run"),
        sa.CheckConstraint("length(run_hash) = 64 AND run_hash = lower(run_hash)", name="ck_investment_committee_runs_hash"),
    )
    op.create_index("ix_investment_committee_runs_owner_id", "investment_committee_runs", ["owner_id"])
    op.create_index("ix_investment_committee_runs_security_id", "investment_committee_runs", ["security_id"])

    op.create_table(
        "investment_evidence_packets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("packet_id", sa.String(128), nullable=False),
        sa.Column("security_id", sa.String(128), nullable=False),
        sa.Column("analysis_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("packet_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "packet_id", name="uq_investment_evidence_packets_owner_packet"),
        sa.CheckConstraint("length(packet_hash) = 64 AND packet_hash = lower(packet_hash)", name="ck_investment_evidence_packets_hash"),
    )
    op.create_index("ix_investment_evidence_packets_owner_id", "investment_evidence_packets", ["owner_id"])
    op.create_index("ix_investment_evidence_packets_security_id", "investment_evidence_packets", ["security_id"])

    op.create_table(
        "investment_committee_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_record_id", sa.Integer(), sa.ForeignKey("investment_committee_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("finding_id", sa.String(160), nullable=False),
        sa.Column("security_id", sa.String(128), nullable=False),
        sa.Column("analysis_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology_version", sa.String(64), nullable=False),
        sa.Column("finding_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "finding_id", name="uq_investment_committee_findings_owner_finding"),
        sa.CheckConstraint("length(finding_hash) = 64 AND finding_hash = lower(finding_hash)", name="ck_investment_committee_findings_hash"),
    )
    op.create_index("ix_investment_committee_findings_owner_id", "investment_committee_findings", ["owner_id"])
    op.create_index("ix_investment_committee_findings_run_record_id", "investment_committee_findings", ["run_record_id"])
    op.create_index("ix_investment_committee_findings_security_id", "investment_committee_findings", ["security_id"])

    op.create_table(
        "investment_recommendation_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation_id", sa.String(160), nullable=False),
        sa.Column("security_id", sa.String(128), nullable=False),
        sa.Column("recommendation_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("recommendation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("recommendation_hash", sa.String(64), nullable=False),
        sa.Column("committee_finding_id", sa.String(160), nullable=False),
        sa.Column("committee_run_id", sa.String(128), nullable=False),
        sa.Column("portfolio_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("owner_id", "recommendation_id", name="uq_investment_recommendations_owner_id"),
        sa.CheckConstraint("recommendation_type IN ('BUY','ADD','HOLD','REDUCE','SELL','WATCH')", name="ck_investment_recommendations_action"),
        sa.CheckConstraint("status IN ('active','superseded','expired','withdrawn')", name="ck_investment_recommendations_status"),
        sa.CheckConstraint("length(recommendation_hash) = 64 AND recommendation_hash = lower(recommendation_hash)", name="ck_investment_recommendations_hash"),
    )
    op.create_index("ix_investment_recommendation_records_owner_id", "investment_recommendation_records", ["owner_id"])
    op.create_index("ix_investment_recommendation_records_security_id", "investment_recommendation_records", ["security_id"])

    op.create_table(
        "investment_decision_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation_record_id", sa.Integer(), sa.ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision_id", sa.String(160), nullable=False, unique=True),
        sa.Column("recommendation_id", sa.String(160), nullable=False),
        sa.Column("recommendation_hash", sa.String(64), nullable=False),
        sa.Column("decision_type", sa.String(16), nullable=False),
        sa.Column("decision_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rationale", sa.String(2000)),
        sa.Column("actor_scope", sa.String(128), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key_hash", name="uq_investment_decisions_owner_idempotency"),
        sa.CheckConstraint("decision_type IN ('accept','reject','defer','modify','no_action')", name="ck_investment_decisions_type"),
        sa.CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_investment_decisions_idempotency"),
    )
    op.create_index("ix_investment_decision_records_owner_id", "investment_decision_records", ["owner_id"])
    op.create_index("ix_investment_decision_records_recommendation_record_id", "investment_decision_records", ["recommendation_record_id"])
    op.create_index("ix_investment_decision_records_recommendation_id", "investment_decision_records", ["recommendation_id"])
    for table in ("investment_committee_runs", "investment_committee_findings", "investment_evidence_packets", "investment_recommendation_records", "investment_decision_records"):
        _immutable(table)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("investment_decision_records", "investment_recommendation_records", "investment_committee_findings", "investment_evidence_packets", "investment_committee_runs"):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError(f"cannot downgrade non-empty immutable table {table}")
    for table in ("investment_committee_runs", "investment_committee_findings", "investment_evidence_packets", "investment_recommendation_records", "investment_decision_records"):
        _drop_immutable(table)
    for table in ("investment_decision_records", "investment_recommendation_records", "investment_committee_findings", "investment_evidence_packets", "investment_committee_runs"):
        op.drop_table(table)
