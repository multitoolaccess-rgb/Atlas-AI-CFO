"""Atlas lifecycle CORS and migration-safety contracts."""

import logging


def test_cors_allows_only_explicit_local_atlas_ui_origins() -> None:
    from app.main import ALLOWED_CORS_ORIGINS

    assert "http://localhost:3333" in ALLOWED_CORS_ORIGINS
    assert "http://127.0.0.1:3333" in ALLOWED_CORS_ORIGINS
    assert all(origin.startswith(("http://localhost:", "http://127.0.0.1:")) for origin in ALLOWED_CORS_ORIGINS)


def test_automatic_migration_is_disabled_without_explicit_opt_in(monkeypatch, caplog) -> None:
    from app.main import _run_alembic_upgrade_on_boot

    monkeypatch.delenv("ATLAS_AUTO_MIGRATE", raising=False)
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    _run_alembic_upgrade_on_boot()

    assert "Automatic migrations are disabled" in caplog.text
