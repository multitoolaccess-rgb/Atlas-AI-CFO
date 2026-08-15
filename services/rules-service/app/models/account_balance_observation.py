"""Mirror of Finlynq's append-only balance-observation audit table."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class AccountBalanceObservation(Base):
    __tablename__ = "account_balance_observations"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_kind = Column(String(32), nullable=False)
    actor_category = Column(String(32), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    precondition_hash = Column(String(64), nullable=False)
    observation_intent_hash = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key_hash", name="uq_account_balance_observations_idempotency"),
        CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_account_balance_observations_id_shape"),
        CheckConstraint("source_kind = 'operator_confirmed'", name="ck_account_balance_observations_source_kind"),
        CheckConstraint("actor_category = 'local_operator'", name="ck_account_balance_observations_actor_category"),
        CheckConstraint("length(precondition_hash) = 64 AND precondition_hash = lower(precondition_hash)", name="ck_account_balance_observations_precondition_hash"),
        CheckConstraint("length(observation_intent_hash) = 64 AND observation_intent_hash = lower(observation_intent_hash)", name="ck_account_balance_observations_intent_hash"),
        CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_account_balance_observations_idempotency_hash"),
    )
