"""Atlas lifecycle CORS and migration-safety contracts."""

from unittest.mock import Mock


def test_cors_allows_only_explicit_local_atlas_ui_origins() -> None:
    from app.main import ALLOWED_CORS_ORIGINS

    assert "http://localhost:3333" in ALLOWED_CORS_ORIGINS
    assert "http://127.0.0.1:3333" in ALLOWED_CORS_ORIGINS
    assert all(origin.startswith(("http://localhost:", "http://127.0.0.1:")) for origin in ALLOWED_CORS_ORIGINS)


def test_automatic_migration_is_disabled_without_explicit_opt_in(monkeypatch) -> None:
    from app import main

    monkeypatch.delenv("ATLAS_AUTO_MIGRATE", raising=False)
    log_info = Mock()
    monkeypatch.setattr(main.LOG, "info", log_info)
    main._run_alembic_upgrade_on_boot()

    log_info.assert_called_once_with(
        "Automatic migrations are disabled; run Alembic explicitly when approved."
    )
