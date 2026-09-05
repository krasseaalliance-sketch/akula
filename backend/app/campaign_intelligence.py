from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .lead_intelligence.provider import OpenAIResponsesProvider
from .models import (
    Audience,
    Campaign,
    CampaignAudienceProfile,
    CampaignCommunityScore,
    CampaignCostRecord,
    CampaignIntelligenceRun,
    CampaignLearningSnapshot,
    Community,
    CommunityCollection,
    CommunityCollectionMembership,
    CommunityPermission,
    Conversation,
    DialogTriageDecision,
    Lead,
    MessageDraft,
    Publication,
    TelegramCommunityCandidate,
    TelegramDialog,
)
from .services import normalize_text

logger = logging.getLogger(__name__)


SEGMENT_TERMS: dict[str, tuple[str, ...]] = {
    "travelers": ("travel", "trip", "поезд", "путешествен", "турист", "маршрут", "экскурс"),
    "expats": ("expat", "экспат", "релокац", "эмигрант", "переезд", "relocat"),
    "nature_lovers": ("nature", "природ", "водопад", "горы", "пляж", "джунгл", "nature"),
    "photographers": ("фото", "photograph", "камера", "съемк", "контент", "фотограф"),
    "yoga_wellness": ("йог", "yoga", "медитац", "wellness", "осознан", "ретрит"),
    "digital_nomads": ("digital nomad", "цифровой кочев", "remote", "удален", "фриланс", "стартап", "it"),
    "investors": ("инвест", "инвестици", "доходност", "покупк", "инвестор", "investment"),
    "families": ("семь", "дет", "школ", "садик", "родител", "family", "kids"),
    "entrepreneurs": ("бизнес", "предприним", "компан", "основател", "business", "founder"),
    "astrology_esoterica": ("таро", "эзотер", "астролог", "натал", "самопозн", "психолог", "oracle"),
    "real_estate": ("недвиж", "аренд", "вилл", "квартир", "риэлтор", "real estate", "property"),
    "companions": ("попутчик", "компани", "вместе", "companions", "поход", "встреч"),
}

GOAL_SEGMENTS: dict[str, tuple[str, ...]] = {
    "Найти попутчиков": ("travelers", "companions"),
    "Продать услугу": ("entrepreneurs", "expats"),
    "Пригласить на мероприятие": ("travelers", "events"),
}


@dataclass(frozen=True)
class CampaignProfileDraft:
    audience_segments: tuple[str, ...]
    intent_signals: tuple[str, ...]
    exclusions: tuple[str, ...]
    summary: str
    provider: str
    model: str


def _terms_for_segments(segments: list[str]) -> tuple[str, ...]:
    return tuple(term for segment in segments for term in SEGMENT_TERMS.get(segment, (segment,)))


def _text(value: Any) -> str:
    return normalize_text(str(value or "")).casefold()


class CampaignIntelligenceEngine:
    """Audience-first discovery, scoring, recommendation and learning pipeline."""

    def build_profile(self, *, answers: dict[str, Any], use_llm: bool = True) -> CampaignProfileDraft:
        offer = str(answers.get("offer") or "").strip()
        audience = str(answers.get("audience") or "").strip()
        goal = str(answers.get("goal") or "Получить заявки").strip()
        base = _text(" ".join([offer, audience, str(answers.get("geography") or ""), goal]))
        segments = [segment for segment, terms in SEGMENT_TERMS.items() if any(term.casefold() in base for term in terms)]
        for segment in GOAL_SEGMENTS.get(goal, ()):
            if segment not in segments:
                segments.append(segment)
        if not segments:
            segments = [part for part in re.findall(r"[a-z][a-z_-]{3,}", base)[:6]] or ["general_interest"]
        signals = [item for item in [offer, audience, str(answers.get("geography") or ""), goal] if item]
        exclusions = [str(item).strip() for item in answers.get("exclusions", []) if str(item).strip()]
        provider_name, model = "RULES", "campaign-audience-rules-v1"
        summary = f"Audience for {offer or 'the campaign'}: {', '.join(segments)}; intent: {', '.join(signals)}"
        settings = get_settings()
        if use_llm and settings.openai_enabled and settings.openai_api_key:
            try:
                output = OpenAIResponsesProvider().analyze_audience(answers=answers)
                data = output.data
                segments = list(dict.fromkeys(str(item) for item in data.get("audience_segments", []) if str(item))) or segments
                signals = list(dict.fromkeys(str(item) for item in data.get("intent_signals", []) if str(item))) or signals
                exclusions = list(dict.fromkeys(str(item) for item in data.get("exclusions", []) if str(item))) or exclusions
                summary = str(data.get("summary") or summary)
                provider_name, model = output.provider, output.model
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
                logger.warning("Campaign audience LLM fell back to deterministic profile")
        return CampaignProfileDraft(tuple(segments), tuple(signals), tuple(exclusions), summary, provider_name, model)

    def create_profile(
        self,
        db: Session,
        *,
        campaign: Campaign,
        workspace_id: str,
        answers: dict[str, Any],
        actor_id: str,
        use_llm: bool = True,
    ) -> CampaignAudienceProfile:
        draft = self.build_profile(answers=answers, use_llm=use_llm)
        profile = db.scalar(select(CampaignAudienceProfile).where(CampaignAudienceProfile.campaign_id == campaign.id))
        audience = db.scalar(select(Audience).where(Audience.workspace_id == workspace_id, Audience.name == f"{campaign.name} audience"))
        if audience is None:
            audience = Audience(workspace_id=workspace_id, name=f"{campaign.name} audience", description=draft.summary, criteria={"segments": list(draft.audience_segments), "signals": list(draft.intent_signals)})
            db.add(audience)
            db.flush()
        values = {
            "workspace_id": workspace_id,
            "campaign_id": campaign.id,
            "audience_id": audience.id,
            "offer_summary": str(answers.get("offer") or campaign.name),
            "audience_summary": str(answers.get("audience") or draft.summary),
            "audience_segments": list(draft.audience_segments),
            "intent_signals": list(draft.intent_signals),
            "exclusions": list(draft.exclusions),
            "geographies": [str(item) for item in answers.get("geographies", []) if str(item)] or ([str(answers["geography"])] if answers.get("geography") else []),
            "languages": [str(item) for item in answers.get("languages", []) if str(item)] or [campaign.language],
            "platforms": [str(item) for item in answers.get("platforms", []) if str(item)],
            "goal": str(answers.get("goal") or campaign.objective),
            "budget": float(answers.get("budget") or 0),
            "profile_summary": {"summary": draft.summary, "answers": answers},
            "provider": draft.provider,
            "model": draft.model,
            "status": "READY",
            "created_by": actor_id,
        }
        if profile is None:
            profile = CampaignAudienceProfile(**values)
            db.add(profile)
        else:
            for key, value in values.items():
                if key not in {"campaign_id", "created_by"}:
                    setattr(profile, key, value)
            profile.version += 1
        db.flush()
        return profile

    def _community_text(self, db: Session, community: Community) -> str:
        recent = list(db.scalars(select(CommunityCollection.name).join(CommunityCollectionMembership, CommunityCollectionMembership.collection_id == CommunityCollection.id).where(CommunityCollectionMembership.community_id == community.id).limit(30)).all())
        return _text(" ".join(filter(None, [community.title, community.username, community.description, community.language, community.geography, community.category, community.rules_text, *(community.ai_tags or []), *recent])))

    def _collection_slugs(self, db: Session, community_id: str) -> list[str]:
        return list(db.scalars(select(CommunityCollection.slug).join(CommunityCollectionMembership, CommunityCollectionMembership.collection_id == CommunityCollection.id).where(CommunityCollectionMembership.community_id == community_id)).all())

    def _eligible_community_ids(self, db: Session, workspace_id: str) -> list[str]:
        has_telegram_dialog = exists(
            select(TelegramDialog.id).where(
                TelegramDialog.community_id == Community.id,
                TelegramDialog.workspace_id == workspace_id,
            )
        )
        has_manual_approval = exists(
            select(DialogTriageDecision.id)
            .join(TelegramDialog, TelegramDialog.id == DialogTriageDecision.telegram_dialog_id)
            .where(
                TelegramDialog.community_id == Community.id,
                TelegramDialog.workspace_id == workspace_id,
                DialogTriageDecision.workspace_id == workspace_id,
                DialogTriageDecision.review_status == "REVIEWED",
                DialogTriageDecision.manual_eligibility.in_(("ELIGIBLE", "READ_ONLY")),
            )
        )
        return list(
            db.scalars(
                select(Community.id).where(
                    Community.workspace_id == workspace_id,
                    or_(~has_telegram_dialog, has_manual_approval),
                )
            ).all()
        )

    def _score_community(self, db: Session, *, community: Community, profile: CampaignAudienceProfile) -> dict[str, Any]:
        text = self._community_text(db, community)
        segments = list(profile.audience_segments or [])
        terms = _terms_for_segments(segments)
        matched_segments = [segment for segment in segments if any(term.casefold() in text for term in SEGMENT_TERMS.get(segment, (segment,)))]
        relevance = min(100, max(0, (community.relevance_score * 100 if community.relevance_score <= 1 else community.relevance_score) + len(matched_segments) * 6))
        audience_match = min(100, len(matched_segments) * 22 + (15 if any(term.casefold() in text for term in terms) else 0))
        activity = min(100, max(0, community.activity_score * 100 if community.activity_score <= 1 else community.activity_score))
        permission = db.scalar(select(CommunityPermission.id).where(CommunityPermission.community_id == community.id, CommunityPermission.status == "ACTIVE"))
        posting = 100 if permission else 88 if community.posting_status in {"APPROVED", "APPROVED_WITH_CONDITIONS"} else 35 if community.posting_status == "NEEDS_REVIEW" else 10
        commercial_risk = 78 if community.posting_status == "REJECTED" else 52 if community.posting_status == "NEEDS_REVIEW" else 18
        spam_risk = min(100, 20 + (25 if any(word in text for word in ("реклама", "advert", "promo", "продам", "sale")) else 0) + (20 if community.member_count == 0 else 0))
        lead_count = int(db.scalar(select(func.count(Lead.id)).where(Lead.source_community_id == community.id)) or 0)
        expected_response = min(100, 20 + lead_count * 18 + audience_match * 0.35 + activity * 0.2)
        total = round(relevance * 0.2 + audience_match * 0.2 + activity * 0.12 + posting * 0.15 + (100 - commercial_risk) * 0.1 + (100 - spam_risk) * 0.08 + expected_response * 0.15, 2)
        lead_probability = round(min(100, max(0, total * 0.62 + lead_count * 4)), 2)
        if total >= 70 and posting >= 80 and spam_risk < 65:
            recommendation = "PUBLISH"
            reason = "Strong audience match and activity with an acceptable publishing boundary; operator approval is still required."
        elif total >= 45:
            recommendation = "REVIEW"
            reason = "Audience signal exists, but permission or commercial/spam risk needs operator review."
        else:
            recommendation = "DO_NOT_PUBLISH"
            reason = "Weak audience match or high operational risk for this campaign."
        return {"relevance": round(relevance, 2), "audience_match": round(audience_match, 2), "activity": activity, "posting": posting, "commercial_risk": commercial_risk, "spam_risk": spam_risk, "expected_response": round(expected_response, 2), "total": total, "lead_probability": lead_probability, "recommendation": recommendation, "reason": reason, "matched_segments": matched_segments, "collection_slugs": self._collection_slugs(db, community.id)}

    def analyze(self, db: Session, *, campaign: Campaign, workspace_id: str, actor_id: str, use_llm: bool = True) -> dict[str, Any]:
        profile = db.scalar(select(CampaignAudienceProfile).where(CampaignAudienceProfile.campaign_id == campaign.id))
        if profile is None:
            profile = self.create_profile(db, campaign=campaign, workspace_id=workspace_id, answers={"offer": campaign.name, "audience": campaign.objective, "geography": campaign.geography, "languages": [campaign.language], "goal": campaign.objective}, actor_id=actor_id, use_llm=use_llm)
        eligible_community_ids = self._eligible_community_ids(db, workspace_id)
        communities = list(db.scalars(select(Community).where(Community.id.in_(eligible_community_ids))).all())
        candidate_count = int(db.scalar(select(func.count(TelegramCommunityCandidate.id)).where(TelegramCommunityCandidate.workspace_id == workspace_id)) or 0)
        run = CampaignIntelligenceRun(workspace_id=workspace_id, campaign_id=campaign.id, audience_profile_id=profile.id, provider=profile.provider, model=profile.model, status="RUNNING", discovered_communities=len(communities) + candidate_count, created_by=actor_id)
        db.add(run)
        db.flush()
        rows: list[CampaignCommunityScore] = []
        for community in communities:
            scored = self._score_community(db, community=community, profile=profile)
            row = db.scalar(select(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == campaign.id, CampaignCommunityScore.community_id == community.id))
            if row is None:
                row = CampaignCommunityScore(workspace_id=workspace_id, campaign_id=campaign.id, community_id=community.id)
                db.add(row)
            row.run_id = run.id
            row.relevance_score = scored["relevance"]
            row.audience_match_score = scored["audience_match"]
            row.activity_score = scored["activity"]
            row.posting_permission_score = scored["posting"]
            row.commercial_risk_score = scored["commercial_risk"]
            row.spam_risk_score = scored["spam_risk"]
            row.expected_response_score = scored["expected_response"]
            row.community_score = scored["total"]
            row.lead_probability = scored["lead_probability"]
            row.recommendation = scored["recommendation"]
            row.recommendation_reason = scored["reason"]
            row.score_breakdown = {**scored, "matched_segments": scored["matched_segments"]}
            row.collection_slugs = scored["collection_slugs"]
            row.provider, row.model, row.status = profile.provider, profile.model, "ANALYZED"
            rows.append(row)
        db.flush()
        rows.sort(key=lambda item: (-item.community_score, item.community_id))
        for index, row in enumerate(rows, start=1):
            row.rank = index
        recommended = [row for row in rows if row.recommendation in {"PUBLISH", "REVIEW"}][:15]
        run.analyzed_communities = len(rows)
        run.recommended_communities = len(recommended)
        run.average_score = round(sum(row.community_score for row in rows) / len(rows), 2) if rows else 0
        projected_reach = 0
        for row in recommended:
            projected_community = db.get(Community, row.community_id)
            if projected_community is not None:
                projected_reach += int((projected_community.member_count or 0) * row.lead_probability / 100)
        run.projected_reach = projected_reach
        run.ai_cost = 0.01 if profile.provider.startswith("OPENAI") else 0
        run.status, run.completed_at = "SUCCEEDED", datetime.utcnow()
        db.add(CampaignCostRecord(workspace_id=workspace_id, campaign_id=campaign.id, run_id=run.id, cost_type="ANALYSIS", amount=run.ai_cost, currency="USD", quantity=1, metadata_json={"provider": profile.provider, "communities": len(rows)}))
        db.commit()
        return self.dashboard(db, campaign=campaign, workspace_id=workspace_id)

    def learn(self, db: Session, *, campaign: Campaign, workspace_id: str, actor_id: str) -> CampaignLearningSnapshot:
        leads = list(db.scalars(select(Lead).where(Lead.campaign_id == campaign.id, Lead.workspace_id == workspace_id)).all())
        conversations = int(db.scalar(select(func.count(Conversation.id)).where(Conversation.campaign_id == campaign.id)) or 0)
        publications = list(db.scalars(select(Publication).where(Publication.campaign_id == campaign.id)).all())
        converted = [lead for lead in leads if lead.status == "CONVERTED"]
        qualified = [lead for lead in leads if lead.status in {"QUALIFIED", "CONVERTED"}]
        best = Counter(lead.source_community_id for lead in qualified if lead.source_community_id).most_common(1)
        best_community_id = best[0][0] if best else None
        snapshot = CampaignLearningSnapshot(workspace_id=workspace_id, campaign_id=campaign.id, analyzed_leads=len(leads), responses=conversations, qualified_leads=len(qualified), converted_leads=len(converted), publications=len(publications), successful_publications=sum(item.status in {"SENT", "DRY_RUN"} for item in publications), best_community_id=best_community_id, learning_summary={"top_community": best_community_id, "qualified_rate": round(len(qualified) / len(leads), 4) if leads else 0, "converted_rate": round(len(converted) / len(leads), 4) if leads else 0}, created_by=actor_id)
        db.add(snapshot)
        db.commit()
        return snapshot

    def dashboard(self, db: Session, *, campaign: Campaign, workspace_id: str) -> dict[str, Any]:
        profile = db.scalar(select(CampaignAudienceProfile).where(CampaignAudienceProfile.campaign_id == campaign.id))
        eligible_community_ids = self._eligible_community_ids(db, workspace_id)
        scores = list(db.scalars(select(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == campaign.id, CampaignCommunityScore.community_id.in_(eligible_community_ids)).order_by(CampaignCommunityScore.rank, CampaignCommunityScore.community_score.desc())).all())
        latest_run = db.scalar(select(CampaignIntelligenceRun).where(CampaignIntelligenceRun.campaign_id == campaign.id).order_by(CampaignIntelligenceRun.created_at.desc()))
        total_cost = float(db.scalar(select(func.sum(CampaignCostRecord.amount)).where(CampaignCostRecord.campaign_id == campaign.id)) or 0)
        leads = int(db.scalar(select(func.count(Lead.id)).where(Lead.campaign_id == campaign.id)) or 0)
        publications = int(db.scalar(select(func.count(Publication.id)).where(Publication.campaign_id == campaign.id)) or 0)
        successful = int(db.scalar(select(func.count(Lead.id)).where(Lead.campaign_id == campaign.id, Lead.status == "CONVERTED")) or 0)
        collection_counts: Counter[str] = Counter(slug for row in scores for slug in (row.collection_slugs or []))
        top = []
        for row in scores[:15]:
            community = db.get(Community, row.community_id)
            if community:
                top.append({"id": community.id, "title": community.title, "score": row.community_score, "lead_probability": row.lead_probability, "recommendation": row.recommendation, "reason": row.recommendation_reason, "collections": row.collection_slugs or []})
        return {"campaign": {"id": campaign.id, "name": campaign.name, "objective": campaign.objective, "status": campaign.status}, "audience": {"summary": profile.audience_summary if profile else None, "segments": profile.audience_segments if profile else [], "goal": profile.goal if profile else campaign.objective}, "communities_found": latest_run.discovered_communities if latest_run else 0, "communities_analyzed": len(scores), "average_score": latest_run.average_score if latest_run else 0, "top_communities": top, "prepared_messages": int(db.scalar(select(func.count(MessageDraft.id)).where(MessageDraft.campaign_id == campaign.id)) or 0), "ai_cost": round(total_cost, 4), "projected_reach": latest_run.projected_reach if latest_run else 0, "collection_distribution": dict(collection_counts), "economics": {"analysis_cost": round(total_cost, 4), "cost_per_lead": round(total_cost / leads, 4) if leads else 0, "cost_per_publication": round(total_cost / publications, 4) if publications else 0, "cost_per_successful_application": round(total_cost / successful, 4) if successful else 0}, "learning": {"leads": leads, "responses": int(db.scalar(select(func.count(Conversation.id)).where(Conversation.campaign_id == campaign.id)) or 0), "converted": successful}}
