"""Immutable Scenario Lab identity and version history models."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class Scenario(Base):
    """Stable owner/goal identity with mutable lifecycle pointer only."""

    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint("lifecycle_state IN ('active', 'archived')", name="ck_scenarios_lifecycle"),
        CheckConstraint("currency = 'USD'", name="ck_scenarios_currency"),
        CheckConstraint("latest_version_number >= 0", name="ck_scenarios_latest_version"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_scenarios_id_shape"),
        CheckConstraint("archive_idempotency_key_hash IS NULL OR (length(archive_idempotency_key_hash) = 64 AND archive_idempotency_key_hash = lower(archive_idempotency_key_hash))", name="ck_scenarios_archive_idempotency_hash"),
        UniqueConstraint("user_id", "goal_id", "id", name="uq_scenarios_owner_goal_id"),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    baseline_forecast_id = Column(String(36), ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")
    lifecycle_state = Column(String(16), nullable=False, default="active", server_default="active")
    latest_version_number = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archive_idempotency_key_hash = Column(String(64), nullable=True)

    versions = relationship("ScenarioVersion", back_populates="scenario", passive_deletes=True)


class ScenarioVersion(Base):
    """Append-only complete deterministic scenario result snapshot."""

    __tablename__ = "scenario_versions"
    __table_args__ = (
        UniqueConstraint("scenario_id", "version_number", name="uq_scenario_versions_number"),
        UniqueConstraint("scenario_id", "scenario_input_hash", "model_version", "calculation_version", name="uq_scenario_versions_input"),
        UniqueConstraint("scenario_id", "idempotency_key_hash", name="uq_scenario_versions_idempotency"),
        CheckConstraint("version_number > 0", name="ck_scenario_versions_positive_number"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_scenario_versions_id_shape"),
        CheckConstraint("currency = 'USD'", name="ck_scenario_versions_currency"),
        CheckConstraint("length(baseline_forecast_id) = 36 AND baseline_forecast_id = lower(baseline_forecast_id)", name="ck_scenario_versions_baseline_id_shape"),
        CheckConstraint("length(baseline_input_state_hash) = 64 AND baseline_input_state_hash = lower(baseline_input_state_hash)", name="ck_scenario_versions_baseline_hash"),
        CheckConstraint("length(scenario_input_hash) = 64 AND scenario_input_hash = lower(scenario_input_hash)", name="ck_scenario_versions_input_hash"),
        CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_scenario_versions_idempotency_hash"),
        CheckConstraint("length(schema_version) > 0 AND length(schema_version) <= 64", name="ck_scenario_versions_schema_version"),
        CheckConstraint("length(model_version) > 0 AND length(model_version) <= 128", name="ck_scenario_versions_model_version"),
        CheckConstraint("length(calculation_version) > 0 AND length(calculation_version) <= 128", name="ck_scenario_versions_calculation_version"),
        CheckConstraint("max_data_age_days >= 0 AND data_age_days >= 0", name="ck_scenario_versions_freshness"),
    )

    id = Column(String(36), primary_key=True)
    scenario_id = Column(String(36), ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    baseline_forecast_id = Column(String(36), ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=False, index=True)
    baseline_version_number = Column(Integer, nullable=False)
    baseline_input_state_hash = Column(String(64), nullable=False)
    scenario_input_hash = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    schema_version = Column(String(64), nullable=False)
    model_version = Column(String(128), nullable=False)
    calculation_version = Column(String(128), nullable=False)
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")
    calculated_at = Column(DateTime(timezone=True), nullable=False)
    source_data_as_of = Column(DateTime(timezone=True), nullable=False)
    max_data_age_days = Column(Integer, nullable=False)
    data_age_days = Column(Integer, nullable=False)
    input_snapshot_json = Column(Text, nullable=False)
    result_snapshot_json = Column(Text, nullable=False)
    comparison_snapshot_json = Column(Text, nullable=False)
    recommendation_reference = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    scenario = relationship("Scenario", back_populates="versions")
