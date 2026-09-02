from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.investments.persistence_service import InvestmentPersistenceError, InvestmentPersistenceService
from app.models import InvestmentOutcomeRecord


def test_outcome_record_is_registered_and_separate_from_recommendation():
    assert InvestmentOutcomeRecord.__tablename__ == "investment_outcome_records"
    assert "investment_recommendation_records" in Base.metadata.tables
    assert InvestmentOutcomeRecord.__table__.c.payload_json is not InvestmentOutcomeRecord.__table__.c.recommendation_hash


def test_outcome_requires_persisted_recommendation():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = InvestmentPersistenceService(session)
        with pytest.raises(AttributeError):
            service.record_outcome(object(), tracking=object())
