from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SourcePolicy:
    source: str
    access_mode: str
    public_scope: str
    rate_limit: str
    terms_risk: str
    automation_allowed: bool
    data_retention_rule: str
    status: str = "APPROVED_FOR_READ_ONLY_CAPTURE"


@dataclass(frozen=True)
class RawSignal:
    id: str
    source: str
    source_url: str
    external_id: str
    author_identifier: str | None
    published_at: datetime | None
    detected_at: datetime
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    lead_type_hint: str | None = None


@dataclass(frozen=True)
class NormalizedSignal:
    raw_signal: RawSignal
    canonical_text: str
    title: str
    text_for_analysis: str
    redactions: tuple[str, ...]
    source_scope: str


@dataclass(frozen=True)
class IntentResult:
    commercial_intent: str
    intent: str | None
    requested_product: str | None
    industry: str | None
    company_or_person: str | None
    city: str | None
    region: str | None
    budget_min: int | None
    budget_max: int | None
    currency: str | None
    deadline: str | None
    urgency: str
    existing_site: str | None
    required_features: tuple[str, ...]
    project_stage: str | None
    decision_maker_signal: str | None
    confidence: float
    evidence: tuple[str, ...]
    provider: str = "rules-v1"
    prompt_version: str = "rules-v1"
    abstain: bool = False
    abstain_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualificationResult:
    decision: str
    lead_type: str
    reasons: tuple[str, ...]
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class LeadScore:
    score: int
    label: str
    components: dict[str, dict[str, Any]]
    positive_factors: tuple[str, ...]
    limiting_factors: tuple[str, ...]
    human_summary: str


@dataclass(frozen=True)
class LeadResult:
    id: str
    rank: int
    lead_type: str
    lead_score: int
    score_label: str
    intent_score: int
    commercial_fit_score: int
    priority_score: int
    result_class: str
    commercial_fit_confidence: str
    commercial_value_confidence: str
    business_demand_class: str
    intent: str | None
    requested_product: str | None
    company_or_person: str | None
    industry: str | None
    location: dict[str, str | None]
    budget: dict[str, Any]
    deadline: str | None
    urgency: str
    freshness: dict[str, Any]
    source: str
    source_url: str
    original_signal_excerpt: str
    why_this_is_a_lead: str
    why_it_fits_vitrina: str
    confidence: float
    actionable_now: str
    verification_status: str
    dedupe_status: str
    score_explanation: LeadScore
    money_score_explanation: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HunterRun:
    profile_id: str
    started_at: datetime
    completed_at: datetime
    source_policies: tuple[SourcePolicy, ...]
    signals_seen: int
    signals_ingested: int
    signals_analyzed: int
    rejected: int
    needs_review: int
    qualified_hot_demand: int
    potential: int
    hot: int
    very_hot: int
    opportunity: int
    duplicates: int
    provider_failures: int
    manual_review_count: int
    average_latency_ms: float
    leads: tuple[LeadResult, ...]
    rejected_breakdown: dict[str, int]
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
