"""Immutable, user-scoped forecast identity and history models (Phase 1)."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class Forecast(Base):
    """Mutable identity row; calculation reasoning lives only in versions."""

    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("user_id", "goal_id", "forecast_kind", "currency", name="uq_forecasts_identity"),
        CheckConstraint("forecast_kind = 'goal_projection'", name="ck_forecasts_kind"),
        CheckConstraint("currency = 'USD'", name="ck_forecasts_currency"),
        CheckConstraint("lifecycle_state = 'active'", name="ck_forecasts_lifecycle"),
        CheckConstraint("latest_version_number >= 0", name="ck_forecasts_latest_version"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_forecasts_id_shape"),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False, index=True)
    forecast_kind = Column(String(32), nullable=False, default="goal_projection", server_default="goal_projection")
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")
    lifecycle_state = Column(String(16), nullable=False, default="active", server_default="active")
    latest_version_number = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    versions = relationship("ForecastVersion", back_populates="forecast", passive_deletes=True)


class ForecastVersion(Base):
    """Append-only reasoning, output, freshness, and provenance record."""

    __tablename__ = "forecast_versions"
    __table_args__ = (
        UniqueConstraint("forecast_id", "version_number", name="uq_forecast_versions_number"),
        UniqueConstraint("forecast_id", "input_state_hash", "model_version", "calculation_version", name="uq_forecast_versions_input"),
        UniqueConstraint("forecast_id", "idempotency_key_hash", name="uq_forecast_versions_idempotency"),
        CheckConstraint("version_number > 0", name="ck_forecast_versions_positive_number"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_forecast_versions_id_shape"),
        CheckConstraint("currency = 'USD'", name="ck_forecast_versions_currency"),
        CheckConstraint("length(input_state_hash) = 64", name="ck_forecast_versions_input_hash_length"),
        CheckConstraint("input_state_hash = lower(input_state_hash)", name="ck_forecast_versions_input_hash_lower"),
        CheckConstraint("length(idempotency_key_hash) = 64", name="ck_forecast_versions_idempotency_hash_length"),
        CheckConstraint("idempotency_key_hash = lower(idempotency_key_hash)", name="ck_forecast_versions_idempotency_hash_lower"),
        CheckConstraint("length(snapshot_schema_version) <= 64", name="ck_forecast_versions_snapshot_version_length"),
        CheckConstraint("length(trim(snapshot_schema_version)) > 0", name="ck_forecast_versions_snapshot_version_present"),
        CheckConstraint("length(hash_schema_version) <= 64", name="ck_forecast_versions_hash_version_length"),
        CheckConstraint("length(trim(hash_schema_version)) > 0", name="ck_forecast_versions_hash_version_present"),
        CheckConstraint("length(model_version) <= 128", name="ck_forecast_versions_model_version_length"),
        CheckConstraint("length(trim(model_version)) > 0", name="ck_forecast_versions_model_version_present"),
        CheckConstraint("length(calculation_version) <= 128", name="ck_forecast_versions_calculation_version_length"),
        CheckConstraint("length(trim(calculation_version)) > 0", name="ck_forecast_versions_calculation_version_present"),
        CheckConstraint("max_data_age_days >= 0", name="ck_forecast_versions_max_data_age"),
        CheckConstraint("data_age_days >= 0", name="ck_forecast_versions_data_age"),
    )

    id = Column(String(36), primary_key=True)
    forecast_id = Column(String(36), ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    input_state_hash = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    snapshot_schema_version = Column(String(64), nullable=False)
    hash_schema_version = Column(String(64), nullable=False)
    model_version = Column(String(128), nullable=False)
    calculation_version = Column(String(128), nullable=False)
    currency = Column(String(3), nullable=False, default="USD", server_default="USD")
    calculated_at = Column(DateTime(timezone=True), nullable=False)
    data_as_of = Column(DateTime(timezone=True), nullable=False)
    max_data_age_days = Column(Integer, nullable=False)
    data_age_days = Column(Integer, nullable=False)
    input_snapshot_json = Column(Text, nullable=False)
    assumption_snapshot_json = Column(Text, nullable=False)
    output_snapshot_json = Column(Text, nullable=False)
    provenance_snapshot_json = Column(Text, nullable=False)
    ending_balance = Column(Numeric(38, 2, asdecimal=True), nullable=False)
    target_gap = Column(Numeric(38, 2, asdecimal=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    forecast = relationship("Forecast", back_populates="versions")
