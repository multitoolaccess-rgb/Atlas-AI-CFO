"""Trusted generation-service contracts; no HTTP route is exercised here."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.forecasts.canonical_state import CanonicalProjectionState
from app.forecasts.repository import IdempotencyConflict
from app.forecasts.service import ForecastGenerationService, ForecastGenerationUnavailable
from app.models import Goal, User


def _state(*, amount="1000", user="atlas-user", goal_id=1, currency="USD", missing=()):
    return CanonicalProjectionState.model_validate({"schema_version":"atlas-projection-state/v1","canonicalization":{"canonical_json_version":"atlas-canonical-json/v1","hash_schema_version":"atlas-input-state-hash/v1","hash_algorithm":"sha256"},"user_id":user,"goal_id":goal_id,"as_of_timestamp":"2026-07-01T12:00:00Z","currency":currency,"current_value_components":[{"kind":"investment","amount":amount,"source_reference":"atlas-test-account","observed_at":"2026-07-01T12:00:00Z"}],"contribution_inputs":[{"kind":"monthly_investable_cash_flow","amount":"100","source_reference":"atlas-test-plan","observed_at":"2026-07-01T12:00:00Z"}],"freshness":{"max_data_age_days":30,"observed_age_days":0,"source_updated_at":"2026-07-01T12:00:00Z"},"provenance":[{"source_system":"finlynq","reference_id":"atlas-test","observed_at":"2026-07-01T12:00:00Z","record_count":1,"source_state_hash":"a"*64}],"missing_data_codes":list(missing),"reconciliation_state":"reconciled"})


class Adapter:
    def __init__(self, state): self.state, self.calls = state, 0
    def load_projection_state(self, *, user_id, goal_id): self.calls += 1; return self.state


@pytest.fixture()
def db():
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([User(id=1,local_user_sub="atlas-user",email="atlas@example.com",hashed_password="x"), Goal(id=1,user_id=1,name="Synthetic",target_amount=2000.0,horizon_years=2,priority=0,is_archived=False)])
        s.commit(); yield s


def test_authorizes_before_adapter_and_persists_complete_snapshots(db):
    adapter=Adapter(_state()); service=ForecastGenerationService(db, adapter)
    created=service.generate(user_id=1,user_sub="atlas-user",goal_id=1,idempotency_key="atlas-key",now=datetime(2026,7,2,tzinfo=timezone.utc))
    assert adapter.calls == 1 and created.persisted.created
    assert 'atlas-projection-assumptions/v1' in created.persisted.version.assumption_snapshot_json
    assert 'atlas-target-decision/v2' in created.persisted.version.output_snapshot_json


def test_cross_user_goal_does_not_invoke_adapter(db):
    adapter=Adapter(_state())
    with pytest.raises(ForecastGenerationUnavailable): ForecastGenerationService(db,adapter).generate(user_id=2,user_sub="other",goal_id=1,idempotency_key="atlas-key",now=datetime(2026,7,2,tzinfo=timezone.utc))
    assert adapter.calls == 0


def test_idempotent_replay_and_changed_state_do_not_replay_old_version(db):
    adapter=Adapter(_state()); service=ForecastGenerationService(db,adapter); now=datetime(2026,7,2,tzinfo=timezone.utc)
    first=service.generate(user_id=1,user_sub="atlas-user",goal_id=1,idempotency_key="atlas-key",now=now)
    replay=service.generate(user_id=1,user_sub="atlas-user",goal_id=1,idempotency_key="atlas-key",now=now)
    assert not replay.persisted.created and replay.persisted.version.id == first.persisted.version.id
    adapter.state=_state(amount="1001")
    with pytest.raises(IdempotencyConflict): service.generate(user_id=1,user_sub="atlas-user",goal_id=1,idempotency_key="atlas-key",now=now)


def test_goal_input_change_changes_hash_and_cannot_replay_old_forecast(db):
    adapter = Adapter(_state())
    service = ForecastGenerationService(db, adapter)
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)
    first = service.generate(user_id=1, user_sub="atlas-user", goal_id=1, idempotency_key="atlas-key", now=now)

    goal = db.get(Goal, 1)
    assert goal is not None
    goal.target_amount = 2001.0
    goal.horizon_years = 3
    db.commit()

    changed = service.generate(user_id=1, user_sub="atlas-user", goal_id=1, idempotency_key="atlas-key-changed-goal", now=now)
    assert changed.persisted.created
    assert changed.persisted.version.id != first.persisted.version.id
    assert changed.persisted.version.input_state_hash != first.persisted.version.input_state_hash

    with pytest.raises(IdempotencyConflict):
        service.generate(user_id=1, user_sub="atlas-user", goal_id=1, idempotency_key="atlas-key", now=now)


def test_goal_deadline_change_changes_hash_and_cannot_replay_old_forecast(db):
    adapter = Adapter(_state())
    service = ForecastGenerationService(db, adapter)
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)
    first = service.generate(user_id=1, user_sub="atlas-user", goal_id=1, idempotency_key="atlas-key", now=now)

    goal = db.get(Goal, 1)
    assert goal is not None
    goal.target_date = date(2028, 7, 2)
    db.commit()

    changed = service.generate(user_id=1, user_sub="atlas-user", goal_id=1, idempotency_key="atlas-key-deadline", now=now)
    assert changed.persisted.created
    assert changed.persisted.version.input_state_hash != first.persisted.version.input_state_hash
    assert '"target_date":"2028-07-02"' in changed.persisted.version.assumption_snapshot_json

    with pytest.raises(IdempotencyConflict):
        service.generate(user_id=1, user_sub="atlas-user", goal_id=1, idempotency_key="atlas-key", now=now)


def test_rejects_missing_authoritative_state(db):
    for state in (_state(missing=("legacy_float_balance_representation",)),):
        with pytest.raises(ForecastGenerationUnavailable): ForecastGenerationService(db,Adapter(state)).generate(user_id=1,user_sub="atlas-user",goal_id=1,idempotency_key="atlas-key",now=datetime(2026,7,2,tzinfo=timezone.utc))
