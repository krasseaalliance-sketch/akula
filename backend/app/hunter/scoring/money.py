from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..freshness import classify_freshness, freshness_score
from ..models import IntentResult, NormalizedSignal, QualificationResult
from ..profiles.vitrina_services import HunterProfile


@dataclass(frozen=True)
class MoneyScore:
    intent_score: int
    commercial_fit_score: int
    priority_score: int
    result_class: str
    commercial_fit_confidence: str
    commercial_value_confidence: str
    business_demand_class: str
    components: dict[str, dict[str, Any]]
    human_summary: str


def source_quality_from_metrics(metrics: dict[str, Any]) -> int:
    if not metrics.get("signals_seen"):
        return 0
    action = float(metrics.get("actionable_rate") or 0) * 100
    age = metrics.get("median_age")
    freshness = max(0.0, 100.0 - float(age) / 72 * 100) if age is not None else 0.0
    fpr = metrics.get("false_positive_rate")
    precision = (1.0 - float(fpr)) * 100 if fpr is not None else 50.0
    return round(action * 0.45 + freshness * 0.35 + precision * 0.20)


def score_money(
    signal: NormalizedSignal,
    intent: IntentResult,
    qualification: QualificationResult,
    profile: HunterProfile,
    now: datetime,
    *,
    source_quality: int,
) -> MoneyScore:
    metadata = signal.raw_signal.metadata
    freshness = classify_freshness(signal.raw_signal.published_at, now)
    freshness_value = freshness_score(freshness)
    manual_verified = bool(metadata.get("manual_verified"))
    actionable = str(metadata.get("actionable_now", "UNKNOWN")).upper() == "YES"

    direct = 35 if intent.commercial_intent == "HIGH" else 23 if intent.commercial_intent == "MEDIUM" else 0
    specificity = min(20, len(intent.evidence) * 6 + len(intent.required_features) * 2)
    requirements = min(15, 5 + len(intent.required_features) * 2) if intent.intent else 0
    time_signal = 10 if intent.deadline or intent.urgency == "HIGH" else 6 if intent.urgency == "MEDIUM" else 3
    verification = 15 if actionable and manual_verified else 8 if actionable else 0
    freshness_component = 10 if freshness.within_72h else round(freshness_value / 10)
    intent_score = min(100, max(0, round(direct + specificity + requirements + time_signal + verification + freshness_component)))

    fit_base = profile.money_filter.unknown_budget_base
    product = intent.intent or ""
    text_lower = signal.text_for_analysis.casefold()
    company_signal = bool(intent.industry or any(marker in text_lower for marker in ("бизнес", "компан", "бренд", "магазин", "агентств", "корпоратив")))
    tender_signal = any(marker in text_lower for marker in ("тендер", "rfq", "закупк", "запрос коммерческого предложения", "procurement"))
    design_dev_signal = product in {"BUILD_WEBSITE", "REDESIGN_WEBSITE", "BUILD_ECOMMERCE", "BUILD_CORPORATE_SITE"} and any(feature in intent.required_features for feature in ("FIGMA", "TILDA", "RESPONSIVE", "FORM"))
    integration_signal = any(feature in intent.required_features for feature in ("INTEGRATION", "API", "CRM", "PAYMENTS"))
    if product in {"BUILD_WEBSITE", "REDESIGN_WEBSITE", "BUILD_CORPORATE_SITE", "BUILD_ECOMMERCE", "BUILD_WEB_APP", "BUILD_MOBILE_APP"}:
        fit_base += 12
    if company_signal:
        fit_base += 8
    fit_base += min(12, len(intent.required_features) * 2)
    if intent.project_stage == "SPECIFIED":
        fit_base += 8
    if integration_signal:
        fit_base += 7
    if intent.existing_site == "YES":
        fit_base += 5
    if any(marker in text_lower for marker in ("поддержк", "дальнейш", "сопровожд", "на постоянку")):
        fit_base += 5

    budget = max(intent.budget_min or 0, intent.budget_max or 0)
    budget_cap: int | None = None
    if budget:
        for upper, cap in profile.money_filter.budget_caps:
            if budget <= upper:
                budget_cap = cap
                break
        if budget_cap is None:
            budget_cap = 100
        if budget <= 5_000:
            fit_base = min(fit_base, 5)
        else:
            fit_base = min(fit_base, budget_cap)
        fit_confidence = "HIGH"
    else:
        budget_cap = None
        strong_evidence = sum((company_signal, len(intent.required_features) >= 3, integration_signal, design_dev_signal, bool(intent.deadline or intent.urgency == "HIGH"), intent.project_stage == "SPECIFIED"))
        very_strong_evidence = strong_evidence >= 5 and (tender_signal or "корпоратив" in text_lower or "procurement" in text_lower)
        budget_cap = profile.money_filter.unknown_budget_very_strong_cap if very_strong_evidence else profile.money_filter.unknown_budget_strong_cap if strong_evidence >= 4 else profile.money_filter.unknown_budget_default_cap
        fit_base = min(fit_base, budget_cap)
        fit_confidence = "MEDIUM" if strong_evidence >= 3 else "LOW"
    commercial_fit = min(100, max(0, fit_base))
    business_demand_class = classify_business_demand(text_lower, intent, budget, company_signal, tender_signal)

    actionability_value = 100 if actionable and manual_verified else 70 if actionable else 25
    priority = round(
        intent_score * commercial_fit / 100 * profile.money_filter.priority_weights[0][1]
        + freshness_value * profile.money_filter.priority_weights[1][1]
        + actionability_value * profile.money_filter.priority_weights[2][1]
        + source_quality * profile.money_filter.priority_weights[3][1]
    )
    if commercial_fit <= 10:
        priority = min(priority, 25)

    result_class = classify_result(
        actionable=actionable,
        manual_verified=manual_verified,
        intent_score=intent_score,
        commercial_fit=commercial_fit,
        fit_confidence=fit_confidence,
        priority=priority,
        profile=profile,
    )
    components = {
        "intent": {"value": intent_score, "direct": direct, "specificity": specificity, "requirements": requirements, "time": time_signal, "verification": verification, "freshness": freshness_component},
        "commercial_fit": {"value": commercial_fit, "budget": budget or None, "budget_cap": budget_cap, "base_before_cap": fit_base, "confidence": fit_confidence, "company_signal": company_signal, "tender_signal": tender_signal, "strong_evidence": strong_evidence if not budget else None},
        "priority": {"value": priority, "source_quality": source_quality, "actionability": actionability_value, "freshness": freshness_value},
    }
    summary = f"intent={intent_score}, commercial_fit={commercial_fit}, priority={priority}; class={result_class}; business_class={business_demand_class}; budget={'UNKNOWN' if not budget else budget}."
    return MoneyScore(intent_score, commercial_fit, priority, result_class, fit_confidence, fit_confidence, business_demand_class, components, summary)


def classify_business_demand(text: str, intent: IntentResult, budget: int, company_signal: bool, tender_signal: bool) -> str:
    if tender_signal:
        return "TENDER_RFP"
    complexity = len(intent.required_features) + (2 if intent.project_stage == "SPECIFIED" else 0) + (2 if intent.intent in {"BUILD_WEB_APP", "BUILD_MOBILE_APP", "AUTOMATE_BUSINESS_PROCESS"} else 0)
    if company_signal and (complexity >= 5 or any(marker in text for marker in ("корпоратив", "заказчик", "несколько отделов", "стейкхолдер"))):
        return "CORPORATE_PROJECT"
    if company_signal or complexity >= 4:
        return "BUSINESS_PROJECT"
    if budget and budget <= 15_000:
        return "MICRO_FREELANCE"
    return "SMALL_PROJECT"


def classify_result(*, actionable: bool, manual_verified: bool, intent_score: int, commercial_fit: int, fit_confidence: str, priority: int, profile: HunterProfile) -> str:
    if not actionable:
        return "NOISE"
    if intent_score < 60:
        return "NOISE"
    if fit_confidence == "MEDIUM" and commercial_fit >= profile.money_filter.good_fit_min:
        return "ACTIONABLE_UNKNOWN_VALUE"
    if commercial_fit < profile.money_filter.good_fit_min:
        return "ACTIONABLE_LOW_VALUE"
    if commercial_fit >= profile.money_filter.hot_money_fit_min and priority >= 70:
        return "HOT_MONEY"
    return "GOOD_FIT"
