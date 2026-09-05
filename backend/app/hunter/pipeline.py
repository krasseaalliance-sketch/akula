from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from statistics import median
from time import perf_counter
from typing import Any

from .dedupe import classify_duplicate
from .freshness import classify_freshness
from .intent import RulesIntentProvider
from .models import HunterRun, LeadResult, NormalizedSignal
from .normalization import normalize_signal
from .profiles.vitrina_services import VITRINA_SERVICES_V1, HunterProfile
from .qualification import qualify_signal
from .safety import assert_hunter_outbound_disabled
from .scoring import score_lead
from .scoring.money import score_money, source_quality_from_metrics
from .sources import ManualJsonSourceAdapter


class HunterPipeline:
    def __init__(self, profile: HunterProfile = VITRINA_SERVICES_V1):
        self.profile = profile
        self.intent_provider = RulesIntentProvider()

    def run(self, source_path: str, *, now: datetime | None = None) -> HunterRun:
        assert_hunter_outbound_disabled()
        now = now or datetime.now(UTC)
        started = datetime.now(UTC)
        policy, raw_signals = ManualJsonSourceAdapter(source_path).read()
        leads: list[LeadResult] = []
        normalized_prior: list[NormalizedSignal] = []
        rejected_breakdown: Counter[str] = Counter()
        counts = Counter()
        elapsed_total = 0.0
        age_hours: list[float] = []
        detection_latency_minutes: list[float] = []
        source_stats: dict[str, dict[str, object]] = {}
        money_context: dict[str, tuple[NormalizedSignal, object, object]] = {}

        for raw in raw_signals:
            started_item = perf_counter()
            counts["signals_ingested"] += 1
            source_stat = source_stats.setdefault(raw.source, {"signals_seen": 0, "qualified": 0, "actionable": 0, "ages": [], "false_positives": 0, "manual_reviewed": 0})
            source_stat["signals_seen"] = int(source_stat["signals_seen"]) + 1
            freshness = classify_freshness(raw.published_at, now)
            if freshness.age_hours is not None:
                age_hours.append(freshness.age_hours)
                source_stat["ages"].append(freshness.age_hours)
                if raw.detected_at and raw.published_at:
                    detection_latency_minutes.append(max(0.0, (raw.detected_at - raw.published_at).total_seconds() / 60))
                for window in (6, 24, 72):
                    if freshness.age_hours <= window:
                        counts[f"signals_last_{window}h"] += 1
            normalized = normalize_signal(raw)
            normalized_prior.append(normalized)
            intent = self.intent_provider.analyze(normalized)
            qualification = qualify_signal(normalized, intent)
            if qualification.decision == "QUALIFIED":
                source_stat["qualified"] = int(source_stat["qualified"]) + 1
            if raw.metadata.get("manual_verified"):
                source_stat["manual_reviewed"] = int(source_stat["manual_reviewed"]) + 1
                if str(raw.metadata.get("manual_verdict", "")).upper() == "FALSE_POSITIVE":
                    source_stat["false_positives"] = int(source_stat["false_positives"]) + 1
            duplicate_status, _ = classify_duplicate(normalized, normalized_prior[:-1])
            elapsed_total += (perf_counter() - started_item) * 1000
            counts["signals_analyzed"] += 1
            if duplicate_status in {"EXACT_DUPLICATE", "LIKELY_DUPLICATE"}:
                counts["duplicates"] += 1
                rejected_breakdown["DUPLICATE"] += 1
                continue
            if qualification.decision == "OPPORTUNITY":
                counts["opportunity"] += 1
                continue
            if qualification.decision == "REJECTED":
                counts["rejected"] += 1
                for reason in qualification.reasons:
                    rejected_breakdown[reason] += 1
                continue
            if qualification.decision == "NEEDS_REVIEW":
                counts["needs_review"] += 1
                counts["manual_review_count"] += 1
                continue
            if freshness.within_72h:
                counts["fresh_demand"] += 1
            if freshness.bucket in {"ULTRA_FRESH", "FRESH", "RECENT"}:
                counts[f"{freshness.bucket.lower()}_leads"] += 1
            actionable_now = str(raw.metadata.get("actionable_now", "UNKNOWN")).upper()
            if actionable_now not in {"YES", "NO", "UNKNOWN"}:
                actionable_now = "UNKNOWN"
            if actionable_now == "YES":
                counts["actionable_demand"] += 1
                if qualification.decision == "QUALIFIED":
                    source_stat["actionable"] = int(source_stat["actionable"]) + 1
            elif actionable_now == "UNKNOWN":
                counts["manual_review_count"] += 1
            score = score_lead(normalized, intent, qualification, self.profile, now)
            if score.score < self.profile.minimum_score:
                counts["rejected"] += 1
                if freshness.bucket in {"STALE", "DEAD"}:
                    counts["stale_rejected"] += 1
                    rejected_breakdown["STALE_FRESHNESS_GATE"] += 1
                else:
                    rejected_breakdown["LOW_SCORE"] += 1
                continue
            money_context[raw.id] = (normalized, intent, qualification)
            money = score_money(normalized, intent, qualification, self.profile, now, source_quality=50)
            lead = LeadResult(
                id=raw.id, rank=0, lead_type="HOT_DEMAND", lead_score=score.score,
                score_label=score.label, intent_score=money.intent_score,
                commercial_fit_score=money.commercial_fit_score, priority_score=money.priority_score,
                result_class=money.result_class, commercial_fit_confidence=money.commercial_fit_confidence,
                commercial_value_confidence=money.commercial_value_confidence,
                business_demand_class=money.business_demand_class,
                intent=intent.intent,
                requested_product=intent.requested_product,
                company_or_person=intent.company_or_person, industry=intent.industry,
                location={"city": intent.city, "region": intent.region},
                budget={"min": intent.budget_min, "max": intent.budget_max, "currency": intent.currency},
                deadline=intent.deadline, urgency=intent.urgency,
                freshness={"published_at": raw.published_at.isoformat() if raw.published_at else None, "detected_at": raw.detected_at.isoformat(), **freshness.to_dict()},
                source=raw.source, source_url=raw.source_url,
                original_signal_excerpt=normalized.text_for_analysis[:420],
                why_this_is_a_lead="The public signal contains a direct request for a digital contractor/project, not a supplier offer or generic discussion.",
                why_it_fits_vitrina=f"Matches Vitrina profile intent {intent.intent} with product fit {score.components['vitrina_product_fit']['value']}/100.",
                confidence=qualification.confidence, actionable_now=actionable_now,
                verification_status=str(raw.metadata.get("verification_status", "SOURCE_CAPTURE_VERIFIED")),
                dedupe_status=duplicate_status, score_explanation=score, money_score_explanation=money,
            )
            leads.append(lead)
            counts["qualified_hot_demand"] += 1
            counts["hot" if score.score >= 75 else "potential"] += 1
            if score.score >= 90:
                counts["very_hot"] += 1

        completed = datetime.now(UTC)
        metrics = {
            "signals_last_6h": counts["signals_last_6h"], "signals_last_24h": counts["signals_last_24h"], "signals_last_72h": counts["signals_last_72h"],
            "fresh_demand": counts["fresh_demand"], "actionable_demand": counts["actionable_demand"],
            "ultra_fresh_leads": counts["ultra_fresh_leads"], "fresh_leads": counts["fresh_leads"], "recent_leads": counts["recent_leads"],
            "stale_rejected": counts["stale_rejected"], "median_signal_age": round(median(age_hours), 3) if age_hours else None,
            "p90_signal_age": round(sorted(age_hours)[max(0, int(len(age_hours) * 0.9) - 1)], 3) if age_hours else None,
            "publication_to_detection_latency": round(median(detection_latency_minutes), 3) if detection_latency_minutes else None,
            "precision": None, "recall": None,
            "source_metrics": {
                source: {
                    "signals_seen": int(stat["signals_seen"]),
                    "qualified": int(stat["qualified"]),
                    "actionable": int(stat["actionable"]),
                    "actionable_rate": round(int(stat["actionable"]) / max(1, int(stat["qualified"])), 4),
                    "median_age": round(median(stat["ages"]), 3) if stat["ages"] else None,
                    "max_age": round(max(stat["ages"]), 3) if stat["ages"] else None,
                    "false_positive_rate": round(int(stat["false_positives"]) / max(1, int(stat["manual_reviewed"])), 4) if stat["manual_reviewed"] else None,
                    "manual_reviewed": int(stat["manual_reviewed"]),
                    "false_positives": int(stat["false_positives"]),
                }
                for source, stat in source_stats.items()
            },
        }
        money_source_stats: dict[str, dict[str, Any]] = {}
        reprioritized: list[LeadResult] = []
        for lead in leads:
            normalized, intent, qualification = money_context[lead.id]
            source_metrics = metrics["source_metrics"].get(lead.source, {})
            money = score_money(
                normalized, intent, qualification, self.profile, now,
                source_quality=source_quality_from_metrics(source_metrics),
            )
            reprioritized.append(replace(
                lead, intent_score=money.intent_score, commercial_fit_score=money.commercial_fit_score,
                priority_score=money.priority_score, result_class=money.result_class,
                commercial_fit_confidence=money.commercial_fit_confidence,
                commercial_value_confidence=money.commercial_value_confidence,
                business_demand_class=money.business_demand_class,
                money_score_explanation=money,
            ))
            source_stat = money_source_stats.setdefault(lead.source, {"budget_values": [], "money_leads": 0, "commercial_fit_total": 0, "hot_money_count": 0, "good_fit_count": 0, "low_value_count": 0, "unknown_value_count": 0})
            if money.result_class == "NOISE":
                continue
            source_stat["money_leads"] += 1
            source_stat["commercial_fit_total"] += money.commercial_fit_score
            budget_value = max(intent.budget_min or 0, intent.budget_max or 0)
            if budget_value:
                source_stat["budget_values"].append(budget_value)
            for key, result_class in (("hot_money_count", "HOT_MONEY"), ("good_fit_count", "GOOD_FIT"), ("low_value_count", "ACTIONABLE_LOW_VALUE"), ("unknown_value_count", "ACTIONABLE_UNKNOWN_VALUE")):
                if money.result_class == result_class:
                    source_stat[key] += 1
        for source, source_stat in metrics["source_metrics"].items():
            money_stat = money_source_stats.get(source, {})
            budgets = money_stat.get("budget_values", [])
            money_leads = int(money_stat.get("money_leads", 0))
            source_stat.update({
                "average_budget": round(sum(budgets) / len(budgets), 2) if budgets else None,
                "median_budget": round(median(budgets), 2) if budgets else None,
                "unknown_budget_rate": round(1 - len(budgets) / money_leads, 4) if money_leads else None,
                "commercial_fit_average": round(money_stat.get("commercial_fit_total", 0) / money_leads, 2) if money_leads else None,
                "hot_money_count": money_stat.get("hot_money_count", 0),
                "good_fit_count": money_stat.get("good_fit_count", 0),
                "low_value_count": money_stat.get("low_value_count", 0),
                "unknown_value_count": money_stat.get("unknown_value_count", 0),
            })
        ranked = tuple(replace(lead, rank=index) for index, lead in enumerate(sorted(reprioritized, key=lambda item: (-item.priority_score, -item.intent_score, item.id)), 1))
        return HunterRun(
            profile_id=self.profile.profile_id, started_at=started, completed_at=completed,
            source_policies=(policy,), signals_seen=len(raw_signals),
            signals_ingested=counts["signals_ingested"], signals_analyzed=counts["signals_analyzed"],
            rejected=counts["rejected"], needs_review=counts["needs_review"],
            qualified_hot_demand=counts["qualified_hot_demand"], potential=counts["potential"],
            hot=counts["hot"], very_hot=counts["very_hot"], opportunity=counts["opportunity"],
            duplicates=counts["duplicates"], provider_failures=0,
            manual_review_count=counts["manual_review_count"],
            average_latency_ms=round(elapsed_total / max(1, len(raw_signals)), 3),
            leads=ranked, rejected_breakdown=dict(rejected_breakdown), metrics=metrics,
        )
