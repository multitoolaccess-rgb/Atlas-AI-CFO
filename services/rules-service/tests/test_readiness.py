"""Focused tests for the sanitized authenticated readiness contract."""
from __future__ import annotations


def _ready_migrations(monkeypatch):
    monkeypatch.setattr("app.readiness._migration_snapshot", lambda _db: ("synthetic-head", ("synthetic-head",)))


def test_readiness_requires_authentication(client_no_auth, monkeypatch):
    _ready_migrations(monkeypatch)
    response = client_no_auth.get("/api/system/readiness")
    assert response.status_code == 401


def test_readiness_is_sanitized_server_owned_and_read_only(client, db_session, monkeypatch):
    _ready_migrations(monkeypatch)
    before = db_session.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM users")).scalar_one()
    response = client.get("/api/system/readiness")
    after = db_session.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM users")).scalar_one()

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "atlas-readiness/v1"
    assert body["overall_state"] in {"configuration_failure", "ready_with_blocked_optional_capabilities", "ready"}
    assert {check["component"] for check in body["checks"]} == {
        "runtime", "storage", "financial_authority", "forecasts", "decision_history",
        "market_intelligence", "scenario_lab", "privacy_safety",
    }
    assert before == after
    serialized = response.text
    for forbidden in ("dev-secret-change-in-production", "balance", "transaction", "holding", "DATABASE_URL"):
        assert forbidden not in serialized
    assert all(isinstance(value, bool) for value in body["feature_flags"].values())
    assert all(isinstance(value, bool) for value in body["credentials"].values())
    assert body["feature_flags"]["atlas_scenario_lab_enabled"] is False


def test_readiness_fails_closed_when_currency_evidence_is_unavailable(client, db_session, make_account, monkeypatch):
    from app.models import Account

    _ready_migrations(monkeypatch)
    account = make_account(account_name="Synthetic USD account")
    db_session.add(account)
    db_session.commit()

    response = client.get("/api/system/readiness")
    assert response.status_code == 200
    body = response.json()
    financial = next(item for item in body["checks"] if item["component"] == "financial_authority")
    assert financial["state"] == "blocked"
    assert financial["reason_code"] == "currency_evidence_missing"
    assert body["overall_state"] == "configuration_failure"
    assert not any("current_balance" in key for key in response.json())
    assert db_session.query(Account).count() == 1


def test_readiness_reports_ready_currency_without_enabling_flags(client, db_session, make_account, monkeypatch):
    from datetime import datetime, timezone

    _ready_migrations(monkeypatch)
    account = make_account(account_name="Synthetic USD account")
    account.currency_code = "USD"
    account.currency_source = "user_confirmed"
    account.currency_observed_at = datetime.now(timezone.utc)
    account.currency_source_reference = "synthetic-acceptance-1"
    db_session.add(account)
    db_session.commit()

    response = client.get("/api/system/readiness")
    body = response.json()
    financial = next(item for item in body["checks"] if item["component"] == "financial_authority")
    forecasts = next(item for item in body["checks"] if item["component"] == "forecasts")
    assert financial["state"] == "ready"
    assert forecasts["state"] == "disabled"
    assert body["feature_flags"]["atlas_forecast_persistence_enabled"] is True
    assert body["feature_flags"]["atlas_forecast_read_api_enabled"] is False


def test_readiness_reports_migration_mismatch_without_mutating(client, monkeypatch):
    monkeypatch.setattr("app.readiness._migration_snapshot", lambda _db: ("old-revision", ("new-revision",)))
    response = client.get("/api/system/readiness")
    assert response.status_code == 200
    storage = next(item for item in response.json()["checks"] if item["component"] == "storage")
    assert storage["state"] == "blocked"
    assert storage["reason_code"] == "migration_state_unavailable"
