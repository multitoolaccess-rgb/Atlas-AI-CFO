"""Concurrency proof for omitted Scenario Lab identity generation."""
from datetime import datetime, timezone
import threading

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Scenario, ScenarioVersion
from app.scenarios.repository import ScenarioRepository
from tests.test_scenario_repository import _calculation, _seed


def test_concurrent_same_input_converges_to_one_scenario_and_version(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'scenario-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 0.05},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as seed_session:
        _seed(seed_session)
    results: list[object] = []
    failures: list[Exception] = []

    def generate(key: str) -> None:
        try:
            with Session(engine) as session:
                persisted = ScenarioRepository(session).persist(
                    user_id=1,
                    goal_id=1,
                    scenario_id=None,
                    baseline_forecast_id="11111111-1111-4111-8111-111111111111",
                    baseline_version_number=1,
                    calculation=_calculation("25"),
                    idempotency_key=key,
                    calculated_at=datetime(2026, 1, 16, tzinfo=timezone.utc),
                )
                results.append((persisted.scenario.id, persisted.version.id))
        except Exception as exc:  # pragma: no cover - assertion below reports it
            failures.append(exc)

    threads = [threading.Thread(target=generate, args=(f"race-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert not failures, failures
    assert len(results) == 2
    assert {item[0] for item in results}.__len__() == 1
    assert {item[1] for item in results}.__len__() == 1
    with Session(engine) as session:
        assert len(session.scalars(select(Scenario)).all()) == 1
        assert len(session.scalars(select(ScenarioVersion)).all()) == 1
