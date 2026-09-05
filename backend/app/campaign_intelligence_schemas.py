from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CampaignWizardRequest(BaseModel):
    workspace_id: str
    offer: str = Field(min_length=2, max_length=1000)
    audience: str = Field(min_length=2, max_length=1000)
    geography: str | None = Field(default=None, max_length=300)
    geographies: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["ru"])
    budget: float = Field(default=0, ge=0, le=1_000_000)
    platforms: list[str] = Field(default_factory=lambda: ["TELEGRAM"])
    goal: str = Field(default="Получить заявки", min_length=2, max_length=120)
    exclusions: list[str] = Field(default_factory=list)
    campaign_name: str | None = Field(default=None, max_length=200)
    brand_id: str | None = None
    offer_id: str | None = None
    use_llm: bool = True


class CampaignAnalyzeRequest(BaseModel):
    use_llm: bool = True


class CampaignScoreResponse(BaseModel):
    id: str
    community_id: str
    community_score: float
    lead_probability: float
    recommendation: str
    recommendation_reason: str
    score_breakdown: dict[str, Any] | None
    collection_slugs: list[str] | None


class CampaignLearningRequest(BaseModel):
    pass
