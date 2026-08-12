"""Repository contracts for immutable Scenario Lab persistence."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Forecast, ForecastVersion, Goal, ScenarioVersion, User
from app.scenarios.contracts import ScenarioInput
from app.scenarios.engine import ScenarioCalculation, calculate_scenario
from app.scenarios.repository import ScenarioIdempotencyConflict, ScenarioNotFound, ScenarioRepository
from app.calculations.projection import ProjectionRequest, project_scenarios


def _request() -> ProjectionRequest:
    return ProjectionRequest(
        currency="USD", current_balance=Decimal("1000"), monthly_contribution=Decimal("100"), horizon_months=12,
        calculation_date=date(2026, 1, 15), data_as_of=date(2026, 1, 15), max_data_age_days=30,
        contribution_timing="end_of_month", annual_inflation_rate=Decimal("0.02"),
        annual_return_rates={"conservative": Decimal("0.02"), "base": Decimal("0.04"), "optimistic": Decimal("0.06")}, target_amount=Decimal("2500"),
    )


def _calculation(delta: str = "10") -> ScenarioCalculation:
    request = _request()
    result = project_scenarios(request)
    baseline = {"drivers": {"target_amount": str(result.drivers.target_amount)}, "scenarios": {}}
    for name, item in result.scenarios.items():
        baseline["scenarios"][name] = {"ending_balance": str(item.ending_balance), "target_gap": str(item.target_gap), "reaches_target": item.reaches_target}
    from app.scenarios.engine import calculate_scenario
    return calculate_scenario(
        request=request,
        scenario_input=ScenarioInput(monthly_contribution_delta=delta),
        baseline_forecast_id="11111111-1111-4111-8111-111111111111",
        baseline_version_number=1,
        baseline_input_state_hash="a" * 64,
        baseline_output_snapshot=baseline,
    )


def _seed(session: Session) -> None:
    session.add(User(id=1, local_user_sub="atlas-user", email="atlas@example.com", hashed_password="synthetic"))
    session.add(Goal(id=1, user_id=1, name="Synthetic Goal", target_amount=2500.0, horizon_years=1, priority=0, is_archived=False))
    session.add(Forecast(id="11111111-1111-4111-8111-111111111111", user_id=1, goal_id=1, forecast_kind="goal_projection", currency="USD", lifecycle_state="active", latest_version_number=1))
    session.add(ForecastVersion(
        id="22222222-2222-4222-8222-222222222222", forecast_id="11111111-1111-4111-8111-111111111111", version_number=1,
        input_state_hash="b" * 64, idempotency_key_hash="c" * 64, snapshot_schema_version="atlas-projection-state/v1", hash_schema_version="atlas-input-state-hash/v1",
        model_version="atlas-monthly-scenarios/v1", calculation_version="atlas-monthly-scenarios/v1", currency="USD",
        calculated_at=datetime(2026, 1, 15, tzinfo=timezone.utc), data_as_of=datetime(2026, 1, 15, tzinfo=timezone.utc), max_data_age_days=30, data_age_days=0,
        input_snapshot_json="{}", assumption_snapshot_json="{}", output_snapshot_json="{}", provenance_snapshot_json="{}", ending_balance=Decimal("1"), target_gap=Decimal("0"),
    ))
    session.commit()


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        yield session


def _persist(session: Session, *, key: str = "scenario-key", scenario_id: str | None = None, calculation: ScenarioCalculation | None = None):
    return ScenarioRepository(session).persist(
        user_id=1, goal_id=1, scenario_id=scenario_id,
        baseline_forecast_id="11111111-1111-4111-8111-111111111111", baseline_version_number=1,
        calculation=calculation or _calculation(), idempotency_key=key, calculated_at=datetime(2026, 1, 16, tzinfo=timezone.utc),
    )


def test_persist_replay_and_same_state_converge_without_plaintext_key(session: Session) -> None:
    first = _persist(session)
    replay = _persist(session)
    assert first.created is True
    assert replay.created is False
    assert replay.version.id == first.version.id
    assert "scenario-key" not in first.version.input_snapshot_json
    assert first.version.idempotency_key_hash != "scenario-key"


def test_same_scenario_id_creates_immutable_monotonic_version(session: Session) -> None:
    first = _persist(session)
    second = _persist(session, scenario_id=first.scenario.id, key="scenario-key-2", calculation=_calculation("20"))
    assert second.created is True
    assert second.version.version_number == 2
    assert session.scalar(select(ScenarioVersion).where(ScenarioVersion.id == first.version.id)) is not None


def test_divergent_idempotency_key_conflicts_for_same_scenario(session: Session) -> None:
    first = _persist(session)
    with pytest.raises(ScenarioIdempotencyConflict):
        _persist(session, scenario_id=first.scenario.id, key="scenario-key", calculation=_calculation("20"))


def test_cross_owner_scenario_id_is_not_disclosed(session: Session) -> None:
    first = _persist(session)
    with pytest.raises(ScenarioNotFound):
        ScenarioRepository(session).persist(
            user_id=2, goal_id=1, scenario_id=first.scenario.id,
            baseline_forecast_id="11111111-1111-4111-8111-111111111111", baseline_version_number=1,
            calculation=_calculation(), idempotency_key="other-key", calculated_at=datetime(2026, 1, 16, tzinfo=timezone.utc),
        )


def test_archive_preserves_all_immutable_versions_and_blocks_new_version(session: Session) -> None:
    first = _persist(session)
    second = _persist(session, scenario_id=first.scenario.id, key="scenario-key-2", calculation=_calculation("20"))
    archived = ScenarioRepository(session).archive(user_id=1, scenario_id=first.scenario.id, idempotency_key="archive-key")
    assert archived.lifecycle_state == "archived"
    assert session.scalar(select(ScenarioVersion).where(ScenarioVersion.id == first.version.id)) is not None
    assert session.scalar(select(ScenarioVersion).where(ScenarioVersion.id == second.version.id)) is not None
    with pytest.raises(Exception, match="archived"):
        _persist(session, scenario_id=first.scenario.id, key="scenario-key-3", calculation=_calculation("30"))


def test_snapshot_rejects_sensitive_field_names(session: Session) -> None:
    calculation = _calculation()
    calculation = ScenarioCalculation(
        scenario_input_hash=calculation.scenario_input_hash,
        input_snapshot={**calculation.input_snapshot, "raw_transactions": "synthetic"},
        result_snapshot=calculation.result_snapshot,
        comparison_snapshot=calculation.comparison_snapshot,
        baseline_input_state_hash=calculation.baseline_input_state_hash,
        source_data_as_of=calculation.source_data_as_of,
        data_age_days=calculation.data_age_days,
        max_data_age_days=calculation.max_data_age_days,
    )
    with pytest.raises(ValueError, match="prohibited"):
        _persist(session, calculation=calculation)
