import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from datetime import UTC, datetime, timedelta

from app.investments.committee_contracts import CommitteeContext, EvidenceCategory, EvidenceItem, EvidencePacket
from app.investments.committee_adapters import FixtureCommitteeModel
from app.investments.committee_orchestrator import run_committee
from app.investments.contracts import EvidenceKind, EvidenceReference
from app.investments.recommendation_contracts import PositionState, RecommendationType, TimeHorizon
from app.investments.recommendation_gates import build_recommendation
from app.investments.persistence_service import InvestmentPersistenceService

from app.auth import issue_token
from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.routes.shared import get_or_create_local_user


@pytest.fixture(autouse=True)
def _enable_persistence():
    settings.atlas_investment_persistence_enabled = True


def _client(token: str | None = None) -> TestClient:
    from app.main import app
    settings.atlas_investment_persistence_enabled = True
    client = TestClient(app)
    if token:
        client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_investment_routes_require_authentication(client_no_auth):
    response = client_no_auth.get('/api/v1/investments/recommendations')
    assert response.status_code == 401


def test_investment_routes_are_owner_scoped_and_do_not_enumerate(client, db_session):
    get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    response = client.get('/api/v1/investments/recommendations/investment-recommendation:does-not-exist')
    assert response.status_code == 404
    assert response.headers.get('X-Error-Code') == 'investment_recommendation_not_found'
    assert 'payload_json' not in response.text


def test_investment_decision_requires_both_preconditions(client, db_session):
    get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    response = client.post(
        '/api/v1/investments/recommendations/investment-recommendation:missing/decisions',
        json={'decision_type': 'accept'},
    )
    assert response.status_code == 428
    assert response.headers.get('X-Error-Code') == 'precondition_required'


def test_investment_decision_rejects_malformed_command(client, db_session):
    get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    response = client.post(
        '/api/v1/investments/recommendations/investment-recommendation:missing/decisions',
        json={'decision_type': 'BUY', 'owner_id': 999},
        headers={'If-Match': 'x', 'Idempotency-Key': 'same-key'},
    )
    assert response.status_code == 422


def _seed_investment(db_session, owner_id: int = 1, *, status="active", evidence_as_of=None):
    now = datetime(2026, 8, 31, 12, tzinfo=UTC)
    evidence_as_of = evidence_as_of or now - timedelta(days=1)
    security = f"sec:http:{owner_id}"
    reference = EvidenceReference(evidence_id=f"market:http:{owner_id}", kind=EvidenceKind.SOURCE, source="fixture", content_hash="a" * 64, as_of=evidence_as_of, retrieved_at=now)
    item = EvidenceItem(evidence_id=f"market:http:{owner_id}", category=EvidenceCategory.MARKET, subject_security_id=security, owner_id=owner_id, reference=reference, numeric_value="100")
    packet = EvidencePacket.with_hash(packet_id=f"packet:http:{owner_id}", owner_id=owner_id, subject_security_id=security, analysis_as_of=now - timedelta(days=1), items=(item,))
    context = CommitteeContext.with_hash(run_id=f"run:http:{owner_id}", owner_id=owner_id, subject_security_id=security, analysis_as_of=packet.analysis_as_of, evidence_packet=packet, input_hashes=(packet.packet_hash,), portfolio_snapshot_hash="b" * 64)
    finding_payload = {"claim": "Evidence supports the view.", "claim_class": "interpretation", "direction": "supports", "evidence_refs": (item.evidence_id,)}
    responses = {role: dict(finding_payload) for role in ("fundamental", "technical", "macro", "quant", "portfolio", "risk", "bull", "bear")} | {"chair": {"committee_view": "constructive", "thesis": "The evidence supports the thesis.", "supporting_evidence": (item.evidence_id,), "contradicting_evidence": (), "key_risks": (), "invalidation_conditions": ("Evidence changes.",)}}
    run = run_committee(context, FixtureCommitteeModel(responses), created_at=now)
    assert run.chair_finding is not None
    recommendation_result = build_recommendation(owner_id=owner_id, committee_finding=run.chair_finding, evidence_packet=packet, portfolio_snapshot_hash="b" * 64, position_state=PositionState.NOT_HELD, requested_type=RecommendationType.BUY, time_horizon=TimeHorizon.MEDIUM_TERM, recommendation_as_of=now)
    recommendation = recommendation_result.recommendation
    assert recommendation is not None, recommendation_result.failure_reason
    if status != "active":
        recommendation = recommendation.model_copy(update={"status": type(recommendation.status)(status)})
    service = InvestmentPersistenceService(db_session)
    service.persist_evidence_packet(packet)
    run = run.model_copy(update={"context_hash": packet.packet_hash, "run_hash": run.run_hash})
    service.persist_committee_run(run, evidence_packet=packet)
    service.persist_committee_finding(run.chair_finding, run=run, evidence_packet=packet)
    service.persist_recommendation(recommendation, committee_finding=run.chair_finding, run=run, evidence_packet=packet)
    db_session.commit()
    return recommendation


def test_http_owner_isolation_for_recommendation_and_evidence(client, db_session):
    owner_a = get_or_create_local_user(db_session, "alex")
    owner_b = get_or_create_local_user(db_session, "owner-b")
    db_session.commit()
    rec = _seed_investment(db_session, owner_b.id)
    client.get("/api/v1/investments/recommendations")
    response = client.get(f"/api/v1/investments/recommendations/{rec.recommendation_id}")
    assert response.status_code == 404
    assert client.get(f"/api/v1/investments/recommendations/{rec.recommendation_id}/evidence").status_code == 404


def test_http_decision_replays_and_conflicts_deterministically(client, db_session):
    owner = get_or_create_local_user(db_session, "alex")
    db_session.commit()
    rec = _seed_investment(db_session, owner.id)
    headers = {"If-Match": rec.recommendation_hash, "Idempotency-Key": "http-replay"}
    first = client.post(f"/api/v1/investments/recommendations/{rec.recommendation_id}/decisions", headers=headers, json={"decision_type": "accept"})
    second = client.post(f"/api/v1/investments/recommendations/{rec.recommendation_id}/decisions", headers=headers, json={"decision_type": "accept"})
    conflict = client.post(f"/api/v1/investments/recommendations/{rec.recommendation_id}/decisions", headers=headers, json={"decision_type": "reject"})
    assert first.status_code == 201
    assert second.status_code == 201 and second.json()["replayed"] is True
    assert second.json()["decision"]["decision_id"] == first.json()["decision"]["decision_id"]
    assert conflict.status_code == 409


def test_http_stale_hash_and_lifecycle_are_rejected(client, db_session):
    owner = get_or_create_local_user(db_session, "alex")
    db_session.commit()
    rec = _seed_investment(db_session, owner.id)
    from app.config import settings
    settings.local_user = "alex"
    path = f"/api/v1/investments/recommendations/{rec.recommendation_id}/decisions"
    assert client.post(path, headers={"If-Match": "0" * 64, "Idempotency-Key": "stale"}, json={"decision_type": "accept"}).status_code == 409
    expired_owner = get_or_create_local_user(db_session, "expired-owner")
    db_session.commit()
    expired = _seed_investment(db_session, expired_owner.id, status="expired")
    expired_client = _client()
    expired_client.headers["Authorization"] = f"Bearer {issue_token()}"
    from app.config import settings
    settings.local_user = "expired-owner"
    expired_client.headers["Authorization"] = f"Bearer {issue_token(username='expired-owner')}"
    assert expired_client.post(f"/api/v1/investments/recommendations/{expired.recommendation_id}/decisions", headers={"If-Match": expired.recommendation_hash, "Idempotency-Key": "expired"}, json={"decision_type": "accept"}).status_code == 409


def test_http_decisions_are_typed_and_owner_scoped(client, db_session):
    from app.config import settings
    settings.local_user = "alex"
    owner = get_or_create_local_user(db_session, "alex")
    db_session.commit()
    rec = _seed_investment(db_session, owner.id)
    client.headers["Cookie"] = f"fc_session={issue_token(username='alex')}"
    assert client.get(f"/api/v1/investments/recommendations/{rec.recommendation_id}/decisions").status_code == 200


def test_wrong_owner_subject_is_not_resolved_to_another_user(client, db_session):
    owner = get_or_create_local_user(db_session, 'alex')
    db_session.commit()
    assert owner is not None
    other = _client(issue_token(username='not-alex'))
    response = other.get('/api/v1/investments/recommendations')
    assert response.status_code == 401
