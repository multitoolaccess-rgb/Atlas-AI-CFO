"""Focused ORM constraints for Phase 1 immutable forecast persistence."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Forecast, ForecastVersion, Goal, User


def test_forecast_model_identity_and_decimal_constraints():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=1, local_user_sub="synthetic", email="synthetic@example.com", hashed_password="x"))
        session.add(Goal(id=1, user_id=1, name="Synthetic Goal", target_amount=1.0, priority=0, is_archived=False))
        session.add(Forecast(id="00000000-0000-4000-8000-000000000001", user_id=1, goal_id=1))
        session.commit()
        session.add(Forecast(id="00000000-0000-4000-8000-000000000003", user_id=1, goal_id=1))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        version = ForecastVersion(id="00000000-0000-4000-8000-000000000002", forecast_id="00000000-0000-4000-8000-000000000001", version_number=1, input_state_hash="a" * 64, idempotency_key_hash="b" * 64, snapshot_schema_version="v1", hash_schema_version="v1", model_version="model-v1", calculation_version="calc-v1", calculated_at=datetime.now(timezone.utc), data_as_of=datetime.now(timezone.utc), max_data_age_days=1, data_age_days=0, input_snapshot_json="{}", assumption_snapshot_json="{}", output_snapshot_json="{}", provenance_snapshot_json="{}", ending_balance=Decimal("1234.56"), target_gap=Decimal("-0.01"))
        session.add(version)
        session.commit()
        assert session.get(ForecastVersion, version.id).ending_balance == Decimal("1234.56")
