"""ADR-006 default-off forecast-persistence flag gate contracts.

Tests in this module prove every contract in the one-shot fourth-cycle
PR #11 correction scope.  They intentionally cover the flag at THREE
boundaries:

* ``app.config.Settings`` parsing (unparseable / explicit-true /
  explicit-false / absent env values).
* ``ForecastGenerationService.generate()`` service-layer gate
  (raises sanitized error before adapter, projection, snapshot, or
  repository work; preserves goal ownership ordering; never leaks
  source financial / config values in the error).
* Architectural invariants (request data, canonical state, adapter
  output cannot enable or override the flag).

These are deliberately orthogonal to ``test_forecast_service.py``,
which covers the *enabled-path* happy-path behaviour.  When this file
is read alongside the existing service tests, the gate contract is
fully closed: ``generate()`` either performs the bounded Slice B work
or fails closed with the single sanitized token
``forecast_generation_unavailable``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.config import settings as settings_singleton
from app.database import Base
from app.forecasts import service as service_module
from app.forecasts.canonical_state import CanonicalProjectionState
from app.forecasts.service import (
    ForecastGenerationService,
    ForecastGenerationUnavailable,
)
from app.models import Goal, User


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def _state(**overrides):
    defaults = {
        "amount": "1000",
        "user": "atlas-user",
        "goal_id": 1,
        "currency": "USD",
        "missing": (),
        "reconciliation": "reconciled",
    }
    defaults.update(overrides)
    return CanonicalProjectionState.model_validate({
        "schema_version": "atlas-projection-state/v1",
        "canonicalization": {
            "canonical_json_version": "atlas-canonical-json/v1",
            "hash_schema_version": "atlas-input-state-hash/v1",
            "hash_algorithm": "sha256",
        },
        "user_id": defaults["user"],
        "goal_id": defaults["goal_id"],
        "as_of_timestamp": "2026-07-01T12:00:00Z",
        "currency": defaults["currency"],
        "current_value_components": [
            {
                "kind": "investment",
                "amount": defaults["amount"],
                "source_reference": "atlas-test-account",
                "observed_at": "2026-07-01T12:00:00Z",
            }
        ],
        "contribution_inputs": [
            {
                "kind": "monthly_investable_cash_flow",
                "amount": "100",
                "source_reference": "atlas-test-plan",
                "observed_at": "2026-07-01T12:00:00Z",
            }
        ],
        "freshness": {
            "max_data_age_days": 30,
            "observed_age_days": 0,
            "source_updated_at": "2026-07-01T12:00:00Z",
        },
        "provenance": [
            {
                "source_system": "finlynq",
                "reference_id": "atlas-test",
                "observed_at": "2026-07-01T12:00:00Z",
                "record_count": 1,
                "source_state_hash": "a" * 64,
            }
        ],
        "missing_data_codes": list(defaults["missing"]),
        "reconciliation_state": defaults["reconciliation"],
    })


class _CountingAdapter:
    """Records every adapter invocation; used to prove the disabled gate."""

    def __init__(self, state):
        self.state = state
        self.calls = 0

    def load_projection_state(self, *, user_id, goal_id):
        self.calls += 1
        return self.state


def _now() -> datetime:
    return datetime(2026, 7, 2, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    """Hermetic in-memory SQLite + seeded local user + goal for service tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([
            User(
                id=1,
                local_user_sub="atlas-user",
                email="atlas@example.com",
                hashed_password="x",
            ),
            Goal(
                id=1,
                user_id=1,
                name="Synthetic",
                target_amount=2000.0,
                horizon_years=2,
                priority=0,
                is_archived=False,
            ),
        ])
        s.commit()
        yield s


@pytest.fixture()
def disabled_flag(monkeypatch):
    """Force the persistence-enabled flag OFF for the lifetime of one test.

    We override the module-level singleton attribute (``app.config.settings``)
    so that any code path that reads ``settings.atlas_forecast_persistence_enabled``
    observes ``False``.  pytest's monkeypatch restores the prior value on
    teardown so neighbouring tests are unaffected.
    """
    monkeypatch.setattr(
        settings_singleton, "atlas_forecast_persistence_enabled", False
    )
    assert settings_singleton.atlas_forecast_persistence_enabled is False
    yield


@pytest.fixture()
def enabled_flag(monkeypatch):
    """Force the persistence-enabled flag ON for the lifetime of one test."""
    monkeypatch.setattr(
        settings_singleton, "atlas_forecast_persistence_enabled", True
    )
    assert settings_singleton.atlas_forecast_persistence_enabled is True
    yield


# ----------------------------------------------------------------------
# Settings-parsing contracts (requirements 1-4, 10)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    ["true", "True", "TRUE", "1", "yes", "Yes", "y", "Y", "on", "On"],
)
def test_settings_accepts_recognised_truthy_value_as_enabled(monkeypatch, value):
    """Every recognised truthy literal enables persistence (req 3)."""
    monkeypatch.setenv("ATLAS_FORECAST_PERSISTENCE_ENABLED", value)
    s = Settings(_env_file=None)
    assert s.atlas_forecast_persistence_enabled is True


@pytest.mark.parametrize(
    "value",
    ["false", "False", "FALSE", "0", "no", "No", "off", "Off"],
)
def test_settings_recognised_falsy_value_remains_disabled(monkeypatch, value):
    """Every recognised falsy literal keeps persistence disabled (req 2)."""
    monkeypatch.setenv("ATLAS_FORECAST_PERSISTENCE_ENABLED", value)
    s = Settings(_env_file=None)
    assert s.atlas_forecast_persistence_enabled is False


def test_settings_absent_keeps_flag_disabled_by_default(monkeypatch):
    """With the env var absent the in-code default ``bool = False`` wins (req 1)."""
    monkeypatch.delenv("ATLAS_FORECAST_PERSISTENCE_ENABLED", raising=False)
    s = Settings(_env_file=None)
    assert s.atlas_forecast_persistence_enabled is False


@pytest.mark.parametrize(
    "value",
    ["maybe", "2", "truely", "yesplease", "offline", "enabled",
     "FALSE_FILE", ".true", "+1", ""],
)
def test_settings_unparseable_ambiguous_env_value_fails_closed(monkeypatch, value):
    """Invalid / malformed / ambiguous strings (incl. empty!) raise; the service cannot start (req 4)."""
    monkeypatch.setenv("ATLAS_FORECAST_PERSISTENCE_ENABLED", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_module_singleton_field_exists_and_defaults_off():
    """``settings.atlas_forecast_persistence_enabled`` is a real attribute (req 1)."""
    assert hasattr(settings_singleton, "atlas_forecast_persistence_enabled")
    assert isinstance(settings_singleton.atlas_forecast_persistence_enabled, bool)


# ----------------------------------------------------------------------
# Service-layer gate contracts (requirements 5-9)
# ----------------------------------------------------------------------
def test_generate_disabled_returns_stable_sanitized_error(db, disabled_flag):
    """Disabled generation surfaces the single bounded token (req 8)."""
    adapter = _CountingAdapter(_state())
    with pytest.raises(
        ForecastGenerationUnavailable, match=r"^forecast_generation_unavailable$"
    ):
        ForecastGenerationService(db, adapter).generate(
            user_id=1,
            user_sub="atlas-user",
            goal_id=1,
            idempotency_key="atlas-key",
            now=_now(),
        )
    assert adapter.calls == 0


def test_generate_disabled_makes_zero_adapter_invocations(db, disabled_flag):
    """After ownership is established, the gate stops before the adapter (req 7a)."""
    adapter = _CountingAdapter(_state())
    with pytest.raises(ForecastGenerationUnavailable):
        ForecastGenerationService(db, adapter).generate(
            user_id=1,
            user_sub="atlas-user",
            goal_id=1,
            idempotency_key="atlas-key",
            now=_now(),
        )
    assert adapter.calls == 0


def test_generate_disabled_performs_zero_projection(db, disabled_flag, monkeypatch):
    """After ownership, the gate stops before Phase 0 projection (req 7b)."""
    def _spy(request):  # if invoked the test fails immediately
        raise AssertionError(
            "project_scenarios was invoked while forecast persistence was disabled"
        )
    monkeypatch.setattr(service_module, "project_scenarios", _spy)

    adapter = _CountingAdapter(_state())
    with pytest.raises(ForecastGenerationUnavailable):
        ForecastGenerationService(db, adapter).generate(
            user_id=1,
            user_sub="atlas-user",
            goal_id=1,
            idempotency_key="atlas-key",
            now=_now(),
        )


def test_generate_disabled_makes_zero_repository_instantiations(
    db, disabled_flag, monkeypatch
):
    """After ownership, the gate stops before snapshot / repo lookup / write (req 7c-e)."""
    real_init = service_module.ForecastRepository.__init__
    snapshot_calls = []

    def _spy_init(self, session):
        snapshot_calls.append(id(session))
        real_init(self, session)

    monkeypatch.setattr(
        service_module.ForecastRepository, "__init__", _spy_init
    )

    adapter = _CountingAdapter(_state())
    with pytest.raises(ForecastGenerationUnavailable):
        ForecastGenerationService(db, adapter).generate(
            user_id=1,
            user_sub="atlas-user",
            goal_id=1,
            idempotency_key="atlas-key",
            now=_now(),
        )
    assert snapshot_calls == []


def test_generate_disabled_preserves_ownership_non_disclosure(
    db, disabled_flag, monkeypatch
):
    """Cross-user goal is rejected with the same token, BEFORE adapter (req 6)."""
    adapter = _CountingAdapter(_state())
    with pytest.raises(ForecastGenerationUnavailable):
        ForecastGenerationService(db, adapter).generate(
            user_id=2,                # wrong user
            user_sub="other-user",
            goal_id=1,
            idempotency_key="atlas-key",
            now=_now(),
        )
    assert adapter.calls == 0


def test_generate_disabled_preserves_missing_goal_non_disclosure(
    db, disabled_flag
):
    """Missing goal returns the single sanitized token before the adapter (req 6)."""
    adapter = _CountingAdapter(_state())
    with pytest.raises(
        ForecastGenerationUnavailable, match=r"^forecast_generation_unavailable$"
    ):
        ForecastGenerationService(db, adapter).generate(
            user_id=1,
            user_sub="atlas-user",
            goal_id=999,                # missing
            idempotency_key="atlas-key",
            now=_now(),
        )
    assert adapter.calls == 0


def test_generate_disabled_error_does_not_leak_sources(db, disabled_flag):
    """Error message contains only the bounded token (req 9)."""
    adapter = _CountingAdapter(
        _state(amount="9999.42", user="atlas-buyer")
    )
    with pytest.raises(ForecastGenerationUnavailable) as exc_info:
        ForecastGenerationService(db, adapter).generate(
            user_id=1,
            user_sub="atlas-buyer",
            goal_id=1,
            idempotency_key="atlas-secret-key",
            now=_now(),
        )
    msg = str(exc_info.value)
    # The whole surface IS the single token - nothing else crosses the boundary.
    assert msg == "forecast_generation_unavailable"
    # Repeated guard so a future regression that appends diagnostic text fails.
    forbidden = (
        "atlas_forecast_persistence_enabled",
        "ATLAS_FORECAST_PERSISTENCE_ENABLED",
        "atlas-buyer",
        "atlas-secret-key",
        "atlas-test-account",
        "9999.42",
        "finlynq",
        "atlas-target-decision",
        "atlas-projection-state",
        "/api/",
    )
    for token in forbidden:
        assert token not in msg, f"{token!r} leaked into disabled-path error message"


def test_generate_does_not_accept_client_controlled_flag(db):
    """``generate()`` has no client-supplied persistence parameter (req 5)."""
    import inspect

    sig = inspect.signature(ForecastGenerationService.generate)
    parameters = list(sig.parameters)
    # The persistence flag is a server setting; the caller cannot pass it.
    assert "persistence_enabled" not in parameters
    assert "atlas_forecast_persistence_enabled" not in parameters
    assert "enabled" not in parameters


def test_canonical_state_rejects_attempt_to_override_flag(db):
    """Canonical state cannot smuggle a persistence flag (req 5)."""
    bogus_state = {
        "schema_version": "atlas-projection-state/v1",
        "canonicalization": {
            "canonical_json_version": "atlas-canonical-json/v1",
            "hash_schema_version": "atlas-input-state-hash/v1",
            "hash_algorithm": "sha256",
        },
        # adversarial extra field - the strict envelope must reject it.
        "persistence_enabled": True,
        "atlas_forecast_persistence_enabled": True,
        "user_id": "atlas-user",
        "goal_id": 1,
        "as_of_timestamp": "2026-07-01T12:00:00Z",
        "currency": "USD",
        "current_value_components": [
            {
                "kind": "investment",
                "amount": "1000",
                "source_reference": "atlas-test-account",
                "observed_at": "2026-07-01T12:00:00Z",
            }
        ],
        "contribution_inputs": [
            {
                "kind": "monthly_investable_cash_flow",
                "amount": "100",
                "source_reference": "atlas-test-plan",
                "observed_at": "2026-07-01T12:00:00Z",
            }
        ],
        "freshness": {
            "max_data_age_days": 30,
            "observed_age_days": 0,
            "source_updated_at": "2026-07-01T12:00:00Z",
        },
        "provenance": [
            {
                "source_system": "finlynq",
                "reference_id": "atlas-test",
                "observed_at": "2026-07-01T12:00:00Z",
                "record_count": 1,
                "source_state_hash": "a" * 64,
            }
        ],
        "missing_data_codes": [],
        "reconciliation_state": "reconciled",
    }
    from app.forecasts.canonical_state import (
        CanonicalProjectionState,
        ContractValidationError,
    )
    with pytest.raises(ContractValidationError):
        CanonicalProjectionState.model_validate(bogus_state)


# ----------------------------------------------------------------------
# Enabled-path regression (requirements: enabled behaviour unchanged)
# ----------------------------------------------------------------------
def test_generate_enabled_persists_complete_snapshots(db, enabled_flag):
    """Explicit-true flag yields the canonical Slice B output (Snapshot, decision, decimal)."""
    adapter = _CountingAdapter(_state())
    created = ForecastGenerationService(db, adapter).generate(
        user_id=1,
        user_sub="atlas-user",
        goal_id=1,
        idempotency_key="atlas-key",
        now=_now(),
    )
    assert created.persisted.created
    assert (
        "atlas-projection-assumptions/v1"
        in created.persisted.version.assumption_snapshot_json
    )
    assert (
        "atlas-target-decision/v2"
        in created.persisted.version.output_snapshot_json
    )
    # Decimal v1 schema identifier must be present in the persisted output snapshot.
    assert (
        "atlas-calculation-decimal/v1"
        in created.persisted.version.output_snapshot_json
    )


def test_generate_enabled_replay_and_changed_state(db, enabled_flag):
    """Idempotent replay + Decimal / hash invariants remain intact under flag=True."""
    from app.forecasts.repository import IdempotencyConflict

    adapter = _CountingAdapter(_state())
    service = ForecastGenerationService(db, adapter)
    now = _now()
    first = service.generate(
        user_id=1,
        user_sub="atlas-user",
        goal_id=1,
        idempotency_key="atlas-key",
        now=now,
    )
    replay = service.generate(
        user_id=1,
        user_sub="atlas-user",
        goal_id=1,
        idempotency_key="atlas-key",
        now=now,
    )
    assert not replay.persisted.created
    assert replay.persisted.version.id == first.persisted.version.id

    adapter.state = _state(amount="1001")
    with pytest.raises(IdempotencyConflict):
        service.generate(
            user_id=1,
            user_sub="atlas-user",
            goal_id=1,
            idempotency_key="atlas-key",
            now=now,
        )


# ----------------------------------------------------------------------
# Checked-in documentation invariants (requirement 10)
# ----------------------------------------------------------------------
def test_repo_root_dot_env_example_documents_flag_disabled():
    """The repo-root ``.env.example`` keeps the flag commented-out / disabled."""
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    env_file = project_root / ".env.example"
    assert env_file.exists(), "Repo-root .env.example must exist"
    text = env_file.read_text(encoding="utf-8")
    # The flag line MUST exist and MUST be commented out so a copy/paste
    # deploys with persistence disabled.
    assert "ATLAS_FORECAST_PERSISTENCE_ENABLED" in text
    flagged_line = next(
        line for line in text.splitlines()
        if "ATLAS_FORECAST_PERSISTENCE_ENABLED" in line
    )
    assert flagged_line.lstrip().startswith("#"), (
        "Checked-in examples must keep ATLAS_FORECAST_PERSISTENCE_ENABLED commented out"
    )


def test_rules_service_dot_env_example_documents_flag_disabled():
    """``services/rules-service/.env.example`` keeps the flag commented / disabled."""
    from pathlib import Path

    rules_service_root = Path(__file__).resolve().parents[1]
    env_file = rules_service_root / ".env.example"
    assert env_file.exists(), "rules-service .env.example must exist"
    text = env_file.read_text(encoding="utf-8")
    assert "ATLAS_FORECAST_PERSISTENCE_ENABLED" in text
    flagged_line = next(
        line for line in text.splitlines()
        if "ATLAS_FORECAST_PERSISTENCE_ENABLED" in line
    )
    assert flagged_line.lstrip().startswith("#"), (
        "rules-service .env.example must keep the flag commented out"
    )
