from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class InvestmentDecisionRequest(BaseModel):
    decision_type: Literal["accept", "reject", "defer", "modify", "no_action"]
    rationale: str | None = Field(default=None, max_length=2000)


class InvestmentDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str
    recommendation_id: str
    decision_type: Literal["accept", "reject", "defer", "modify", "no_action"]
    decision_timestamp: datetime
    rationale: str | None
    recommendation_hash: str
    created_at: datetime | None


class InvestmentDecisionListResponse(BaseModel):
    schema_version: Literal["atlas-investment-decision-list/v1"]
    items: list[InvestmentDecisionResponse]


class InvestmentDecisionEnvelope(BaseModel):
    schema_version: Literal["atlas-investment-decision/v1"]
    decision: InvestmentDecisionResponse
    replayed: bool


class InvestmentEvidenceItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    category: str
    subject_security_id: str | None = None
    owner_id: int | None = None
    reference: dict[str, Any]
    excerpt: str | None = None
    numeric_value: str | None = None


class InvestmentEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    packet_id: str
    packet_hash: str
    owner_id: int
    subject_security_id: str
    analysis_as_of: datetime
    items: list[InvestmentEvidenceItemResponse]


class InvestmentCommitteeFindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    finding: dict[str, Any]
    finding_hash: str
    as_of: datetime


class InvestmentOutcomeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_id: str
    outcome_hash: str
    recommendation_id: str
    recommendation_hash: str
    decision_id: str | None = None
    evaluation_as_of: datetime


class InvestmentOutcomeListResponse(BaseModel):
    schema_version: Literal["atlas-investment-outcome-list/v1"]
    items: list[InvestmentOutcomeResponse]


class InvestmentRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    recommendation: dict[str, Any]


class InvestmentRecommendationListResponse(BaseModel):
    schema_version: Literal["atlas-investment-recommendation-list/v1"]
    items: list[dict[str, Any]]


class InvestmentEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["atlas-investment-evaluation/v1"]
    evaluation: dict[str, Any]


class InvestmentEvaluationListResponse(BaseModel):
    schema_version: Literal["atlas-investment-evaluation-list/v1"]
    items: list[dict[str, Any]]


class InvestmentEvaluationReplayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["atlas-investment-evaluation-replay/v1"]
    evaluation_id: str
    replay_state: str
    verified: bool
    evaluation_hash: str
    input_hash: str
    replayed_at: datetime
