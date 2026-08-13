"""Boundary tests for the default-off Phase 4 decision-history routes."""
from __future__ import annotations

from tests.test_outcome_evaluation_migration import _plant_world


def _seed(db_session):
    world = _plant_world(db_session, local_user_sub="alex", email="alex@local")
    db_session.commit()
    return world


def _payload(world, **extra):
    value = {"recommendation_id": world["recommendation"], "decision_journal_entry_id": world["decision"], "alternatives": ["do_nothing", "accept"], "rationale": "I considered preserving the current plan."}
    value.update(extra)
    return value


def test_history_default_off_is_safe(client, db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "atlas_decision_history_api_enabled", False)
    assert client.get("/api/v1/goals/1/decision-history").status_code == 503


def test_history_strict_write_replay_conflict_and_safe_read(client, db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "atlas_decision_history_api_enabled", True)
    world = _seed(db_session)
    url = f"/api/v1/goals/{world['goal']}/decision-history"
    assert client.post(url, json={**_payload(world), "unknown": "no"}, headers={"Idempotency-Key": "history-route-1"}).status_code == 422
    first = client.post(url, json=_payload(world), headers={"Idempotency-Key": "history-route-1"})
    assert first.status_code == 201, first.text
    assert client.post(url, json=_payload(world), headers={"Idempotency-Key": "history-route-1"}).json()["replayed"] is True
    assert client.post(url, json=_payload(world, rationale="different"), headers={"Idempotency-Key": "history-route-1"}).status_code == 409
    response = client.get(url)
    assert response.status_code == 200
    body = response.json(); serialized = response.text
    assert body["history"][0]["outcome_lifecycles"] == []
    for forbidden in ("idempotency", "correlation", "evidence", "result_json", "explanation"):
        assert forbidden not in serialized


def test_history_owner_missing_and_cross_user_share_404(client, db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "atlas_decision_history_api_enabled", True)
    world = _seed(db_session)
    missing = client.get("/api/v1/goals/999999/decision-history")
    # A real owned goal paired with another user's linked records is equally
    # sanitized at the write boundary.
    cross = client.post(f"/api/v1/goals/{world['goal']}/decision-history", json=_payload(world, recommendation_id="00000000-0000-4000-8000-000000000099"), headers={"Idempotency-Key": "history-cross"})
    assert (missing.status_code, missing.json()) == (404, {"code": "decision_history_not_found", "message": "Decision history not found."})
    assert (cross.status_code, cross.json()) == (404, {"code": "decision_history_not_found", "message": "Decision history not found."})
