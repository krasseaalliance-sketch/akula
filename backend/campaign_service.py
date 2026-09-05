"""Campaign Engine service process for Bali Companions."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.campaign_intelligence import CampaignIntelligenceEngine
from app.config import get_settings
from app.human_writing.engine import HumanWritingEngine
from app.integrations import validate_message
from app.models import Campaign, CampaignCommunityScore, Community, MessageDraft, Offer, Publication, TelegramAccountProfile, TelegramCommunityCandidate, TelegramDiscoveryRun
from app.queue import enqueue_publication
from app.service_scheduler import IndependentServiceScheduler, TickResult, actor_for, default_service_specs
from app.telegram_engine.engine import TelegramEngineService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("campaign-engine")

# Global public discovery queries for the Bali campaign.
QUERIES = ["Bali", "Бали", "Русские на Бали", "Bali русскоязычные"]

QUERIES = [
    "Бали русские попутчики",
    "Бали русские туристы",
    "Бали экспаты",
    "Bali русскоязычные",
]

# Use real UTF-8 global Telegram queries; the legacy mojibake constants above
# produced no meaningful Discovery results.
QUERIES = [
    "Бали русские попутчики",
    "Бали русские туристы",
    "Бали экспаты",
    "Бали русскоязычные",
    "Бали путешествия",
]

# Override legacy mojibake queries with UTF-8 queries used by the live client.
QUERIES = [
    "Бали русские попутчики",
    "Бали русские туристы",
    "Бали экспаты",
    "Bali русскоязычные",
]


def prepare_drafts(db, *, campaign: Campaign, workspace_id: str, actor_id: str) -> int:
    """Prepare at most the campaign daily limit; approval remains pending."""
    rows = list(db.scalars(select(CampaignCommunityScore).where(
        CampaignCommunityScore.campaign_id == campaign.id,
        CampaignCommunityScore.recommendation.in_({"PUBLISH", "REVIEW"}),
    ).order_by(CampaignCommunityScore.rank, CampaignCommunityScore.community_score.desc()).limit(campaign.daily_limit)).all())
    offer = db.get(Offer, campaign.offer_id) if campaign.offer_id else None
    prepared = 0
    writer = HumanWritingEngine()
    for row in rows:
        community = db.get(Community, row.community_id)
        if community is None:
            continue
        existing = db.scalar(select(MessageDraft).where(
            MessageDraft.campaign_id == campaign.id,
            MessageDraft.community_id == community.id,
            MessageDraft.approval_status.in_({"PENDING", "APPROVED"}),
        ))
        if existing is not None:
            continue
        result = writer.generate(db, workspace_id=workspace_id, campaign=campaign, community=community, lead=None, actor_id=actor_id)
        validation = validate_message(result.selected.content, language=campaign.language, similarity_score=result.selected.similarity_score)
        db.add(MessageDraft(
            campaign_id=campaign.id,
            community_id=community.id,
            language=campaign.language,
            content=validation.normalized_content,
            facts_snapshot={"offer": offer.name if offer else campaign.name, "verified": True},
            generation_context={"service": "campaign_engine", "human_writing_run_id": result.run.id, "approval_required": True},
            model_name=result.selected.model,
            prompt_version="human-writing-v1",
            similarity_score=validation.similarity_score,
            validation_status="VALID" if validation.valid else "INVALID",
            approval_status="PENDING",
            publication_type="COMPANION_SEARCH",
            created_by=actor_id,
            human_writing_run_id=result.run.id,
            human_variant_id=result.selected.id,
            naturalness_score=result.selected.naturalness_score,
            human_similarity_score=result.selected.similarity_score,
            human_critic={"flags": result.selected.critic_flags, "reasons": result.selected.critic_reasons},
        ))
        prepared += 1
    db.flush()
    return prepared


def queue_approved_publications(db, *, campaign: Campaign) -> int:
    """Move approved, not-yet-attempted drafts into the durable publication queue."""
    drafts = list(db.scalars(select(MessageDraft).where(
        MessageDraft.campaign_id == campaign.id,
        MessageDraft.approval_status == "APPROVED",
        MessageDraft.validation_status == "VALID",
    ).order_by(MessageDraft.created_at)).all())
    now = datetime.utcnow()
    queued = 0
    for draft in drafts:
        existing = db.scalar(select(Publication).where(
            Publication.campaign_id == campaign.id,
            Publication.message_draft_id == draft.id,
        ))
        if existing is not None:
            # Failed or unconfirmed targets are isolated; the campaign proceeds
            # with other approved objects instead of retrying a blocked target.
            continue
        publication = Publication(
            message_draft_id=draft.id,
            campaign_id=campaign.id,
            community_id=draft.community_id,
            idempotency_key=f"campaign-{campaign.id}-{draft.id}",
        )
        db.add(publication)
        db.flush()
        job = enqueue_publication(db, publication)
        job.available_at = now + timedelta(minutes=20 * queued)
        queued += 1
    return queued


def promote_discovered_candidates(db, *, candidates: list[TelegramCommunityCandidate], workspace_id: str) -> int:
    """Make externally discovered public communities available to scoring."""
    promoted = 0
    for candidate in candidates:
        community = db.scalar(select(Community).where(
            Community.workspace_id == workspace_id,
            Community.external_id == candidate.external_id,
        ))
        if community is None:
            community = Community(
                workspace_id=workspace_id,
                platform="TELEGRAM",
                external_id=candidate.external_id,
                title=candidate.title,
                username=candidate.username,
                url=candidate.url,
                language=candidate.language or "ru",
                geography=candidate.geography or "Bali",
                category=candidate.category,
                relevance_score=candidate.relevance_score * 100,
                activity_score=candidate.activity_score * 100,
                posting_status="NEEDS_REVIEW",
                classification_status="NEEDS_REVIEW",
                classification_source="CAMPAIGN_DISCOVERY",
                classification_reason=candidate.reason,
            )
            db.add(community)
            promoted += 1
    db.flush()
    return promoted


def discover_bali_candidates(db, *, profile, actor, telegram) -> list[TelegramCommunityCandidate]:
    """Discover public Bali chat communities globally, not from local dialogs."""
    candidates_by_id: dict[str, TelegramCommunityCandidate] = {}
    for query in QUERIES:
        try:
            dialogs = telegram.search_global_communities(profile=profile, query=query, limit=100)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bali global discovery failed for %r: %s", query, type(exc).__name__)
            continue
        run = TelegramDiscoveryRun(
            workspace_id=profile.workspace_id,
            integration_account_id=profile.integration_account_id,
            search_query=query,
            status="SUCCEEDED",
            result_count=0,
            completed_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()
        for item in dialogs:
            if item.dialog_type not in {"GROUP", "SUPERGROUP"} or not item.username:
                continue
            candidate = db.scalar(select(TelegramCommunityCandidate).where(
                TelegramCommunityCandidate.workspace_id == profile.workspace_id,
                TelegramCommunityCandidate.external_id == item.external_id,
            ))
            if candidate is None:
                candidate = TelegramCommunityCandidate(
                    workspace_id=profile.workspace_id,
                    discovery_run_id=run.id,
                    external_id=item.external_id,
                    title=item.title,
                    username=item.username,
                    url=f"https://t.me/{item.username}",
                    source="TELEGRAM_GLOBAL",
                    search_query=query,
                    relevance_score=0.5,
                    activity_score=min(1.0, (item.member_count or 0) / 10000),
                    geography="Bali",
                    language="ru_candidate",
                    category="BALI_COMPANIONS",
                    reason="Returned by global Telegram search; audience and posting rights require verification",
                    review_status="NEW",
                )
                db.add(candidate)
            candidates_by_id[item.external_id] = candidate
            run.result_count += 1
    db.commit()
    return list(candidates_by_id.values())


def run_tick(db, workspace) -> TickResult:
    actor = actor_for(workspace, db)
    username = os.getenv("TELEGRAM_ACCOUNT_USERNAME", "Nusa_Penida_Man")
    profile = db.scalar(select(TelegramAccountProfile).where(
        TelegramAccountProfile.workspace_id == workspace.id,
        TelegramAccountProfile.username == username,
        TelegramAccountProfile.authorization_status == "AUTHORIZED",
    ))
    if profile is None:
        raise RuntimeError("TELEGRAM_AUTH_REQUIRED")
    campaign_name = os.getenv("CAMPAIGN_SERVICE_CAMPAIGN_NAME", "Bali Companions")
    campaign = db.scalar(select(Campaign).where(Campaign.name.ilike(f"%{campaign_name}%")).order_by(Campaign.created_at))
    if campaign is None:
        campaign = db.scalar(select(Campaign).where(Campaign.geography.ilike("%Bali%")).order_by(Campaign.created_at))
    if campaign is None:
        raise RuntimeError("CAMPAIGN_NOT_CONFIGURED")

    tick_started = datetime.utcnow()
    telegram = TelegramEngineService()
    candidates = discover_bali_candidates(db, profile=profile, actor=actor, telegram=telegram)
    promoted = promote_discovered_candidates(db, candidates=candidates, workspace_id=workspace.id)
    new_candidates = [candidate for candidate in candidates if candidate.created_at and candidate.created_at >= tick_started]
    if new_candidates:
        lines = ["📡 Campaign Engine · Bali Companions", f"Новых сообществ: {len(new_candidates)}"]
        for candidate in new_candidates[:20]:
            lines.append(f"• {candidate.title}")
            if candidate.url:
                lines.append(f"  {candidate.url}")
        telegram.send_operator_notification(profile=profile, content="\n".join(lines), target=os.getenv("TELEGRAM_BALI_LEADS_CHAT_ID"))
    # Campaign Intelligence scores the existing dataset and remains approval-first.
    CampaignIntelligenceEngine().analyze(db, campaign=campaign, workspace_id=workspace.id, actor_id=actor.id, use_llm=True)
    prepared = prepare_drafts(db, campaign=campaign, workspace_id=workspace.id, actor_id=actor.id)
    queued = queue_approved_publications(db, campaign=campaign)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    publications = int(db.scalar(select(func.count(Publication.id)).where(Publication.campaign_id == campaign.id, Publication.created_at >= today)) or 0)
    communities = int(db.scalar(select(func.count(Community.id)).where(Community.workspace_id == workspace.id, Community.geography.ilike("%Bali%"))) or 0)
    return TickResult(publications=publications, communities=communities, stats={
        "campaign_id": campaign.id,
        "candidate_records": len(candidates),
        "queries": len(QUERIES),
        "prepared_drafts": prepared,
        "promoted_communities": promoted,
        "queued_publications": queued,
        "approval_required": True,
        "real_send_enabled": get_settings().telegram_real_send_enabled,
        "result_verification_required": True,
    })


if __name__ == "__main__":
    IndependentServiceScheduler(default_service_specs()["campaign_engine"], run_tick).run_forever()
