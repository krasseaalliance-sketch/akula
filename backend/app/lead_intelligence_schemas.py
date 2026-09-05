from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntelligenceORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IntelligenceRunRequest(BaseModel):
    workspace_id: str
    campaign_id: str | None = None
    lead_ids: list[str] | None = None


class SearchProfileCreate(BaseModel):
    workspace_id: str
    campaign_id: str | None = None
    name: str = Field(min_length=2, max_length=160)
    natural_language_query: str = Field(min_length=3, max_length=2000)
    criteria: dict[str, Any] | None = None


class SearchProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    natural_language_query: str | None = Field(default=None, min_length=3, max_length=2000)
    criteria: dict[str, Any] | None = None
    status: str | None = None


class SimilarityRequest(BaseModel):
    workspace_id: str
    text: str = Field(min_length=1, max_length=10000)
    compared_texts: list[str] = Field(min_length=1, max_length=100)
    threshold: float = Field(default=0.92, ge=0, le=1)


class CommunityScoreResponse(IntelligenceORM):
    id: str
    community_id: str
    community_score: float
    activity_score: float
    size_score: float
    lead_score: float
    conversion_score: float
    rules_score: float
    geography_score: float
    topic_score: float
    rationale: dict[str, Any] | None
    created_at: datetime
