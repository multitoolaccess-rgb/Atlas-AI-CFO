"""Local-profile configuration coverage for Finlynq."""
from app.config import Settings


def test_default_local_profile_is_loopback_and_uses_atlas_ports(monkeypatch):
    for name in ("API_HOST", "API_PORT", "ATLAS_UI_PORT", "CORS_ALLOW_ORIGINS"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8889
    assert "http://localhost:3333" in settings.development_cors_origins()
    assert "http://127.0.0.1:3333" in settings.development_cors_origins()
    assert "http://localhost:3000" in settings.development_cors_origins()


def test_cors_uses_configured_atlas_ui_port_and_optional_origins(monkeypatch):
    monkeypatch.setenv("ATLAS_UI_PORT", "4333")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:4555")

    origins = Settings(_env_file=None).development_cors_origins()

    assert "http://localhost:4333" in origins
    assert "http://127.0.0.1:4333" in origins
    assert "http://localhost:4555" in origins
