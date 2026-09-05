"""Schedule approved Bali posts with a 20-minute interval."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Campaign,
    Community,
    CommunityPermission,
    MessageDraft,
    Publication,
    PublicationJob,
    TelegramAccountProfile,
    TelegramDialog,
    Workspace,
)
from app.queue import enqueue_publication
from app.service_scheduler import actor_for
from app.telegram_engine.engine import TelegramEngineService


TEXTS = {
    "voprosBali": "Бали, кто-нибудь планирует выбраться на север острова 29–30 июля? Ищем попутчиков на двухдневную поездку: дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Есть четыре места в машине. Пишите в личку.",
    "balichat": "Друзья, на 29–30 июля собираем двухдневную поездку по северному Бали. В маршруте дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Едем на машине, свободны четыре места. Пишите в личку.",
    "russians_in_bali": "Есть идея на конец июля: два дня едем по северу Бали 29–30 июля. Хотим успеть дельфинов, Батур, Sekumpul, храм на озере, клубничные плантации и места с дикими животными. Осталось четыре места в машине. Пишите в личку.",
}


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        profile = db.scalar(select(TelegramAccountProfile).where(
            TelegramAccountProfile.workspace_id == workspace.id,
            TelegramAccountProfile.username == "Alexey_Mifanyuk",
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        ))
        actor = actor_for(workspace, db)
        dialogs = TelegramEngineService().sync_dialogs(db, profile=profile, actor=actor)
        campaign = db.scalar(select(Campaign).where(
            Campaign.geography.ilike("%Bali%"), Campaign.status == "ACTIVE"
        ).order_by(Campaign.created_at))
        now = datetime.utcnow()
        scheduled = []
        for index, (username, content) in enumerate(TEXTS.items(), start=1):
            dialog = next((item for item in dialogs if (item.username or "").casefold() == username.casefold()), None)
            if dialog is None or not dialog.is_joined or not dialog.can_send_messages:
                print(f"SKIP {username} not_joined_or_no_send", flush=True)
                continue
            community = db.scalar(select(Community).where(
                Community.workspace_id == workspace.id,
                Community.external_id == dialog.external_dialog_id,
            ))
            if community is None:
                print(f"SKIP {username} community_not_found", flush=True)
                continue
            permission = db.scalar(select(CommunityPermission).where(
                CommunityPermission.workspace_id == workspace.id,
                CommunityPermission.community_id == community.id,
            ))
            if permission is None:
                permission = CommunityPermission(
                    workspace_id=workspace.id, community_id=community.id, permission_type="POST"
                )
                db.add(permission)
            permission.status = "ACTIVE"
            permission.approved_by = actor.id
            permission.reviewed_by = actor.id
            permission.allowed_content_types = ["COMPANION_SEARCH"]
            community.posting_status = "APPROVED"
            draft = db.scalar(select(MessageDraft).where(
                MessageDraft.campaign_id == campaign.id,
                MessageDraft.community_id == community.id,
                MessageDraft.approval_status.in_(["PENDING", "APPROVED"]),
            ))
            if draft is None:
                draft = MessageDraft(
                    campaign_id=campaign.id, community_id=community.id,
                    message_type="DIRECT_RESPONSE", publication_type="COMPANION_SEARCH",
                    language="ru", content=content,
                    facts_snapshot={"dates": "29-30 July", "route": "North Bali", "seats": 4, "verified": True},
                    generation_context={"operator_confirmed": True, "unique_for_community": username},
                    model_name="operator-approved-v1", prompt_version="operator-approved-v1",
                    similarity_score=0, validation_status="VALID", approval_status="APPROVED",
                    created_by=actor.id, approved_by=actor.id, naturalness_score=90,
                    human_similarity_score=0, human_critic={"operator_confirmed": True},
                )
                db.add(draft)
                db.flush()
            else:
                draft.content = content
                draft.approval_status = "APPROVED"
                draft.approved_by = actor.id
            publication = db.scalar(select(Publication).where(
                Publication.campaign_id == campaign.id,
                Publication.community_id == community.id,
                Publication.idempotency_key == "campaign-bali-distributed-" + username,
            ))
            if publication is None:
                publication = Publication(
                    message_draft_id=draft.id, campaign_id=campaign.id,
                    community_id=community.id,
                    idempotency_key="campaign-bali-distributed-" + username,
                )
                db.add(publication)
                db.flush()
            publication.status = "QUEUED"
            publication.external_message_id = None
            publication.sent_at = None
            publication.error_code = None
            publication.error_message = None
            publication.queued_at = now
            job = db.scalar(select(PublicationJob).where(PublicationJob.publication_id == publication.id))
            if job is None:
                job = enqueue_publication(db, publication)
            else:
                job.status = "QUEUED"
                job.attempts = 0
                job.error_code = None
                job.error_message = None
                job.cancelled_at = None
            job.available_at = now + timedelta(minutes=20 * index)
            scheduled.append((username, job.available_at.isoformat()))
        db.commit()
        for username, available_at in scheduled:
            print(f"SCHEDULED {username} {available_at}", flush=True)


if __name__ == "__main__":
    main()
