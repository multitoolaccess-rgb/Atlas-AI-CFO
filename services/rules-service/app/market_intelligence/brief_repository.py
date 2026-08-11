"""Idempotent repository for immutable market brief records."""
import json
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.market_brief import MarketBrief
from .briefing import MarketBrief as BriefPayload


class MarketBriefRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(self, brief: BriefPayload) -> tuple[MarketBrief, bool]:
        filters = dict(user_id=brief.owner_id, portfolio_state_hash=brief.portfolio_state_hash, universe_hash=brief.universe_hash, report_window=brief.report_window, schema_version=brief.schema_version, calculation_version=brief.calculation_version)
        existing = self._session.scalar(select(MarketBrief).filter_by(**filters))
        if existing is not None:
            return existing, True
        row = MarketBrief(id=str(uuid.uuid4()), generated_at=brief.generated_at, payload_json=brief.model_dump_json(), **filters)
        try:
            self._session.add(row)
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            winner = self._session.scalar(select(MarketBrief).filter_by(**filters))
            if winner is None:
                raise
            return winner, True
        return row, False

    def get_owned(self, *, user_id: int, brief_id: str) -> MarketBrief | None:
        return self._session.scalar(select(MarketBrief).where(MarketBrief.id == brief_id, MarketBrief.user_id == user_id))
