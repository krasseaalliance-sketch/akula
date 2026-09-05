from __future__ import annotations

from datetime import datetime

from ..freshness import apply_freshness_cap, classify_freshness, freshness_score
from ..models import IntentResult, LeadScore, NormalizedSignal, QualificationResult
from ..profiles.vitrina_services import HunterProfile


def score_lead(signal: NormalizedSignal, intent: IntentResult, qualification: QualificationResult, profile: HunterProfile, now: datetime) -> LeadScore:
    freshness_info = classify_freshness(signal.raw_signal.published_at, now)
    values = {
        "direct_order_intent": 100 if intent.commercial_intent == "HIGH" else 65 if intent.commercial_intent == "MEDIUM" else 0,
        "project_specificity": min(100, 25 + len(intent.evidence) * 18 + len(intent.required_features) * 8),
        "budget_signal": 90 if intent.budget_min and intent.budget_max else 65 if intent.budget_min else 20,
        "requirements_signal": min(100, 20 + len(intent.required_features) * 16),
        "deadline_signal": 95 if intent.deadline else 25,
        "urgency_signal": {"HIGH": 100, "MEDIUM": 68, "LOW": 35}.get(intent.urgency, 0),
        "contractor_signal": 100 if intent.decision_maker_signal else 35,
        "commercial_scale": 85 if intent.industry or intent.budget_max else 55,
        "freshness": freshness_score(freshness_info),
        "vitrina_product_fit": 100 if intent.intent in profile.primary_offers else 82 if intent.intent in profile.secondary_offers else 0,
    }
    components: dict[str, dict[str, object]] = {}
    for key, weight in profile.weights.items():
        value = int(values[key])
        components[key] = {"value": value, "weight": weight, "weighted": round(value * weight / 100, 2)}
    score = max(0, min(100, round(sum(float(item["weighted"]) for item in components.values()))))
    score = apply_freshness_cap(score, freshness_info)
    label = "VERY_HOT" if score >= 90 else "HOT" if score >= 75 else "POTENTIAL" if score >= 60 else "INTEREST" if score >= 40 else "NOISE"
    positives = tuple(key for key, item in components.items() if int(item["value"]) >= 80)
    limiting = tuple(key for key, item in components.items() if int(item["value"]) < 50)
    human = f"{intent.requested_product or 'Digital service'} request with {intent.confidence:.0%} intent confidence; freshness={freshness_info.bucket}; score is supported by {', '.join(positives[:3]) or 'limited evidence'}."
    return LeadScore(score, label, components, positives, limiting, human)
