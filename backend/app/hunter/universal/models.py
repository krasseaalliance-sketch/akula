from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

T = TypeVar("T")


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Inference[T]:
    value: T
    confidence: float
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class BusinessInput:
    company_name: str | None = None
    website: str | None = None
    public_social_links: tuple[str, ...] = ()
    business_description: str | None = None
    product_description: str | None = None
    service_description: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    service_area: str | None = None
    customer_type: str | None = None
    known_minimum_order: float | None = None
    operator_notes: str | None = None

    def __post_init__(self) -> None:
        if not any((self.company_name, self.website, self.business_description, self.product_description, self.service_description)):
            raise ValueError("at least one business identifier or description is required")
        if self.known_minimum_order is not None and self.known_minimum_order < 0:
            raise ValueError("known_minimum_order cannot be negative")

    @property
    def supplied_fields(self) -> tuple[str, ...]:
        return tuple(name for name, value in asdict(self).items() if value not in (None, "", ()))


@dataclass(frozen=True)
class OfferNode:
    offer_id: str
    name: str
    offer_type: str
    ownership: str
    evidence: tuple[str, ...]
    confidence: float
    price_signal: float | None = None


@dataclass(frozen=True)
class OfferGraph:
    business_id: str
    nodes: tuple[OfferNode, ...]
    edges: tuple[dict[str, Any], ...] = ()
    version: str = "offer-graph-v1"


@dataclass(frozen=True)
class BuyerModel:
    offer_id: str
    buyer_types: tuple[str, ...]
    buyer_roles: tuple[str, ...]
    company_types: tuple[str, ...]
    consumer_types: tuple[str, ...]
    problem_contexts: tuple[str, ...]
    purchase_triggers: tuple[str, ...]
    commercial_events: tuple[str, ...]
    typical_requirements: tuple[str, ...]
    budget_signals: tuple[str, ...]
    urgency_signals: tuple[str, ...]
    decision_signals: tuple[str, ...]
    negative_buyer_signals: tuple[str, ...]
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class GeoModel:
    scope: str
    service_radius: str | None
    delivery_radius: str | None
    travel_allowed: bool | None
    remote_allowed: bool | None
    excluded_geographies: tuple[str, ...]
    evidence: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class BusinessLanguageModel:
    customer_interface_language: str | None
    business_languages: tuple[str, ...]
    market_languages: tuple[str, ...]
    source_languages: tuple[str, ...]
    required_understanding_languages: tuple[str, ...]
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class MarketContext:
    country: str | None
    currency: str | None
    timezone: str | None
    language_set: tuple[str, ...]
    regulatory_context_ref: str | None
    source_strategy_ref: str | None
    business_norms_ref: str | None
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class IntentMap:
    canonical_families: tuple[str, ...]
    business_specific_intents: tuple[str, ...]
    positive_patterns: tuple[str, ...]
    evidence: tuple[str, ...]
    version: str = "intent-map-v1"


@dataclass(frozen=True)
class NegativeIntentMap:
    exclusions: tuple[str, ...]
    patterns: tuple[str, ...]
    evidence: tuple[str, ...]
    version: str = "negative-intent-v1"


@dataclass(frozen=True)
class CommercialValueModel:
    known_minimum_order: float | None
    value_factors: tuple[str, ...]
    confidence_class: str
    unknown_budget_penalty: float
    repeat_potential: str
    upsell_potential: str
    sales_cycle_class: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class DemandModel:
    demand_model_id: str
    business_id: str
    offer_ids: tuple[str, ...]
    intent_classes: tuple[str, ...]
    buyer_models: tuple[str, ...]
    positive_intent_patterns: tuple[str, ...]
    negative_intent_patterns: tuple[str, ...]
    commercial_events: tuple[str, ...]
    required_context: tuple[str, ...]
    optional_context: tuple[str, ...]
    budget_model: dict[str, Any]
    geo_model: GeoModel
    language_model: BusinessLanguageModel
    freshness_model: dict[str, Any]
    commercial_value_model: CommercialValueModel
    exclusion_model: dict[str, Any]
    confidence: float
    evidence: tuple[str, ...]
    version: str = "demand-model-v1"


@dataclass(frozen=True)
class SourceStrategy:
    preferred: tuple[str, ...]
    secondary: tuple[str, ...]
    experimental: tuple[str, ...]
    unsuitable: tuple[str, ...]
    unavailable: tuple[str, ...]
    freshness_required: str
    cadence_minutes: int
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class MatchingProfile:
    business_id: str
    match_score: float
    intent_score: float
    commercial_fit_score: float
    priority_score: float
    matching_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    confidence: float
    version: str = "matching-profile-v1"


@dataclass(frozen=True)
class PolicyDecision:
    status: str
    category: str | None
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]
    version: str = "policy-gate-v1"


@dataclass(frozen=True)
class ClarificationQuestion:
    question_id: str
    text: str
    reason: str
    priority: int


@dataclass(frozen=True)
class BusinessModel:
    business_id: str
    model_version: str
    business_name: Inference[str | None]
    business_type: Inference[str]
    business_summary: Inference[str | None]
    industry_primary: Inference[str | None]
    industry_secondary: Inference[tuple[str, ...]]
    business_model_type: Inference[str | None]
    b2b_b2c_class: Inference[str]
    products: Inference[tuple[str, ...]]
    services: Inference[tuple[str, ...]]
    bundles: Inference[tuple[str, ...]]
    customer_segments: Inference[tuple[str, ...]]
    geographies: Inference[tuple[str, ...]]
    languages: Inference[tuple[str, ...]]
    price_positioning: Inference[str | None]
    minimum_commercial_value: Inference[float | None]
    seasonality: Inference[str | None]
    urgency_patterns: Inference[tuple[str, ...]]
    repeat_purchase_pattern: Inference[str | None]
    sales_cycle_class: Inference[str | None]
    regulatory_flags: Inference[tuple[str, ...]]
    overall_confidence: float
    evidence: tuple[str, ...]
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    supersedes: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.overall_confidence <= 1:
            raise ValueError("overall_confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UnderstandingResult:
    business_model: BusinessModel
    offer_graph: OfferGraph
    buyer_models: tuple[BuyerModel, ...]
    demand_model: DemandModel
    intent_map: IntentMap
    negative_intent_map: NegativeIntentMap
    commercial_value_model: CommercialValueModel
    geo_model: GeoModel
    language_model: BusinessLanguageModel
    market_context: MarketContext
    source_strategy: SourceStrategy
    matching_profile: MatchingProfile
    policy_decision: PolicyDecision
    clarification_questions: tuple[ClarificationQuestion, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
