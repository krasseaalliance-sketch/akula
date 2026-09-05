from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from math import ceil
from typing import Any

from sqlalchemy import asc, case, delete, desc, func, select
from sqlalchemy.orm import Session

from .models import (
    Community,
    CommunityCollection,
    CommunityCollectionMembership,
    CommunityTag,
    CommunityTagMembership,
    DialogTriageCollection,
    DialogTriageCollectionMembership,
    DialogTriageDecision,
    DialogTriageTag,
    DialogTriageTagMembership,
    TelegramAccountProfile,
    TelegramDialog,
    TelegramMessageRecord,
)
from .services import audit, normalize_text

SYSTEM_COLLECTIONS = (
    ("Бали", "bali"),
    ("Красноярск", "krasnoyarsk"),
    ("Грузия", "georgia"),
    ("Таиланд", "thailand"),
    ("Путешествия", "travel"),
    ("Попутчики", "companions"),
    ("Недвижимость", "real-estate"),
    ("Йога", "yoga"),
    ("Таро и эзотерика", "tarot-esoterica"),
    ("Онлайн-квизы", "online-quizzes"),
    ("Digital", "digital"),
    ("Бизнес", "business"),
    ("Работа", "work"),
    ("Экспаты", "expats"),
    ("Релокация", "relocation"),
    ("Личное", "personal"),
    ("Боты", "bots"),
    ("Каналы", "channels"),
    ("Архив", "archive"),
    ("Другое", "other"),
)

TRIAGE_STATUSES = {
    "UNREVIEWED",
    "IN_REVIEW",
    "REVIEWED",
    "SKIPPED",
    "NEEDS_CONTEXT",
    "ARCHIVED_FROM_TRIAGE",
}
TRIAGE_TYPES = {
    "PERSON",
    "GROUP",
    "SUPERGROUP",
    "CHANNEL",
    "BOT",
    "SAVED_MESSAGES",
    "SERVICE",
    "UNKNOWN",
}
ELIGIBILITIES = {"ELIGIBLE", "READ_ONLY", "NOT_ELIGIBLE", "MANUAL_REVIEW"}
GROUP_TYPES = {"GROUP", "SUPERGROUP", "CHANNEL"}


def slugify(value: str) -> str:
    normalized = normalize_text(value).casefold()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-")
    return slug[:180] or "collection"


def mapped_dialog_type(dialog_type: str) -> str:
    return {
        "USER": "PERSON",
        "PRIVATE": "PERSON",
        "BOT": "BOT",
        "GROUP": "GROUP",
        "SUPERGROUP": "SUPERGROUP",
        "CHANNEL": "CHANNEL",
        "SAVED_MESSAGES": "SAVED_MESSAGES",
        "SERVICE": "SERVICE",
    }.get(dialog_type, "UNKNOWN")


class TriageConflict(ValueError):
    pass


class DialogTriageService:
    def ensure_system_collections(self, db: Session, workspace_id: str) -> None:
        existing = set(
            db.scalars(
                select(DialogTriageCollection.slug).where(DialogTriageCollection.workspace_id == workspace_id)
            ).all()
        )
        for name, slug in SYSTEM_COLLECTIONS:
            if slug not in existing:
                db.add(DialogTriageCollection(workspace_id=workspace_id, name=name, slug=slug, is_system=True))
        db.flush()

    def account(self, db: Session, *, workspace_id: str, account_id: str | None) -> TelegramAccountProfile:
        query = select(TelegramAccountProfile).where(TelegramAccountProfile.workspace_id == workspace_id)
        if account_id:
            query = query.where(TelegramAccountProfile.id == account_id)
        profile = db.scalar(query.order_by(desc(TelegramAccountProfile.created_at)))
        if profile is None:
            raise ValueError("Telegram account not found in workspace")
        return profile

    def _dialog_query(self, db: Session, *, workspace_id: str, account: TelegramAccountProfile):
        latest_message = func.max(TelegramMessageRecord.sent_at).label("latest_message_at")
        entity_priority = case(
            (TelegramDialog.dialog_type.in_(("GROUP", "SUPERGROUP", "CHANNEL")), 0),
            (TelegramDialog.dialog_type == "UNKNOWN", 1),
            else_=2,
        )
        reviewed_ids = select(DialogTriageDecision.telegram_dialog_id).where(
            DialogTriageDecision.workspace_id == workspace_id,
            DialogTriageDecision.telegram_account_id == account.id,
            DialogTriageDecision.review_status != "UNREVIEWED",
        )
        return (
            select(TelegramDialog, latest_message)
            .outerjoin(
                TelegramMessageRecord,
                (TelegramMessageRecord.external_dialog_id == TelegramDialog.external_dialog_id)
                & (TelegramMessageRecord.integration_account_id == TelegramDialog.integration_account_id),
            )
            .where(
                TelegramDialog.workspace_id == workspace_id,
                TelegramDialog.integration_account_id == account.integration_account_id,
                ~TelegramDialog.id.in_(reviewed_ids),
            )
            .group_by(TelegramDialog.id)
            .order_by(entity_priority, desc(latest_message).nullslast(), asc(TelegramDialog.external_dialog_id))
        )

    def _collections(self, db: Session, decision_id: str) -> list[str]:
        return list(
            db.scalars(
                select(DialogTriageCollection.slug)
                .join(DialogTriageCollectionMembership, DialogTriageCollectionMembership.collection_id == DialogTriageCollection.id)
                .where(DialogTriageCollectionMembership.decision_id == decision_id)
                .order_by(DialogTriageCollection.slug)
            ).all()
        )

    def _tags(self, db: Session, decision_id: str) -> list[str]:
        return list(
            db.scalars(
                select(DialogTriageTag.slug)
                .join(DialogTriageTagMembership, DialogTriageTagMembership.tag_id == DialogTriageTag.id)
                .where(DialogTriageTagMembership.decision_id == decision_id)
                .order_by(DialogTriageTag.slug)
            ).all()
        )

    def _decision(self, db: Session, *, workspace_id: str, account_id: str, dialog_id: str) -> DialogTriageDecision | None:
        return db.scalar(
            select(DialogTriageDecision).where(
                DialogTriageDecision.workspace_id == workspace_id,
                DialogTriageDecision.telegram_account_id == account_id,
                DialogTriageDecision.telegram_dialog_id == dialog_id,
            )
        )

    def _message_preview(self, db: Session, dialog: TelegramDialog) -> list[dict[str, Any]]:
        if not dialog.can_view_history:
            return []
        messages = list(
            db.scalars(
                select(TelegramMessageRecord)
                .where(
                    TelegramMessageRecord.integration_account_id == dialog.integration_account_id,
                    TelegramMessageRecord.external_dialog_id == dialog.external_dialog_id,
                    TelegramMessageRecord.text.is_not(None),
                )
                .order_by(desc(TelegramMessageRecord.sent_at))
                .limit(3)
            ).all()
        )
        return [
            {"text": (item.text or "")[:240], "sent_at": item.sent_at.isoformat(), "sender": item.sender_display_name or item.sender_username}
            for item in messages
        ]

    def _suggestion(self, db: Session, dialog: TelegramDialog) -> dict[str, Any]:
        suggested_type = mapped_dialog_type(dialog.dialog_type)
        confidence = 0.95 if suggested_type != "UNKNOWN" else 0.25
        collections: list[str] = []
        tags: list[str] = []
        if dialog.community_id:
            collections = list(
                db.scalars(
                    select(CommunityCollection.slug)
                    .join(CommunityCollectionMembership, CommunityCollectionMembership.collection_id == CommunityCollection.id)
                    .where(CommunityCollectionMembership.community_id == dialog.community_id)
                ).all()
            )
            tags = list(
                db.scalars(
                    select(CommunityTag.slug)
                    .join(CommunityTagMembership, CommunityTagMembership.tag_id == CommunityTag.id)
                    .where(CommunityTagMembership.community_id == dialog.community_id)
                ).all()
            )
        return {"type": suggested_type, "confidence": confidence, "collection_slugs": collections, "tag_slugs": tags}

    def card(self, db: Session, *, dialog: TelegramDialog, account_id: str, latest_message_at: datetime | None = None) -> dict[str, Any]:
        decision = self._decision(db, workspace_id=dialog.workspace_id, account_id=account_id, dialog_id=dialog.id)
        suggestion = self._suggestion(db, dialog)
        raw_avatar = (dialog.raw_metadata_sanitized or {}).get("avatar_url")
        avatar_url = raw_avatar if isinstance(raw_avatar, str) and raw_avatar.startswith(("https://", "http://")) else None
        return {
            "id": dialog.id,
            "number": None,
            "title": dialog.title,
            "username": dialog.username,
            "entity_type": dialog.dialog_type,
            "manual_dialog_type": decision.manual_dialog_type if decision else None,
            "avatar_url": avatar_url,
            "member_count": dialog.member_count,
            "last_message_at": latest_message_at.isoformat() if latest_message_at else dialog.last_synced_at.isoformat() if dialog.last_synced_at else None,
            "message_preview": self._message_preview(db, dialog),
            "current_automatic_tags": list(dialog.raw_metadata_sanitized.get("ai_tags", [])) if dialog.raw_metadata_sanitized else [],
            "current_automatic_collections": suggestion["collection_slugs"],
            "suggestion": suggestion,
            "decision": {
                "review_status": decision.review_status if decision else "UNREVIEWED",
                "manual_dialog_type": decision.manual_dialog_type if decision else "UNKNOWN",
                "manual_eligibility": decision.manual_eligibility if decision else "MANUAL_REVIEW",
                "operator_notes": decision.operator_notes if decision else None,
                "needs_context_reason": decision.needs_context_reason if decision else None,
                "version": decision.version if decision else 0,
                "manual_override": decision.manual_override if decision else False,
                "collection_slugs": self._collections(db, decision.id) if decision else [],
                "tag_slugs": self._tags(db, decision.id) if decision else [],
            },
        }

    def _sync_community_taxonomy(self, db: Session, *, community: Community, decision: DialogTriageDecision, actor_id: str) -> None:
        """Apply the operator's decision to the linked Community Dataset row."""
        from .community_classification import CommunityClassificationEngine

        definitions = CommunityClassificationEngine().ensure_system_collections(db, community.workspace_id)
        db.execute(delete(CommunityCollectionMembership).where(CommunityCollectionMembership.community_id == community.id))
        selected_collections = []
        for slug in self._collections(db, decision.id):
            collection = definitions.get(slug)
            if collection is None:
                collection = db.scalar(select(CommunityCollection).where(CommunityCollection.workspace_id == community.workspace_id, CommunityCollection.slug == slug))
            if collection is None:
                collection = CommunityCollection(workspace_id=community.workspace_id, name=slug.replace("-", " ").title(), slug=slug, kind="MANUAL", is_system=False)
                db.add(collection)
                db.flush()
            selected_collections.append(slug)
            db.add(CommunityCollectionMembership(collection_id=collection.id, community_id=community.id, assignment_source="MANUAL", confidence=1.0, reason="Interactive operator review", assigned_by=actor_id))

        db.execute(delete(CommunityTagMembership).where(CommunityTagMembership.community_id == community.id))
        selected_tags = self._tags(db, decision.id)
        for slug in selected_tags:
            tag = db.scalar(select(CommunityTag).where(CommunityTag.workspace_id == community.workspace_id, CommunityTag.slug == slug))
            if tag is None:
                tag = CommunityTag(workspace_id=community.workspace_id, name=slug.replace("-", " ").title(), slug=slug, source="MANUAL")
                db.add(tag)
                db.flush()
            db.add(CommunityTagMembership(tag_id=tag.id, community_id=community.id, assignment_source="MANUAL", confidence=1.0))

        region_by_collection = {"bali": "Бали", "krasnoyarsk": "Красноярск", "georgia": "Грузия", "thailand": "Таиланд"}
        community.region = next((region_by_collection[slug] for slug in selected_collections if slug in region_by_collection), community.region)
        community.category = selected_collections[0] if selected_collections else community.category
        community.ai_tags = selected_tags
        community.classification_status = "MANUAL_OVERRIDE"
        community.classification_source = "MANUAL"
        community.manual_classification_override = True
        community.classification_confidence = 1.0
        community.classification_reason = "Interactive operator review"
        db.flush()

    def _refresh_campaign_scores(self, db: Session, *, workspace_id: str, community_ids: set[str]) -> int:
        """Re-score only affected communities for existing campaign profiles."""
        if not community_ids:
            return 0
        from .campaign_intelligence import CampaignIntelligenceEngine
        from .models import CampaignAudienceProfile, CampaignCommunityScore, CampaignIntelligenceRun

        engine = CampaignIntelligenceEngine()
        eligible_ids = set(engine._eligible_community_ids(db, workspace_id))
        profiles = list(db.scalars(select(CampaignAudienceProfile).where(CampaignAudienceProfile.workspace_id == workspace_id)).all())
        refreshed = 0
        for profile in profiles:
            latest_run = db.scalar(select(CampaignIntelligenceRun).where(CampaignIntelligenceRun.campaign_id == profile.campaign_id).order_by(CampaignIntelligenceRun.created_at.desc()))
            for community_id in sorted(community_ids & eligible_ids):
                community = db.get(Community, community_id)
                if community is None:
                    continue
                scored = engine._score_community(db, community=community, profile=profile)
                row = db.scalar(select(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == profile.campaign_id, CampaignCommunityScore.community_id == community_id))
                if row is None:
                    row = CampaignCommunityScore(workspace_id=workspace_id, campaign_id=profile.campaign_id, community_id=community_id)
                    db.add(row)
                row.run_id = latest_run.id if latest_run else None
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
                row.status = "ANALYZED"
                refreshed += 1
            rows = list(db.scalars(select(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == profile.campaign_id).order_by(desc(CampaignCommunityScore.community_score), asc(CampaignCommunityScore.community_id))).all())
            for rank, row in enumerate(rows, start=1):
                row.rank = rank
        db.flush()
        return refreshed

    def refresh_downstream(self, db: Session, *, workspace_id: str, account_id: str, decisions: list[DialogTriageDecision], actor_id: str) -> dict[str, int]:
        community_ids: set[str] = set()
        for decision in decisions:
            if decision.review_status != "REVIEWED":
                continue
            dialog = db.get(TelegramDialog, decision.telegram_dialog_id)
            if dialog is None or not dialog.community_id:
                continue
            community = db.get(Community, dialog.community_id)
            if community is None:
                continue
            self._sync_community_taxonomy(db, community=community, decision=decision, actor_id=actor_id)
            community_ids.add(community.id)
        scores = self._refresh_campaign_scores(db, workspace_id=workspace_id, community_ids=community_ids)
        return {"communities_updated": len(community_ids), "campaign_scores_refreshed": scores}

    def completion_summary(self, db: Session, *, workspace_id: str, account_id: str | None) -> dict[str, Any]:
        account = self.account(db, workspace_id=workspace_id, account_id=account_id)
        total = int(db.scalar(select(func.count(TelegramDialog.id)).where(TelegramDialog.workspace_id == workspace_id, TelegramDialog.integration_account_id == account.integration_account_id)) or 0)
        counts = {str(kind): int(count) for kind, count in db.execute(select(DialogTriageDecision.manual_dialog_type, func.count(DialogTriageDecision.id)).where(DialogTriageDecision.workspace_id == workspace_id, DialogTriageDecision.telegram_account_id == account.id, DialogTriageDecision.review_status != "UNREVIEWED").group_by(DialogTriageDecision.manual_dialog_type)).all()}
        processed = sum(counts.values())
        community_dataset = int(db.scalar(select(func.count(func.distinct(TelegramDialog.community_id))).join(DialogTriageDecision, DialogTriageDecision.telegram_dialog_id == TelegramDialog.id).where(TelegramDialog.workspace_id == workspace_id, TelegramDialog.integration_account_id == account.integration_account_id, TelegramDialog.community_id.is_not(None), DialogTriageDecision.telegram_account_id == account.id, DialogTriageDecision.review_status == "REVIEWED", DialogTriageDecision.manual_eligibility.in_(("ELIGIBLE", "READ_ONLY")))) or 0)
        return {"complete": processed >= total, "total_dialogs": total, "processed_dialogs": processed, "remaining": max(0, total - processed), "community_dataset": community_dataset, "personal": counts.get("PERSON", 0), "bots": counts.get("BOT", 0), "channels": counts.get("CHANNEL", 0), "groups": counts.get("GROUP", 0) + counts.get("SUPERGROUP", 0), "service": counts.get("SERVICE", 0), "unknown": counts.get("UNKNOWN", 0)}

    def next_batch(self, db: Session, *, workspace_id: str, account_id: str | None, limit: int) -> dict[str, Any]:
        self.ensure_system_collections(db, workspace_id)
        account = self.account(db, workspace_id=workspace_id, account_id=account_id)
        rows = list(db.execute(self._dialog_query(db, workspace_id=workspace_id, account=account).limit(limit)).all())
        cards = [self.card(db, dialog=dialog, account_id=account.id, latest_message_at=latest) for dialog, latest in rows]
        for index, card in enumerate(cards, start=1):
            card["number"] = index
        result = {"account": {"id": account.id, "display_name": account.first_name or account.username or "Telegram account"}, "batch_size": limit, "dialogs": cards, "progress": self.progress(db, workspace_id=workspace_id, account_id=account.id, batch_size=limit)}
        if not cards:
            result["completion"] = self.completion_summary(db, workspace_id=workspace_id, account_id=account.id)
        return result

    def progress(self, db: Session, *, workspace_id: str, account_id: str | None, batch_size: int = 30) -> dict[str, Any]:
        account = self.account(db, workspace_id=workspace_id, account_id=account_id)
        total = int(
            db.scalar(
                select(func.count(TelegramDialog.id)).where(
                    TelegramDialog.workspace_id == workspace_id,
                    TelegramDialog.integration_account_id == account.integration_account_id,
                )
            )
            or 0
        )
        counts: dict[str, int] = {
            status: int(count)
            for status, count in db.execute(
                select(DialogTriageDecision.review_status, func.count(DialogTriageDecision.id))
                .where(DialogTriageDecision.workspace_id == workspace_id, DialogTriageDecision.telegram_account_id == account.id)
                .group_by(DialogTriageDecision.review_status)
            ).all()
        }
        reviewed = counts.get("REVIEWED", 0) + counts.get("ARCHIVED_FROM_TRIAGE", 0)
        skipped = counts.get("SKIPPED", 0)
        needs_context = counts.get("NEEDS_CONTEXT", 0)
        in_review = counts.get("IN_REVIEW", 0)
        remaining = max(0, total - sum(counts.values()))
        return {"total": total, "reviewed": reviewed, "remaining": remaining, "skipped": skipped, "needs_context": needs_context, "in_review": in_review, "batches_remaining": ceil(remaining / batch_size) if remaining else 0, "batch_size": batch_size}

    def reviewed(self, db: Session, *, workspace_id: str, account_id: str | None, limit: int = 100) -> list[dict[str, Any]]:
        account = self.account(db, workspace_id=workspace_id, account_id=account_id)
        rows = list(
            db.scalars(
                select(DialogTriageDecision)
                .where(DialogTriageDecision.workspace_id == workspace_id, DialogTriageDecision.telegram_account_id == account.id, DialogTriageDecision.review_status != "UNREVIEWED")
                .order_by(desc(DialogTriageDecision.reviewed_at), desc(DialogTriageDecision.updated_at))
                .limit(limit)
            ).all()
        )
        return [self.decision_payload(db, decision) for decision in rows]

    def decision_payload(self, db: Session, decision: DialogTriageDecision) -> dict[str, Any]:
        dialog = db.get(TelegramDialog, decision.telegram_dialog_id)
        return {"id": decision.id, "dialog_id": decision.telegram_dialog_id, "title": dialog.title if dialog else "Unknown dialog", "review_status": decision.review_status, "manual_dialog_type": decision.manual_dialog_type, "manual_eligibility": decision.manual_eligibility, "operator_notes": decision.operator_notes, "needs_context_reason": decision.needs_context_reason, "version": decision.version, "manual_override": decision.manual_override, "collection_slugs": self._collections(db, decision.id), "tag_slugs": self._tags(db, decision.id), "reviewed_at": decision.reviewed_at.isoformat() if decision.reviewed_at else None, "updated_at": decision.updated_at.isoformat() if decision.updated_at else None}

    def _replace_memberships(self, db: Session, *, decision: DialogTriageDecision, workspace_id: str, actor_id: str, collection_slugs: Iterable[str] | None, tag_slugs: Iterable[str] | None) -> None:
        if collection_slugs is not None:
            slugs = list(dict.fromkeys(collection_slugs))
            collections = list(db.scalars(select(DialogTriageCollection).where(DialogTriageCollection.workspace_id == workspace_id, DialogTriageCollection.slug.in_(slugs))).all()) if slugs else []
            if len(collections) != len(slugs):
                raise ValueError("Unknown triage collection")
            db.execute(delete(DialogTriageCollectionMembership).where(DialogTriageCollectionMembership.decision_id == decision.id))
            db.add_all([DialogTriageCollectionMembership(decision_id=decision.id, collection_id=item.id, assigned_by=actor_id) for item in collections])
        if tag_slugs is not None:
            slugs = list(dict.fromkeys(tag_slugs))
            tags = []
            for slug in slugs:
                tag = db.scalar(select(DialogTriageTag).where(DialogTriageTag.workspace_id == workspace_id, DialogTriageTag.slug == slug))
                if tag is None:
                    tag = DialogTriageTag(workspace_id=workspace_id, name=slug.replace("-", " ").title(), slug=slug)
                    db.add(tag)
                    db.flush()
                tags.append(tag)
            db.execute(delete(DialogTriageTagMembership).where(DialogTriageTagMembership.decision_id == decision.id))
            db.add_all([DialogTriageTagMembership(decision_id=decision.id, tag_id=item.id, assigned_by=actor_id) for item in tags])

    def save_one(self, db: Session, *, workspace_id: str, account_id: str, dialog: TelegramDialog, actor_id: str, payload: dict[str, Any], allow_existing: bool = False) -> DialogTriageDecision:
        status = payload.get("review_status", "REVIEWED")
        dialog_type = payload.get("manual_dialog_type", "UNKNOWN")
        eligibility = payload.get("manual_eligibility", "MANUAL_REVIEW")
        if status not in TRIAGE_STATUSES or dialog_type not in TRIAGE_TYPES or eligibility not in ELIGIBILITIES:
            raise ValueError("Invalid triage decision values")
        if status == "REVIEWED" and dialog_type in GROUP_TYPES and eligibility not in ELIGIBILITIES:
            raise ValueError("Eligibility is required for communities and channels")
        if status == "NEEDS_CONTEXT" and not payload.get("needs_context_reason"):
            raise ValueError("needs_context_reason is required")
        decision = self._decision(db, workspace_id=workspace_id, account_id=account_id, dialog_id=dialog.id)
        if decision is not None:
            expected = payload.get("expected_version")
            if expected is not None and expected != decision.version:
                raise TriageConflict("TRIAGE_VERSION_CONFLICT")
            if not allow_existing and decision.review_status != "UNREVIEWED":
                raise TriageConflict("TRIAGE_ALREADY_REVIEWED")
            before = self.decision_payload(db, decision)
            decision.version += 1
        else:
            before = None
            decision = DialogTriageDecision(workspace_id=workspace_id, telegram_account_id=account_id, telegram_dialog_id=dialog.id)
            db.add(decision)
            db.flush()
        decision.review_status = status
        decision.manual_dialog_type = dialog_type
        decision.manual_eligibility = eligibility
        decision.operator_notes = payload.get("operator_notes")
        decision.needs_context_reason = payload.get("needs_context_reason")
        decision.manual_override = True
        decision.reviewed_by = actor_id if status == "REVIEWED" else decision.reviewed_by
        decision.reviewed_at = datetime.utcnow() if status == "REVIEWED" else decision.reviewed_at
        decision.skipped_at = datetime.utcnow() if status == "SKIPPED" else None
        self._replace_memberships(db, decision=decision, workspace_id=workspace_id, actor_id=actor_id, collection_slugs=payload.get("collection_slugs"), tag_slugs=payload.get("tag_slugs"))
        db.flush()
        audit(db, workspace_id=workspace_id, actor_id=actor_id, action="dialog_triage.decision.save", entity_type="DialogTriageDecision", entity_id=decision.id, before=before, after=self.decision_payload(db, decision))
        return decision

    def return_to_queue(self, db: Session, *, workspace_id: str, account_id: str, dialog: TelegramDialog, actor_id: str, expected_version: int) -> DialogTriageDecision:
        decision = self._decision(db, workspace_id=workspace_id, account_id=account_id, dialog_id=dialog.id)
        if decision is None:
            raise ValueError("Triage decision not found")
        if decision.version != expected_version:
            raise TriageConflict("TRIAGE_VERSION_CONFLICT")
        before = self.decision_payload(db, decision)
        decision.review_status = "UNREVIEWED"
        decision.version += 1
        decision.manual_override = True
        decision.reviewed_at = None
        decision.skipped_at = None
        db.flush()
        audit(db, workspace_id=workspace_id, actor_id=actor_id, action="dialog_triage.return_to_queue", entity_type="DialogTriageDecision", entity_id=decision.id, before=before, after=self.decision_payload(db, decision))
        return decision

    def bulk_action(self, db: Session, *, workspace_id: str, account_id: str, dialogs: list[TelegramDialog], actor_id: str, action: str, collection_slug: str | None, tag_slug: str | None, reason: str | None, confirm_overwrite: bool) -> list[DialogTriageDecision]:
        result: list[DialogTriageDecision] = []
        for dialog in dialogs:
            decision = self._decision(db, workspace_id=workspace_id, account_id=account_id, dialog_id=dialog.id)
            if decision and decision.manual_override and not confirm_overwrite:
                raise TriageConflict("TRIAGE_BULK_OVERWRITE_CONFIRMATION_REQUIRED")
            payload: dict[str, Any]
            if action == "MARK_PERSONAL":
                payload = {"review_status": "REVIEWED", "manual_dialog_type": "PERSON", "manual_eligibility": "NOT_ELIGIBLE", "collection_slugs": None, "tag_slugs": None}
            elif action == "MARK_BOT":
                payload = {"review_status": "REVIEWED", "manual_dialog_type": "BOT", "manual_eligibility": "NOT_ELIGIBLE", "collection_slugs": None, "tag_slugs": None}
            elif action == "EXCLUDE_CAMPAIGNS":
                payload = {"review_status": "REVIEWED", "manual_dialog_type": decision.manual_dialog_type if decision else mapped_dialog_type(dialog.dialog_type), "manual_eligibility": "NOT_ELIGIBLE", "collection_slugs": None, "tag_slugs": None}
            elif action == "SKIP":
                payload = {"review_status": "SKIPPED", "manual_dialog_type": decision.manual_dialog_type if decision else mapped_dialog_type(dialog.dialog_type), "manual_eligibility": decision.manual_eligibility if decision else "MANUAL_REVIEW", "collection_slugs": None, "tag_slugs": None}
            elif action == "NEEDS_CONTEXT":
                payload = {"review_status": "NEEDS_CONTEXT", "manual_dialog_type": decision.manual_dialog_type if decision else mapped_dialog_type(dialog.dialog_type), "manual_eligibility": decision.manual_eligibility if decision else "MANUAL_REVIEW", "needs_context_reason": reason, "collection_slugs": None, "tag_slugs": None}
            elif action in {"ADD_COLLECTION", "REMOVE_COLLECTION"}:
                if not collection_slug:
                    raise ValueError("collection_slug is required")
                current = set(self._collections(db, decision.id)) if decision else set()
                current.add(collection_slug) if action == "ADD_COLLECTION" else current.discard(collection_slug)
                payload = {"review_status": decision.review_status if decision else "UNREVIEWED", "manual_dialog_type": decision.manual_dialog_type if decision else mapped_dialog_type(dialog.dialog_type), "manual_eligibility": decision.manual_eligibility if decision else "MANUAL_REVIEW", "collection_slugs": sorted(current), "tag_slugs": None, "allow_existing": True}
            elif action in {"ADD_TAG", "REMOVE_TAG"}:
                if not tag_slug:
                    raise ValueError("tag_slug is required")
                current = set(self._tags(db, decision.id)) if decision else set()
                current.add(tag_slug) if action == "ADD_TAG" else current.discard(tag_slug)
                payload = {"review_status": decision.review_status if decision else "UNREVIEWED", "manual_dialog_type": decision.manual_dialog_type if decision else mapped_dialog_type(dialog.dialog_type), "manual_eligibility": decision.manual_eligibility if decision else "MANUAL_REVIEW", "collection_slugs": None, "tag_slugs": sorted(current), "allow_existing": True}
            else:
                raise ValueError("Unknown bulk action")
            payload["expected_version"] = decision.version if decision else None
            result.append(self.save_one(db, workspace_id=workspace_id, account_id=account_id, dialog=dialog, actor_id=actor_id, payload=payload, allow_existing=bool(payload.pop("allow_existing", False))))
        return result
