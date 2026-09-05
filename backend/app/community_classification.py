from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Community,
    CommunityCollection,
    CommunityCollectionMembership,
    CommunityTag,
    CommunityTagMembership,
    Lead,
    TelegramMessageRecord,
)
from .services import normalize_text

SYSTEM_COLLECTIONS: tuple[tuple[str, str, str | None], ...] = (
    ("Бали", "bali", None),
    ("Красноярск", "krasnoyarsk", None),
    ("Таиланд", "thailand", None),
    ("Digital", "digital", None),
    ("Онлайн-квизы", "online-quizzes", None),
    ("Йога", "yoga", None),
    ("Путешествия", "travel", None),
    ("Бизнес", "business", None),
    ("Остальное", "other", None),
)
BALI_SUBCATEGORIES: tuple[tuple[str, str], ...] = (
    ("Русские", "bali/russian"),
    ("Попутчики", "bali/companions"),
    ("Экспаты", "bali/expats"),
    ("Йога", "bali/yoga"),
    ("Недвижимость", "bali/real-estate"),
    ("Работа", "bali/work"),
    ("Мероприятия", "bali/events"),
    ("Аренда", "bali/rent"),
    ("Автомобили", "bali/cars"),
    ("Дети", "bali/kids"),
    ("Общие", "bali/general"),
    ("Другое", "bali/other"),
)

REGION_TERMS = {
    "Бали": ("bali", "бали", "убуд", "ubud", "чангу", "canggu", "санур", "sanur", "денпасар", "denpasar", "seminyak", "семиньяк"),
    "Красноярск": ("красноярск", "красноярске", "красноярский", "krasnoyarsk"),
    "Таиланд": ("таиланд", "тайланд", "тай", "thailand", "phuket", "пхукет", "бангкок", "bangkok", "самуи", "samui"),
}
CATEGORY_TERMS = {
    "digital": ("digital", "разработ", "сайт", "бот", "crm", "программ", "it", "автоматизац"),
    "online-quizzes": ("квиз", "quiz", "викторин", "игр", "настольн"),
    "yoga": ("йог", "yoga", "медитац", "осознан"),
    "travel": ("путешеств", "travel", "туризм", "поезд", "попутчик", "экскурс", "trip", "виза"),
    "business": ("бизнес", "предприним", "стартап", "инвест", "business", "нетворкинг", "продаж"),
}
TAG_TERMS = {
    "bali": REGION_TERMS["Бали"],
    "krasnoyarsk": REGION_TERMS["Красноярск"],
    "thailand": REGION_TERMS["Таиланд"],
    "travel": CATEGORY_TERMS["travel"],
    "digital": CATEGORY_TERMS["digital"],
    "yoga": CATEGORY_TERMS["yoga"],
    "business": CATEGORY_TERMS["business"],
    "quizzes": CATEGORY_TERMS["online-quizzes"],
    "companions": ("попутчик", "попутчица", "companions", "вместе", "компани"),
    "russian": ("русск", "russian", "россия", "кирилл"),
    "expats": ("expat", "экспат", "эмигрант", "релокац", "relocat"),
    "events": ("мероприят", "ивент", "event", "афиша", "встреч"),
    "nature": ("природ", "nature", "водопад", "пляж", "горы", "mountain"),
}
BALI_SUBCATEGORY_TERMS = {
    "bali/russian": TAG_TERMS["russian"],
    "bali/companions": TAG_TERMS["companions"] + TAG_TERMS["travel"],
    "bali/expats": TAG_TERMS["expats"],
    "bali/yoga": TAG_TERMS["yoga"],
    "bali/real-estate": ("недвиж", "villa", "вилл", "арендодатель", "земл", "real estate"),
    "bali/work": ("работ", "ваканс", "job", "remote", "удален", "фриланс"),
    "bali/events": TAG_TERMS["events"],
    "bali/rent": ("аренд", "rent", "снять", "жилье", "байк", "дом"),
    "bali/cars": ("авто", "машин", "скутер", "байк", "car", "транспорт"),
    "bali/kids": ("дет", "школ", "садик", "ребен", "kids", "family"),
}


@dataclass(frozen=True)
class ClassificationResult:
    region: str
    category: str
    tags: tuple[str, ...]
    collection_slugs: tuple[str, ...]
    confidence: float
    reason: str


def _contains(haystack: str, terms: tuple[str, ...]) -> bool:
    return any(term.casefold() in haystack for term in terms)


def _slug_tag(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.casefold()).strip("-")


class CommunityClassificationEngine:
    """Deterministic, idempotent community classification with manual precedence."""

    def ensure_system_collections(self, db: Session, workspace_id: str) -> dict[str, CommunityCollection]:
        collections: dict[str, CommunityCollection] = {}
        for name, slug, _parent in SYSTEM_COLLECTIONS:
            collection = db.scalar(select(CommunityCollection).where(
                CommunityCollection.workspace_id == workspace_id,
                CommunityCollection.slug == slug,
            ))
            if collection is None:
                collection = CommunityCollection(workspace_id=workspace_id, name=name, slug=slug, is_system=True)
                db.add(collection)
                db.flush()
            collections[slug] = collection
        bali = collections["bali"]
        for name, slug in BALI_SUBCATEGORIES:
            collection = db.scalar(select(CommunityCollection).where(
                CommunityCollection.workspace_id == workspace_id,
                CommunityCollection.slug == slug,
            ))
            if collection is None:
                collection = CommunityCollection(workspace_id=workspace_id, parent_id=bali.id, name=name, slug=slug, is_system=True)
                db.add(collection)
                db.flush()
            collections[slug] = collection
        return collections

    def classify_fields(self, community: Community, messages: list[str]) -> ClassificationResult:
        metadata = " ".join(filter(None, [community.title, community.username, community.description, community.language, community.geography, community.category, community.rules_text]))
        haystack = normalize_text(" ".join([metadata, *messages])).casefold()
        region = next((name for name, terms in REGION_TERMS.items() if _contains(haystack, terms)), "Другое")
        categories = [slug for slug, terms in CATEGORY_TERMS.items() if _contains(haystack, terms)]
        category = categories[0] if categories else "other"
        tags = sorted({tag for tag, terms in TAG_TERMS.items() if _contains(haystack, terms)})
        if region == "Бали" and "bali" not in tags:
            tags.append("bali")
        collections: list[str] = []
        if region == "Бали":
            collections.append("bali")
            subcategory = next((slug for slug, terms in BALI_SUBCATEGORY_TERMS.items() if _contains(haystack, terms)), "bali/general")
            collections.append(subcategory)
        elif region == "Красноярск":
            collections.append("krasnoyarsk")
        elif region == "Таиланд":
            collections.append("thailand")
        for category_slug in categories:
            if category_slug not in collections:
                collections.append(category_slug)
        if not collections:
            collections.append("other")
        matched = len(tags) + len(categories) + (1 if region != "Другое" else 0)
        confidence = round(min(0.99, 0.45 + matched * 0.08), 2)
        reason = f"region={region}; category={category}; tags={','.join(tags) or 'none'}; evidence_messages={len(messages)}"
        return ClassificationResult(region, category, tuple(tags), tuple(dict.fromkeys(collections)), confidence, reason)

    def classify_community(self, db: Session, *, community: Community, actor_id: str | None = None) -> ClassificationResult:
        messages = list(db.scalars(select(TelegramMessageRecord.text).where(
            TelegramMessageRecord.community_id == community.id,
            TelegramMessageRecord.text.is_not(None),
        ).order_by(TelegramMessageRecord.sent_at.desc()).limit(200)).all())
        result = self.classify_fields(community, [text for text in messages if text])
        collections = self.ensure_system_collections(db, community.workspace_id)
        if not community.manual_classification_override:
            community.region = result.region
            community.category = result.category
            community.ai_tags = list(result.tags)
            community.classification_status = "AUTO_CLASSIFIED" if result.confidence >= 0.65 else "NEEDS_REVIEW"
            community.classification_source = "AUTO"
            community.classification_confidence = result.confidence
            community.classification_reason = result.reason
            wanted = set(result.collection_slugs)
            current = list(db.scalars(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)).all())
            for existing_membership in current:
                if existing_membership.assignment_source == "AUTO" and existing_membership.collection_id not in {collections[slug].id for slug in wanted}:
                    db.delete(existing_membership)
            for slug in wanted:
                collection = collections[slug]
                membership: CommunityCollectionMembership | None = db.scalar(select(CommunityCollectionMembership).where(
                    CommunityCollectionMembership.collection_id == collection.id,
                    CommunityCollectionMembership.community_id == community.id,
                ))
                if membership is None:
                    db.add(CommunityCollectionMembership(collection_id=collection.id, community_id=community.id, confidence=result.confidence, reason=result.reason, assigned_by=actor_id))
                elif membership.assignment_source == "AUTO":
                    membership.confidence, membership.reason = result.confidence, result.reason
            for tag_slug in result.tags:
                tag = db.scalar(select(CommunityTag).where(CommunityTag.workspace_id == community.workspace_id, CommunityTag.slug == tag_slug))
                if tag is None:
                    tag = CommunityTag(workspace_id=community.workspace_id, name=tag_slug.replace("-", " ").title(), slug=tag_slug, source="AI")
                    db.add(tag)
                    db.flush()
                if db.scalar(select(CommunityTagMembership).where(CommunityTagMembership.tag_id == tag.id, CommunityTagMembership.community_id == community.id)) is None:
                    db.add(CommunityTagMembership(tag_id=tag.id, community_id=community.id, confidence=result.confidence, assignment_source="AI"))
        elif not db.scalar(select(CommunityCollectionMembership.id).where(CommunityCollectionMembership.community_id == community.id)):
            fallback = collections["other"]
            db.add(CommunityCollectionMembership(collection_id=fallback.id, community_id=community.id, assignment_source="AUTO", confidence=0.5, reason="Manual override has no collection yet", assigned_by=actor_id))
        return result

    def classify_workspace(self, db: Session, *, workspace_id: str, actor_id: str | None = None) -> dict[str, Any]:
        self.ensure_system_collections(db, workspace_id)
        communities = list(db.scalars(select(Community).where(Community.workspace_id == workspace_id).order_by(Community.created_at)).all())
        bali = multi = manual = unresolved = manual_review = 0
        for community in communities:
            result = self.classify_community(db, community=community, actor_id=actor_id)
            db.flush()
            memberships = list(db.scalars(select(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id)).all())
            if result.region == "Бали": bali += 1
            if len(memberships) > 1: multi += 1
            if community.manual_classification_override: manual += 1
            if community.classification_status == "NEEDS_REVIEW": manual_review += 1
            if not memberships: unresolved += 1
        db.commit()
        return {"communities": len(communities), "bali": bali, "automatically_distributed": len(communities) - manual, "manual_override": manual, "requires_manual_review": manual_review, "multiple_collections": multi, "unclassified": unresolved}

    def dashboard(self, db: Session, *, workspace_id: str) -> list[dict[str, Any]]:
        collections = self.ensure_system_collections(db, workspace_id)
        result: list[dict[str, Any]] = []
        for collection in collections.values():
            communities = list(db.scalars(select(Community).join(CommunityCollectionMembership, CommunityCollectionMembership.community_id == Community.id).where(
                CommunityCollectionMembership.collection_id == collection.id,
                Community.workspace_id == workspace_id,
            )).all())
            community_ids = [item.id for item in communities]
            participants = sum(item.member_count or 0 for item in communities)
            leads = db.scalar(select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id, Lead.source_community_id.in_(community_ids))) if community_ids else 0
            campaigns = db.scalar(select(func.count(func.distinct(Lead.campaign_id))).where(Lead.workspace_id == workspace_id, Lead.source_community_id.in_(community_ids), Lead.campaign_id.is_not(None))) if community_ids else 0
            result.append({"id": collection.id, "name": collection.name, "slug": collection.slug, "parent_id": collection.parent_id, "chat_count": len(communities), "member_count": participants, "allowed_publications": sum(item.posting_status in {"APPROVED", "APPROVED_WITH_CONDITIONS"} for item in communities), "lead_count": int(leads or 0), "active_campaign_count": int(campaigns or 0)})
        return result
