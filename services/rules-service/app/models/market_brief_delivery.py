"""Phase 5 delivery preferences and immutable fake-delivery receipts."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from app.database import Base


class MarketBriefDeliveryPreference(Base):
    __tablename__ = "market_brief_delivery_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_market_brief_delivery_preference_user"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    email_authorized = Column(Boolean, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MarketBriefDeliveryAttempt(Base):
    __tablename__ = "market_brief_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "brief_id", "idempotency_key", name="uq_market_brief_delivery_attempt_idempotency"),
        CheckConstraint("status IN ('previewed', 'sent', 'failed')", name="ck_market_brief_delivery_status"),
    )
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    brief_id = Column(String(36), ForeignKey("market_briefs.id", ondelete="RESTRICT"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False)
    receipt = Column(String(160), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
