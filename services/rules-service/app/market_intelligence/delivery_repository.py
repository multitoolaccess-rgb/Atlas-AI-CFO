"""Idempotent, immutable delivery attempt persistence."""
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.market_brief_delivery import MarketBriefDeliveryAttempt, MarketBriefDeliveryPreference


class DeliveryRepository:
    def __init__(self, session: Session) -> None: self.session = session
    def preference(self, user_id: int) -> MarketBriefDeliveryPreference | None:
        return self.session.scalar(select(MarketBriefDeliveryPreference).where(MarketBriefDeliveryPreference.user_id == user_id))
    def record(self, *, user_id: int, brief_id: str, idempotency_key: str, status: str, receipt: str | None) -> tuple[MarketBriefDeliveryAttempt, bool]:
        existing = self.session.scalar(select(MarketBriefDeliveryAttempt).where(MarketBriefDeliveryAttempt.user_id == user_id, MarketBriefDeliveryAttempt.brief_id == brief_id, MarketBriefDeliveryAttempt.idempotency_key == idempotency_key))
        if existing: return existing, True
        row = MarketBriefDeliveryAttempt(id=str(uuid.uuid4()), user_id=user_id, brief_id=brief_id, idempotency_key=idempotency_key, status=status, receipt=receipt)
        try:
            self.session.add(row); self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return self.session.scalar(select(MarketBriefDeliveryAttempt).where(MarketBriefDeliveryAttempt.user_id == user_id, MarketBriefDeliveryAttempt.brief_id == brief_id, MarketBriefDeliveryAttempt.idempotency_key == idempotency_key)), True
        return row, False
