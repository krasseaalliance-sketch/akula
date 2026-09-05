from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Brand,
    Campaign,
    Community,
    CommunityScoreSnapshot,
    Company,
    Lead,
    LeadIntelligenceAnalysis,
    LeadIntelligenceRun,
    MessageRecommendation,
    Offer,
)
from ..services import audit, normalize_text
from .provider import OpenAIResponsesProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntelligenceResult:
    intent: str
    pain: str
    need: str
    confidence: float
    score: float
    matched_signals: list[str]
    excluded_signals: list[str]
    explanation: str
    recommendation: str
    recommendation_reason: str
    provider: str = "RULES"
    model: str = "lead-intelligence-rules-v1"


INTENTS: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("DIGITAL_SERVICE", ("website", "site", "сайт", "разработчик", "developer", "crm", "бот", "bot", "automation", "автоматиз"), "Нет цифрового инструмента или исполнителя", "Website / Telegram Bot / Mobile App"),
    ("BALI_TRAVEL", ("bali", "бали", "попутчик", "экскурс", "travel", "trip", "поездк"), "Не хватает понятного маршрута или компании", "Bali Trip"),
    ("YACHT_TRIP", ("yacht", "яхт", "морю", "яхта"), "Нет подходящего формата отдыха и компании", "Yacht Trip"),
    ("LOCAL_EVENT", ("событи", "мероприят", "куда сходить", "афиша", "event"), "Не хватает понятного варианта досуга", "Event / Consulting"),
    ("QUIZ", ("quiz", "квиз", "викторин", "загадк", "настолк"), "Не хватает вовлекающего игрового формата", "Online Quiz"),
    ("CHALLENGE", ("challenge", "челлендж", "познаком", "скучно", "компан"), "Недостаток окружения и повода для знакомства", "Challenge"),
    ("CONSULTING", ("консультац", "consult", "стратег", "совет"), "Не хватает экспертного решения", "Consulting"),
)


def _match(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _rule_classify(text: str, *, contact_initiated: bool) -> IntelligenceResult:
    normalized = normalize_text(text).casefold()
    if not normalized:
        return IntelligenceResult("UNKNOWN", "Недостаточно данных", "Уточнить контекст", 0.1, 0, [], ["EMPTY"], "Сообщение не содержит текста.", "WAIT_FOR_CONTEXT", "Сначала нужен контекст.")
    matched: list[str] = []
    intent, pain, need, confidence = "UNKNOWN", "Недостаточно данных", "Уточнить контекст", 0.24
    for name, terms, pain_text, need_text in INTENTS:
        signals = _match(normalized, terms)
        if len(signals) > len(matched):
            matched, intent, pain, need = signals, name, pain_text, need_text
            confidence = min(0.96, 0.52 + len(signals) * 0.12)
    excluded: list[str] = []
    if any(term in normalized for term in ("spam", "заработок без вложений", "scam", "не пишите мне", "не писать")):
        excluded.append("SPAM_OR_DO_NOT_CONTACT")
    if excluded:
        return IntelligenceResult(intent, pain, need, confidence, 0, matched, excluded, "Обнаружен сигнал нежелательного контакта или спама.", "DO_NOT_CONTACT", "Не инициировать контакт.")
    score = round(min(100, confidence * 75 + min(len(matched), 4) * 5), 2)
    if contact_initiated:
        recommendation, reason = "DIRECT_REPLY", "Пользователь сам начал контакт; ответить в текущем диалоге после проверки фактов."
    elif matched:
        recommendation, reason = "PUBLIC_REPLY", "Есть публичный сигнал намерения; сначала дать короткий релевантный публичный ответ."
    else:
        recommendation, reason = "WAIT_FOR_CONTEXT", "Намерение недостаточно выражено; не отправлять инициативное личное сообщение."
    explanation = f"Намерение {intent} определено по сигналам: {', '.join(matched) or 'нет явных сигналов'}."
    return IntelligenceResult(intent, pain, need, confidence, score, matched, excluded, explanation, recommendation, reason)


def _token_vector(text: str) -> dict[str, float]:
    tokens = re.findall(r"[\w-]{2,}", normalize_text(text).casefold())
    result: dict[str, float] = {}
    for token in tokens:
        result[token] = result.get(token, 0) + 1
    return result


def token_cosine(left: str, right: str) -> float:
    a, b = _token_vector(left), _token_vector(right)
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    return round(dot / (math.sqrt(sum(value * value for value in a.values())) * math.sqrt(sum(value * value for value in b.values()))), 4)


class LeadIntelligenceService:
    def analyze_text(self, text: str, *, contact_initiated: bool = False, context: dict[str, Any] | None = None) -> IntelligenceResult:
        result = _rule_classify(text, contact_initiated=contact_initiated)
        settings = get_settings()
        if settings.openai_enabled and settings.openai_api_key:
            try:
                output = OpenAIResponsesProvider().classify(text=text, context=context or {})
                data = output.data
                return IntelligenceResult(
                    intent=str(data.get("intent", result.intent)), pain=str(data.get("pain", result.pain)),
                    need=str(data.get("need", result.need)), confidence=float(data.get("confidence", result.confidence)),
                    score=round(float(data.get("confidence", result.confidence)) * 100, 2),
                    matched_signals=result.matched_signals, excluded_signals=result.excluded_signals,
                    explanation=str(data.get("reason", result.explanation)),
                    recommendation=str(data.get("recommendation", result.recommendation)),
                    recommendation_reason=result.recommendation_reason, provider=output.provider, model=output.model,
                )
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
                # AI failure cannot unblock or loosen any policy; rules stay as the safe fallback.
                logger.warning("OpenAI lead classification fell back to rules: %s", type(exc).__name__)
        return result

    def match_offer(self, db: Session, *, workspace_id: str, result: IntelligenceResult) -> tuple[Offer | None, float]:
        offers = list(db.scalars(select(Offer).join(Campaign, Campaign.offer_id == Offer.id).join(Brand, Brand.id == Offer.brand_id).join(Company, Company.id == Brand.company_id).where(Company.workspace_id == workspace_id)).all())
        intent = result.intent.casefold()
        best: tuple[Offer | None, float] = (None, 0.0)
        for offer in offers:
            haystack = f"{offer.name} {offer.type} {offer.description or ''}".casefold()
            score = 0.0
            if intent == "DIGITAL_SERVICE" and any(term in haystack for term in ("website", "bot", "app", "digital", "сайт", "бот")):
                score = 0.92
            elif (intent == "BALI_TRAVEL" and any(term in haystack for term in ("travel", "bali", "trip", "пут"))) or (intent == "YACHT_TRIP" and any(term in haystack for term in ("yacht", "яхт"))):
                score = 0.94
            elif intent in {"QUIZ", "CHALLENGE"} and any(term in haystack for term in ("quiz", "challenge", "квиз", "челлендж")):
                score = 0.9
            elif result.need.casefold() in haystack:
                score = 0.65
            if score > best[1]:
                best = (offer, score)
        return best

    def analyze_lead(self, db: Session, *, lead: Lead, actor_id: str, run: LeadIntelligenceRun) -> LeadIntelligenceAnalysis:
        result = self.analyze_text(lead.raw_text, contact_initiated=lead.contact_initiated, context={"campaign_id": lead.campaign_id})
        offer, offer_score = self.match_offer(db, workspace_id=lead.workspace_id, result=result)
        lead.intent, lead.pain, lead.need = result.intent, result.pain, result.need
        lead.intent_confidence, lead.pain_confidence, lead.need_confidence = result.confidence, result.confidence, result.confidence
        lead.score, lead.confidence = result.score, result.confidence
        lead.score_breakdown = {"intent": result.confidence, "signals": len(result.matched_signals), "offer_match": offer_score}
        lead.matched_signals, lead.excluded_signals = result.matched_signals, result.excluded_signals
        lead.explanation, lead.recommended_action = result.explanation, result.recommendation
        lead.first_contact_recommendation, lead.recommendation_reason = result.recommendation, result.recommendation_reason
        lead.offer_match_id, lead.offer_match_score = offer.id if offer else None, offer_score
        lead.ai_provider, lead.ai_model, lead.evaluated_at = result.provider, result.model, datetime.utcnow()
        if "SPAM_OR_DO_NOT_CONTACT" in result.excluded_signals:
            lead.status = "DO_NOT_CONTACT"
        elif lead.status in {"REJECTED_IRRELEVANT", "REJECTED_SPAM", "DO_NOT_CONTACT"}:
            # Preserve an explicit operator decision across later AI/rules runs.
            pass
        elif lead.status == "NEW" and result.score >= 70:
            lead.status = "QUALIFIED"
        else:
            lead.status = "REVIEW"
        analysis = LeadIntelligenceAnalysis(
            lead_id=lead.id, run_id=run.id, intent=result.intent, pain=result.pain, need=result.need,
            confidence=result.confidence, score=result.score, matched_signals=result.matched_signals,
            excluded_signals=result.excluded_signals, explanation=result.explanation,
            recommendation=result.recommendation, provider=result.provider, model=result.model,
        )
        db.add(analysis)
        db.flush()
        return analysis

    def run(self, db: Session, *, workspace_id: str, actor_id: str, campaign_id: str | None = None, lead_ids: list[str] | None = None) -> LeadIntelligenceRun:
        settings = get_settings()
        provider = "OPENAI_RESPONSES" if settings.openai_enabled and settings.openai_api_key else "RULES"
        run = LeadIntelligenceRun(workspace_id=workspace_id, campaign_id=campaign_id, provider=provider, model=settings.openai_model if provider.startswith("OPENAI") else "lead-intelligence-rules-v1", status="RUNNING")
        db.add(run)
        db.flush()
        query = select(Lead).where(Lead.workspace_id == workspace_id)
        if campaign_id:
            query = query.where(Lead.campaign_id == campaign_id)
        if lead_ids:
            query = query.where(Lead.id.in_(lead_ids))
        leads = list(db.scalars(query.order_by(Lead.created_at)).all())
        run.total_leads = len(leads)
        for lead in leads:
            self.analyze_lead(db, lead=lead, actor_id=actor_id, run=run)
            run.processed_leads += 1
        run.status, run.completed_at = "SUCCEEDED", datetime.utcnow()
        audit(db, workspace_id=workspace_id, actor_id=actor_id, action="lead_intelligence.run", entity_type="LeadIntelligenceRun", entity_id=run.id, after={"processed": run.processed_leads, "provider": provider})
        db.commit()
        db.refresh(run)
        return run

    def recommend(self, db: Session, *, lead: Lead, actor_id: str) -> MessageRecommendation:
        result = self.analyze_text(lead.raw_text, contact_initiated=lead.contact_initiated)
        recommendation = MessageRecommendation(
            workspace_id=lead.workspace_id, lead_id=lead.id, campaign_id=lead.campaign_id,
            recommendation=result.recommendation, channel=result.recommendation,
            reason=result.recommendation_reason, suggested_content=None,
            facts_snapshot={"intent": result.intent, "pain": result.pain, "need": result.need},
            provider=result.provider, model=result.model, status="DRAFT",
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)
        return recommendation

    def score_community(self, db: Session, *, community: Community) -> CommunityScoreSnapshot:
        rules = 100 if community.rules_text else 35
        activity = min(100, max(0, community.activity_score * 100 if community.activity_score <= 1 else community.activity_score))
        size = min(100, math.log10(max(community.member_count, 1)) * 22)
        leads = db.query(Lead).filter(Lead.source_community_id == community.id).count()
        qualified = db.query(Lead).filter(Lead.source_community_id == community.id, Lead.status == "QUALIFIED").count()
        lead_score = min(100, leads * 12)
        conversion = min(100, (qualified / leads) * 100) if leads else 0
        total = round(activity * 0.2 + size * 0.1 + lead_score * 0.25 + conversion * 0.2 + rules * 0.15 + community.relevance_score * 0.1, 2)
        breakdown = {"activity": activity, "size": size, "leads": lead_score, "conversion": conversion, "rules": rules, "relevance": community.relevance_score}
        community.community_score, community.lead_quality_score, community.conversion_rate = total, round((lead_score + conversion) / 2, 2), round(conversion / 100, 4)
        community.score_breakdown, community.last_scored_at = breakdown, datetime.utcnow()
        snapshot = CommunityScoreSnapshot(community_id=community.id, community_score=total, activity_score=activity, size_score=size, lead_score=lead_score, conversion_score=conversion, rules_score=rules, geography_score=50, topic_score=community.relevance_score, rationale=breakdown)
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot
