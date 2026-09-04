from datetime import UTC, datetime


def test_scout_research_requires_authentication(client_no_auth):
    response = client_no_auth.post(
        "/api/v1/investments/scout/research",
        json={"security_id": "sec:test", "question": "What changed?"},
    )
    assert response.status_code == 401


def test_scout_history_requires_authentication(client_no_auth):
    response = client_no_auth.get("/api/v1/investments/scout/runs")
    assert response.status_code == 401


def test_scout_research_rejects_client_sources_and_ambiguous_selectors(client):
    response = client.post(
        "/api/v1/investments/scout/research",
        json={
            "security_id": "sec:test",
            "recommendation_id": "investment-recommendation:test",
            "question": "What changed?",
            "source_url": "https://attacker.test",
        },
    )
    assert response.status_code == 422


def test_scout_research_is_default_off_and_does_not_disclose_provider_state(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "atlas_investment_scout_external_provider_enabled", False)
    response = client.post(
        "/api/v1/investments/scout/research",
        json={"security_id": "sec:test", "question": "What changed?"},
    )
    assert response.status_code == 503
    assert response.headers["X-Error-Code"] == "investment_scout_unavailable"
    assert "Finnhub" not in response.text
    assert "secret" not in response.text.lower()


def test_scout_run_lookup_is_owner_scoped_and_unknown_is_non_enumerating(client, db_session):
    from app.investments.scout import (
        ScoutResearchResult,
        ScoutSecurityProjection,
        ScoutState,
        persist_scout_result,
    )
    from app.investments.securities import InstrumentType, SecurityIdentity, SecurityState
    from app.models import InvestmentScoutRun, User
    from app.routes.shared import get_or_create_local_user

    now = datetime(2026, 9, 3, 12, tzinfo=UTC)
    identity = SecurityIdentity(
        security_id="sec:test",
        state=SecurityState.RESOLVED,
        instrument_type=InstrumentType.EQUITY,
        symbol="AAPL",
        currency="USD",
        as_of=now,
    )

    def result_for(owner_id: int, question: str = "What changed?"):
        return ScoutResearchResult(
            run_id="scout-run:" + "0" * 32,
            owner_id=owner_id,
            question=question,
            security=ScoutSecurityProjection(security=identity, symbol="AAPL"),
            state=ScoutState.UNAVAILABLE,
            requested_at=now,
            as_of=now,
            as_known_at=now,
            limitations=("No sources found.",),
            result_hash="0" * 64,
        ).with_hash()

    local = get_or_create_local_user(db_session, "alex")
    other = User(local_user_sub="scout-other", email="scout-other@test.local", hashed_password="x")
    db_session.add(other)
    db_session.commit()
    local_result = result_for(local.id)
    other_result = result_for(other.id, question="Other owner's context")
    persist_scout_result(db_session, local_result)
    persist_scout_result(db_session, other_result)

    from app.config import settings
    settings.atlas_investment_scout_external_provider_enabled = True
    summaries = client.get("/api/v1/investments/scout/runs")
    same_owner = client.get(f"/api/v1/investments/scout/runs/{local_result.run_id}")
    cross_owner = client.get(f"/api/v1/investments/scout/runs/{other_result.run_id}")
    missing = client.get("/api/v1/investments/scout/runs/scout-run:" + "c" * 32)

    assert summaries.status_code == 200
    assert summaries.json()[0]["run_id"] == local_result.run_id
    assert "owner_id" not in summaries.text
    assert same_owner.status_code == 200
    assert "owner_id" not in same_owner.json()
    assert cross_owner.status_code == missing.status_code == 404
    assert cross_owner.json() == missing.json()
    assert db_session.query(InvestmentScoutRun).count() == 2
