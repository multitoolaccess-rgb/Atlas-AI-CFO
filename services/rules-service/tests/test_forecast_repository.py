"""Repository transaction contracts for immutable forecast history."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.forecasts.canonical_state import CanonicalProjectionState
from app.forecasts.repository import (
    ForecastRepository,
    IdempotencyConflict,
    StaleForecastVersion,
)
from app.forecasts.snapshots import build_forecast_snapshots
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
        assumption_snapshot=_assumptions(),
        output_snapshot=_output(),
        ending_balance=Decimal("1234.56"),
        target_gap=Decimal("-1.00"),
        expected_latest_version=expected_latest_version,
    )


def _assumptions() -> dict[str, object]:
    return {
        "assumption_profile": "atlas-test-default",
        "annual_return_rates": {
            "conservative": "0.02",
            "base": "0.04",
            "optimistic": "0.06",
        },
        "annual_inflation_rate": "0.02",
        "contribution_timing": "end",
        "period": "monthly",
        "rounding_rule": "ROUND_HALF_EVEN",
        "money_precision": "0.01",
    }


def _output() -> dict[str, object]:
    return {
        "target_status": True,
        "drivers": {
            "current_balance": "1234.56",
            "monthly_contribution": "100",
            "total_contributions": "1200",
            "target_amount": "1000",
            "horizon_months": 12,
            "data_as_of": "2026-07-01",
            "data_age_days": 0,
        },
        "scenarios": {
            name: {
                "annual_return_rate": rate,
                "monthly_real_rate": "0.001",
                "ending_balance": "1234.56",
                "investment_growth": "10",
                "target_gap": "0",
                "reaches_target": True,
            }
            for name, rate in {
                "conservative": "0.02",
                "base": "0.04",
                "optimistic": "0.06",
            }.items()
        },
    }


def test_repository_persists_canonical_snapshots_and_only_hashed_idempotency_key(session: Session) -> None:
    result = _persist(ForecastRepository(session))
    assert not session.in_transaction()
    assert result.created is True
    assert result.version.version_number == 1
    assert result.version.input_snapshot_json == result.input_snapshot_json
    assert result.version.idempotency_key_hash == hashlib.sha256(b"atlas-test-key").hexdigest()
    # SQLite stores these legacy DateTime values without a timezone offset;
    # the canonical snapshot preserves the authoritative UTC representation.
    assert result.version.data_as_of == datetime(2026, 7, 1, 12)
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


def test_repository_recovers_committed_winner_after_database_conflict(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loser of a uniqueness race re-reads the committed winner safely."""

    first = _persist(ForecastRepository(session))
    contender = ForecastRepository(session)

    def concurrent_conflict(**_kwargs):
        raise IntegrityError("INSERT forecast_versions", {}, RuntimeError("unique conflict"))

    monkeypatch.setattr(contender, "_persist_once", concurrent_conflict)
    replay = _persist(contender)

    assert replay.created is False
    assert not session.in_transaction()
    assert replay.version.id == first.version.id


def test_repository_conflict_recovery_rejects_changed_state_for_same_key(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-reading a winner never turns a conflicting idempotency key into replay."""

    _persist(ForecastRepository(session))
    contender = ForecastRepository(session)
    changed = _state().model_copy(update={"as_of_timestamp": "2026-07-02T12:00:00Z"})

    def concurrent_conflict(**_kwargs):
        raise IntegrityError("INSERT forecast_versions", {}, RuntimeError("unique conflict"))

    monkeypatch.setattr(contender, "_persist_once", concurrent_conflict)
    with pytest.raises(IdempotencyConflict):
        _persist(contender, state=changed)
    assert not session.in_transaction()


def test_repository_recovers_real_sqlite_lock_race_with_committed_winner(tmp_path) -> None:
    """Independent SQLite sessions converge after a short writer lock releases."""

    engine = create_engine(
        f"sqlite:///{tmp_path / 'forecast-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 0.05},
    )
    Base.metadata.create_all(engine)
    state = _state()
    snapshots = build_forecast_snapshots(
        state=state,
        assumption_snapshot=_assumptions(),
        output_snapshot=_output(),
    )
    with Session(engine) as seed:
        seed.add(User(id=1, local_user_sub="atlas-test-user", email="atlas@example.com", hashed_password="x"))
        seed.add(Goal(id=1, user_id=1, name="Atlas Test Goal", target_amount=1000.0, priority=0, is_archived=False))
        seed.commit()

    writer = Session(engine)
    writer_repo = ForecastRepository(writer)
    writer_repo._persist_once(
        user_id=1,
        goal_id=1,
        key_hash=hashlib.sha256(b"atlas-test-key").hexdigest(),
        snapshots=snapshots,
        state=state,
        model_version="atlas-model-v1",
        calculation_version="phase0-projection-v1",
        calculated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
        ending_balance=Decimal("1234.56"),
        target_gap=Decimal("-1.00"),
        expected_latest_version=None,
    )
    result: list[object] = []

    def contend() -> None:
        with Session(engine) as contender_session:
            result.append(_persist(ForecastRepository(contender_session)))

    contender = threading.Thread(target=contend)
    contender.start()
    time.sleep(0.15)
    writer.commit()
    contender.join(timeout=3)
    writer.close()

    assert not contender.is_alive()
    assert len(result) == 1
    assert result[0].created is False


@pytest.mark.parametrize(
    "field",
    [
        "raw_statement",
        "raw_transactions",
        "credentials",
        "idempotency_key",
        "upload",
        "api_key",
        "access_token",
        "password",
        "authorization",
        "transaction_history",
    ],
)
def test_repository_rejects_raw_or_secret_snapshot_payloads(session: Session, field: str) -> None:
    repository = ForecastRepository(session)
    with pytest.raises(ValueError, match="bounded projection contract"):
        repository.persist(
            user_id=1, goal_id=1, state=_state(), idempotency_key="atlas-test-key",
            model_version="atlas-model-v1", calculation_version="phase0-projection-v1",
            calculated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
            assumption_snapshot={field: "SYNTHETIC-SECRET"}, output_snapshot=_output(),
            ending_balance=Decimal("1.00"), target_gap=Decimal("0.00"),
        )


@pytest.mark.parametrize(
    "snapshot",
    [
        {"assumption_profile": "atlas-test-default", "note": "SYNTHETIC-RAW-STATEMENT"},
        {"assumption_profile": "atlas-test-default", "metadata": {"value": "SYNTHETIC-TOKEN"}},
    ],
)
def test_repository_rejects_unknown_snapshot_fields_even_when_keys_look_benign(
    session: Session, snapshot: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="bounded projection contract"):
        ForecastRepository(session).persist(
            user_id=1,
            goal_id=1,
            state=_state(),
            idempotency_key="atlas-test-key",
            model_version="atlas-model-v1",
            calculation_version="phase0-projection-v1",
            calculated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
            assumption_snapshot=snapshot,
            output_snapshot=_output(),
            ending_balance=Decimal("1.00"),
            target_gap=Decimal("0.00"),
        )


@pytest.mark.parametrize(
    "assumptions,output",
    [
        ({"assumption_profile": "atlas-test-default"}, _output()),
        (_assumptions(), {"target_status": True}),
        (_assumptions(), {**_output(), "drivers": {}}),
        (
            _assumptions(),
            {
                **_output(),
                "scenarios": {
                    **_output()["scenarios"],
                    "base": {"annual_return_rate": "0.04"},
                },
            },
        ),
    ],
)
def test_repository_rejects_incomplete_immutable_snapshots(
    session: Session, assumptions: dict[str, object], output: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="bounded projection contract"):
        ForecastRepository(session).persist(
            user_id=1,
            goal_id=1,
            state=_state(),
            idempotency_key="atlas-test-key",
            model_version="atlas-model-v1",
            calculation_version="phase0-projection-v1",
            calculated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
            assumption_snapshot=assumptions,
            output_snapshot=output,
            ending_balance=Decimal("1.00"),
            target_gap=Decimal("0.00"),
        )
