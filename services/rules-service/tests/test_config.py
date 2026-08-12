"""Hermetic tests for ``app.config.Settings``.

Minimal coverage of three contracts the lifted module must obey:

- Defaults are usable without any env (developer drop-in). The ``_env_file=None``
  arg disables the ``.env`` file so tests never depend on host state.
- Environment overrides win over defaults — her test of merge-plan §10 surface.
- ``case_sensitive=False`` (from ``pydantic_settings``) means env keys in any
  capitalisation map to the same field.
"""
import pytest

from app.config import Settings


def test_default_settings_when_no_env(monkeypatch):
    """Wipe known env keys; constructed ``Settings()`` returns documented defaults."""
    for k in (
        "DATABASE_URL",
        "JWT_SECRET",
        "ENVIRONMENT",
        "APP_NAME",
        "APP_VERSION",
        "LOCAL_USER",
        "JWT_ALGORITHM",
        "JWT_EXPIRATION_HOURS",
        "API_HOST",
        "API_PORT",
        "PLAID_CLIENT_ID",
        "PLAID_SECRET",
        "PLAID_ENV",
    ):
        monkeypatch.delenv(k, raising=False)

    s = Settings(_env_file=None)

    assert s.database_url == "postgresql://wealthiq:wealthiq@localhost:5432/wealthiq"
    assert s.environment == "development"
    assert s.app_name == "Finance Copilot"
    assert s.app_version == "0.1.0"
    assert s.local_user == "alex"            # §10 decision 4
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_expiration_hours == 24


def test_env_overrides_win(monkeypatch):
    """``DATABASE_URL`` + ``LOCAL_USER`` env overrides are honoured."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@h:5433/d")
    monkeypatch.setenv("LOCAL_USER", "casey")
    monkeypatch.setenv("JWT_SECRET", "rotated")

    s = Settings(_env_file=None)

    assert s.database_url == "postgresql+psycopg2://u:p@h:5433/d"
    assert s.local_user == "casey"
    assert s.jwt_secret == "rotated"


def test_case_insensitive_env(monkeypatch):
    """Mixed-case env keys map to the same field (case_sensitive=False)."""
    monkeypatch.setenv("Database_URL", "from-caps")
    monkeypatch.setenv("jwt_SECRET", "secret-from-caps")

    s = Settings(_env_file=None)

    assert s.database_url == "from-caps"
    assert s.jwt_secret == "secret-from-caps"


def test_module_level_settings_is_a_settings_instance():
    """``from app.config import settings`` is the singleton used at runtime."""
    from app.config import settings

    assert isinstance(settings, Settings)
    assert settings.app_name == "Finance Copilot"


def test_default_env_file_is_anchored_to_rules_service_directory():
    """Runtime config must not depend on whether uvicorn was launched from repo root."""
    from pathlib import Path

    from app.config import RULES_SERVICE_ENV_FILE

    expected = Path(__file__).resolve().parents[1] / ".env"
    assert RULES_SERVICE_ENV_FILE.resolve() == expected.resolve()


def test_production_environment_refuses_dev_default_jwt_secret(monkeypatch):
    """Hardening raised by Phase 2 code-review: a production deploy with the
    dev-default ``jwt_secret`` must raise, not silently ship a forge-any-token cookie."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Strip JWT_SECRET so the model's dev-default ('dev-secret-change-in-production')
    # kicks in — that's the value the hardening validator must reject.
    monkeypatch.delenv("JWT_SECRET", raising=False)
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "JWT_SECRET" in str(exc.value)


def test_production_environment_accepts_explicit_jwt_secret(monkeypatch):
    """Production deploy WITH an explicit ``JWT_SECRET`` succeeds."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "from-explicit-env-override")
    s = Settings(_env_file=None)
    assert s.environment == "production"
    assert s.jwt_secret == "from-explicit-env-override"

# =============================================================================
# Phase 1 Slice E.1 — atlas_forecast_read_api_enabled default-off flag
# =============================================================================


def test_read_api_flag_default_is_off(monkeypatch: object) -> None:
    """When ``ATLAS_FORECAST_READ_API_ENABLED`` is unset, the flag is ``False``."""
    monkeypatch.delenv(  # type: ignore[attr-defined]
        "ATLAS_FORECAST_READ_API_ENABLED", raising=False
    )
    Settings = __import__("app.config", fromlist=["Settings"]).Settings
    settings = Settings()
    assert settings.atlas_forecast_read_api_enabled is False


def test_read_api_flag_explicit_false_remains_off(monkeypatch: object) -> None:
    """When ``ATLAS_FORECAST_READ_API_ENABLED=false``, the flag is ``False``."""
    monkeypatch.setenv("ATLAS_FORECAST_READ_API_ENABLED", "false")  # type: ignore[attr-defined]
    Settings = __import__("app.config", fromlist=["Settings"]).Settings
    settings = Settings()
    assert settings.atlas_forecast_read_api_enabled is False


def test_read_api_flag_explicit_true_enables(monkeypatch: object) -> None:
    """When ``ATLAS_FORECAST_READ_API_ENABLED=true``, the flag is ``True``."""
    monkeypatch.setenv("ATLAS_FORECAST_READ_API_ENABLED", "true")  # type: ignore[attr-defined]
    Settings = __import__("app.config", fromlist=["Settings"]).Settings
    settings = Settings()
    assert settings.atlas_forecast_read_api_enabled is True


def test_read_api_flag_invalid_value_fails_closed(monkeypatch: object) -> None:
    """An invalid or ambiguous env value MUST raise a validation error (fail-closed)."""
    from pydantic import ValidationError
    monkeypatch.setenv("ATLAS_FORECAST_READ_API_ENABLED", "maybe")  # type: ignore[attr-defined]
    Settings = __import__("app.config", fromlist=["Settings"]).Settings
    try:
        Settings()
    except ValidationError as exc:
        assert "atlas_forecast_read_api_enabled" in str(exc).lower()
        return
    raise AssertionError(
        "expected ValidationError on ambiguous ATLAS_FORECAST_READ_API_ENABLED"
    )


def test_phase5_market_brief_flags_default_off(monkeypatch: object) -> None:
    """Phase 5 external capabilities require an explicit server env setting."""
    names = (
        "ATLAS_MARKET_BRIEF_GENERATION_ENABLED",
        "ATLAS_MARKET_BRIEF_READ_API_ENABLED",
        "ATLAS_MARKET_BRIEF_EXTERNAL_PROVIDER_ENABLED",
        "ATLAS_MARKET_BRIEF_EMAIL_DELIVERY_ENABLED",
        "ATLAS_MARKET_BRIEF_SCHEDULER_ENABLED",
        "ATLAS_MARKET_BRIEF_LOCAL_SUMMARIZATION_ENABLED",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)  # type: ignore[attr-defined]

    settings = Settings(_env_file=None)
    assert all((
        settings.atlas_market_brief_generation_enabled is False,
        settings.atlas_market_brief_read_api_enabled is False,
        settings.atlas_market_brief_external_provider_enabled is False,
        settings.atlas_market_brief_email_delivery_enabled is False,
        settings.atlas_market_brief_scheduler_enabled is False,
        settings.atlas_market_brief_local_summarization_enabled is False,
    ))
