"""INV-12 evaluation read API: auth, owner isolation, typed envelopes.

The API is read-only by construction: list/detail/replay take no analytical
JSON body, so there is no client-injection surface; owner scope always comes
from auth. Assertions cover 401 unauthenticated, non-enumerating 404 with
typed ``X-Error-Code`` headers, cross-owner isolation, invalid-horizon 422,
and no ORM/payload leakage in responses.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.investments.committee_adapters import FixtureCommitteeModel
from app.investments.committee_contracts import CommitteeContext, EvidenceCategory, EvidenceItem, EvidencePacket
from app.investments.committee_orchestrator import run_committee
from app.investments.contracts import DataState, EvidenceKind, EvidenceReference
from app.investments.evaluation_contracts import StoredMarketObservation
from app.investments.evaluation_service import EvaluationService
from app.investments.market_observations import AdjustmentBasis, ObservationQuality
from app.investments.persistence_service import InvestmentPersistenceService
from app.investments.portfolio_intelligence import build_portfolio_snapshot
from app.investments.recommendation_contracts import PositionState, RecommendationType, TimeHorizon
from app.investments.recommendation_gates import build_recommendation
from app.routes.shared import get_or_create_local_user


@pytest.fixture(autouse=True)
def _enable_persistence():
    settings.atlas_investment_persistence_enabled = True
    settings.atlas_investment_read_enabled = True


def _client_for(sub: str) -> TestClient:
    """TestClient authenticated as ``sub`` under single-user dev auth.

    ``require_user`` accepts a JWT whose ``sub`` equals
    ``settings.local_user``, so the helper switches the local-user contract
    for the duration of the requests and the caller restores it afterwards.
    """
    from app.auth import issue_token
    from app.main import app

    settings.local_user = sub
    client = TestClient(app)
    client.headers["Cookie"] = f"fc_session={issue_token()}"
    return client


def _seed_artifacts(db_session, owner_id: int) -> tuple[str, str]:
    """Seed recommendation + snapshot + observations; return (rec_id, eval_id)."""
    security = f"atlas-security:{owner_id}:acme"
    as_of = datetime(2026, 6, 1, 12, tzinfo=UTC)
    evaluation_as_of = as_of + timedelta(days=30)
    snapshot = build_portfolio_snapshot(owner_id=owner_id, accounts=[], holdings=[], as_of=as_of)
    portfolio_snapshot_hash = snapshot.snapshot_hash

    now = as_of
    evidence_as_of = now - timedelta(days=1)
    reference = EvidenceReference(evidence_id=f"market:http-inv12:{owner_id}", kind=EvidenceKind.SOURCE, source="fixture", content_hash="a" * 64, as_of=evidence_as_of, retrieved_at=now)
    item = EvidenceItem(evidence_id=f"market:http-inv12:{owner_id}", category=EvidenceCategory.MARKET, subject_security_id=security, owner_id=owner_id, reference=reference, numeric_value="100")
    packet = EvidencePacket.with_hash(packet_id=f"packet:http-inv12:{owner_id}", owner_id=owner_id, subject_security_id=security, analysis_as_of=evidence_as_of, items=(item,))
    context = CommitteeContext.with_hash(run_id=f"run:http-inv12:{owner_id}", owner_id=owner_id, subject_security_id=security, analysis_as_of=packet.analysis_as_of, evidence_packet=packet, input_hashes=(packet.packet_hash,), portfolio_snapshot_hash=portfolio_snapshot_hash)
    finding_payload = {"claim": "Evidence supports the view.", "claim_class": "interpretation", "direction": "supports", "evidence_refs": (item.evidence_id,)}
    responses = {role: dict(finding_payload) for role in ("fundamental", "technical", "macro", "quant", "portfolio", "risk", "bull", "bear")} | {"chair": {"committee_view": "constructive", "thesis": "The evidence supports the thesis.", "supporting_evidence": (item.evidence_id,), "contradicting_evidence": (), "key_risks": (), "invalidation_conditions": ("Evidence changes.",)}}
    committee_run = run_committee(context, FixtureCommitteeModel(responses), created_at=now)
    assert committee_run.chair_finding is not None
    recommendation_result = build_recommendation(
        owner_id=owner_id,
        committee_finding=committee_run.chair_finding,
        evidence_packet=packet,
        portfolio_snapshot_hash=portfolio_snapshot_hash,
        position_state=PositionState.NOT_HELD,
        requested_type=RecommendationType.BUY,
        time_horizon=TimeHorizon.MEDIUM_TERM,
        recommendation_as_of=now,
    )
    recommendation = recommendation_result.recommendation
    assert recommendation is not None, recommendation_result.failure_reason

    service = InvestmentPersistenceService(db_session)
    service.persist_evidence_packet(packet)
    committee_run = committee_run.model_copy(update={"context_hash": packet.packet_hash, "run_hash": committee_run.run_hash})
    service.persist_committee_run(committee_run, evidence_packet=packet)
    service.persist_committee_finding(committee_run.chair_finding, run=committee_run, evidence_packet=packet)
    service.persist_recommendation(recommendation, committee_finding=committee_run.chair_finding, run=committee_run, evidence_packet=packet)

    evaluations = EvaluationService(db_session)
    evaluations.store_portfolio_snapshot(snapshot)
    for price, observed_at, as_known_at in (
        ("100", as_of - timedelta(hours=2), as_of - timedelta(hours=2)),
        ("110", evaluation_as_of - timedelta(hours=1), evaluation_as_of - timedelta(hours=1)),
    ):
        evaluations.store_observation(StoredMarketObservation.with_hash(
            security_id=security,
            observed_value=price,
            currency="USD",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            observed_at=observed_at,
            as_known_at=as_known_at,
            retrieved_at=as_known_at,
            source="fixture-provider",
            state=DataState.OBSERVED,
            quality=ObservationQuality.VALIDATED,
            freshness=DataState.OBSERVED,
        ))
    run = evaluations.evaluate(owner_id=owner_id, recommendation_id=recommendation.recommendation_id, evaluation_as_of=evaluation_as_of, horizon="1M")
    assert run.created is True
    db_session.commit()
    return recommendation.recommendation_id, run.artifact.evaluation_id


def test_evaluation_routes_require_authentication(client_no_auth):
    assert client_no_auth.get("/api/v1/investments/evaluations").status_code == 401
    assert client_no_auth.get("/api/v1/investments/evaluations/investment-evaluation:missing").status_code == 401
    assert client_no_auth.get("/api/v1/investments/evaluations/investment-evaluation:missing/replay").status_code == 401


def test_evaluation_unknown_ids_are_non_enumerating(client, db_session):
    get_or_create_local_user(db_session, "alex")
    db_session.commit()
    response = client.get("/api/v1/investments/evaluations/investment-evaluation:" + "0" * 64)
    assert response.status_code == 404
    assert response.headers.get("X-Error-Code") == "investment_evaluation_not_found"
    assert "payload_json" not in response.text
    replay = client.get("/api/v1/investments/evaluations/investment-evaluation:" + "0" * 64 + "/replay")
    assert replay.status_code == 404
    assert replay.headers.get("X-Error-Code") == "investment_evaluation_not_found"


def test_evaluation_list_and_detail_are_typed_and_owner_scoped(client, db_session):
    owner = get_or_create_local_user(db_session, "alex")
    get_or_create_local_user(db_session, "owner-b")
    db_session.commit()
    recommendation_id, evaluation_id = _seed_artifacts(db_session, owner.id)

    listed = client.get(f"/api/v1/investments/evaluations?recommendation_id={recommendation_id}")
    assert listed.status_code == 200
    body = listed.json()
    assert body["schema_version"] == "atlas-investment-evaluation-list/v1"
    assert [item["evaluation_id"] for item in body["items"]] == [evaluation_id]
    assert "owner_id" not in body["items"][0]
    assert "payload_json" not in listed.text

    detail = client.get(f"/api/v1/investments/evaluations/{evaluation_id}")
    assert detail.status_code == 200
    artifact = detail.json()["evaluation"]
    assert detail.json()["schema_version"] == "atlas-investment-evaluation/v1"
    assert artifact["evaluation_id"] == evaluation_id
    assert artifact["evaluation_state"] == "evaluated"
    assert artifact["result_state"] == "available"
    assert artifact["recommendation_id"] == recommendation_id
    assert "owner_id" not in artifact
    assert "payload_json" not in detail.text

    # Foreign-owner reads: non-enumerating 404 / empty lists. Restore the
    # single-user auth contract afterwards so sibling tests keep running as
    # the default local user.
    try:
        other = _client_for("owner-b")
        assert other.get(f"/api/v1/investments/evaluations/{evaluation_id}").status_code == 404
        assert other.get(f"/api/v1/investments/evaluations/{evaluation_id}/replay").status_code == 404
        assert other.get(f"/api/v1/investments/evaluations?recommendation_id={recommendation_id}").json()["items"] == []
    finally:
        settings.local_user = "alex"


def test_evaluation_replay_returns_match(client, db_session):
    owner = get_or_create_local_user(db_session, "alex")
    db_session.commit()
    _, evaluation_id = _seed_artifacts(db_session, owner.id)
    response = client.get(f"/api/v1/investments/evaluations/{evaluation_id}/replay")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "atlas-investment-evaluation-replay/v1"
    assert body["evaluation_id"] == evaluation_id
    assert body["replay_state"] == "match"
    assert body["verified"] is True
    assert len(body["evaluation_hash"]) == 64 and len(body["input_hash"]) == 64


def test_evaluation_list_rejects_invalid_horizon(client, db_session):
    get_or_create_local_user(db_session, "alex")
    db_session.commit()
    response = client.get("/api/v1/investments/evaluations?horizon=2Q")
    assert response.status_code == 422
    assert response.headers.get("X-Error-Code") == "invalid_horizon"
