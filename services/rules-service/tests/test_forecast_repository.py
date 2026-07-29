"""Repository transaction contracts for immutable forecast history."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.forecasts.canonical_state import CanonicalProjectionState
from app.forecasts.repository import (
    ForecastRepository,
    IdempotencyConflict,
    StaleForecastVersion,
)
from app.models import Goal, User


def _state() -> CanonicalProjectionState:
    return CanonicalProjectionState.model_validate(
        json.loads(
            ("""{
              "schema_version":"atlas-projection-state/v1",
              "canonicalization":{"canonical_json_version":"atlas-canonical-json/v1","hash_schema_version":"atlas-input-state-hash/v1","hash_algorithm":"sha256"},
              "user_id":"atlas-test-user","goal_id":1,"as_of_timestamp":"2026-07-01T12:00:00Z","currency":"USD",
              "current_value_components":[{"kind":"investment","amount":"1234.56","source_reference":"atlas-test-account","observed_at":"2026-07-01T12:00:00Z"}],
              "contribution_inputs":[{"kind":"monthly_investable_cash_flow","amount":"100","source_reference":"atlas-test-cashflow","observed_at":"2026-07-01T12:00:00Z"}],
              "freshness":{"max_data_age_days":30,"observed_age_days":0,"source_updated_at":"2026-07-01T12:00:00Z"},
              "provenance":[{"source_system":"finlynq","reference_id":"atlas-test-aggregate","observed_at":"2026-07-01T12:00:00Z","record_count":1,"source_state_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],
              "missing_data_codes":[],"reconciliation_state":"reconciled"
            }""")
        )
    )


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, local_user_sub="atlas-test-user", email="atlas@example.com", hashed_password="x"))
        db.add(Goal(id=1, user_id=1, name="Atlas Test Goal", target_amount=1000.0, priority=0, is_archived=False))
        db.commit()
        yield db


def _persist(repository: ForecastRepository, *, key: str = "atlas-test-key", state: CanonicalProjectionState | None = None, expected_latest_version: int | None = None):
    return repository.persist(
        user_id=1,
        goal_id=1,
        state=state or _state(),
        idempotency_key=key,
        model_version="atlas-model-v1",
        calculation_version="phase0-projection-v1",
        calculated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
        assumption_snapshot={"assumption_profile":"atlas-test-default"},
        output_snapshot={"target_status": True},
        ending_balance=Decimal("1234.56"),
        target_gap=Decimal("-1.00"),
        expected_latest_version=expected_latest_version,
    )


def test_repository_persists_canonical_snapshots_and_only_hashed_idempotency_key(session: Session) -> None:
    result = _persist(ForecastRepository(session))
    assert result.created is True
    assert result.version.version_number == 1
    assert result.version.input_snapshot_json == result.input_snapshot_json
    assert result.version.idempotency_key_hash == hashlib.sha256(b"atlas-test-key").hexdigest()
    assert result.version.data_as_of == datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    assert "atlas-test-key" not in result.version.input_snapshot_json
    assert not hasattr(result.version, "idempotency_key")


def test_repository_replays_same_key_and_converges_same_state_with_new_key(session: Session) -> None:
    repository = ForecastRepository(session)
    first = _persist(repository)
    replay = _persist(repository)
    same_state = _persist(repository, key="atlas-test-key-2")
    assert replay.created is False and replay.version.id == first.version.id
    assert same_state.created is False and same_state.version.id == first.version.id


def test_repository_rejects_reused_key_for_different_state(session: Session) -> None:
    repository = ForecastRepository(session)
    _persist(repository)
    changed = _state().model_copy(update={"as_of_timestamp": "2026-07-02T12:00:00Z"})
    with pytest.raises(IdempotencyConflict):
        _persist(repository, state=changed)


def test_repository_rejects_stale_latest_version(session: Session) -> None:
    repository = ForecastRepository(session)
    _persist(repository)
    with pytest.raises(StaleForecastVersion):
        _persist(repository, key="atlas-test-key-2", expected_latest_version=0)


@pytest.mark.parametrize("field", ["raw_statement", "raw_transactions", "credentials", "idempotency_key", "upload"])
def test_repository_rejects_raw_or_secret_snapshot_payloads(session: Session, field: str) -> None:
    repository = ForecastRepository(session)
    with pytest.raises(ValueError, match="raw source payloads"):
        repository.persist(
            user_id=1, goal_id=1, state=_state(), idempotency_key="atlas-test-key",
            model_version="atlas-model-v1", calculation_version="phase0-projection-v1",
            calculated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
            assumption_snapshot={field: "SYNTHETIC-SECRET"}, output_snapshot={},
            ending_balance=Decimal("1.00"), target_gap=Decimal("0.00"),
        )
