from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.investments.discovery import DiscoveryStatus, DiscoveryUniverse

class DiscoveryCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    universe: DiscoveryUniverse
    security: dict[str, Any]
    status: DiscoveryStatus
    reason: str
    source: str
    as_of: datetime
    freshness: str
    methodology_version: str
    metrics: dict[str, str | None]
    metric_states: dict[str, str]
    recommendation_id: str | None = None
    detail_available: bool = True

class DiscoveryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    as_of: datetime
    methodology_version: str
    candidates: list[DiscoveryCandidateResponse]
    omitted_count: int = Field(ge=0)
    universe: DiscoveryUniverse = DiscoveryUniverse.PORTFOLIO
    source_scope: str = "server-owned-current-only"

class DiscoveryComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_ids: list[str] = Field(min_length=2, max_length=10)
    universe: DiscoveryUniverse = DiscoveryUniverse.PORTFOLIO
    metric_names: list[str] = Field(min_length=1, max_length=20)

class DiscoveryComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    candidate_ids: list[str]
    metrics: list[dict[str, Any]]
    comparable: bool
    limitations: list[str]
    metric_compatibility: dict[str, bool] = {}
