from sqlalchemy import inspect

from app.investment_schemas import (
    InvestmentDecisionEnvelope, InvestmentDecisionRequest,
    InvestmentEvidenceResponse, InvestmentOutcomeListResponse,
    InvestmentRecommendationListResponse, InvestmentRecommendationResponse,
)
from app.models import (
    InvestmentCommitteeFinding, InvestmentCommitteeRun, InvestmentDecisionRecord,
    InvestmentEvidencePacket, InvestmentOutcomeRecord, InvestmentRecommendationRecord,
)
from app.routes.investment_persistence import router


def test_investment_api_is_typed_and_separate_from_forecast_contracts():
    expected = {
        ("GET", "/api/v1/investments/recommendations"): InvestmentRecommendationListResponse,
        ("GET", "/api/v1/investments/recommendations/{recommendation_id}"): InvestmentRecommendationResponse,
        ("GET", "/api/v1/investments/recommendations/{recommendation_id}/evidence"): InvestmentEvidenceResponse,
        ("POST", "/api/v1/investments/recommendations/{recommendation_id}/decisions"): InvestmentDecisionEnvelope,
        ("GET", "/api/v1/investments/recommendations/{recommendation_id}/outcomes"): InvestmentOutcomeListResponse,
    }
    for route in router.routes:
        for method in getattr(route, "methods", set()):
            if (method, route.path) in expected:
                assert route.response_model is expected[(method, route.path)]
    assert InvestmentDecisionRequest.model_fields["decision_type"].annotation is not None
    assert all("forecast" not in route.path for route in router.routes)


def test_investment_tables_have_owner_and_immutable_identity_constraints():
    for model, identity in (
        (InvestmentCommitteeRun, "run_id"),
        (InvestmentCommitteeFinding, "finding_id"),
        (InvestmentEvidencePacket, "packet_id"),
        (InvestmentRecommendationRecord, "recommendation_id"),
        (InvestmentDecisionRecord, "decision_id"),
        (InvestmentOutcomeRecord, "outcome_id"),
    ):
        columns = inspect(model).columns
        assert "owner_id" in columns
        assert identity in columns
        assert "payload_json" in columns or model is InvestmentDecisionRecord


def test_decision_command_cannot_accept_analytical_fields():
    command = InvestmentDecisionRequest.model_validate({"decision_type": "accept", "action": "BUY", "owner_id": 999})
    assert command.decision_type == "accept"
    assert not hasattr(command, "action")
    assert not hasattr(command, "owner_id")
