from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Campaign,
    Community,
    MessageDraft,
    Publication,
    TelegramAccountProfile,
    TelegramDialog,
    User,
    Workspace,
)
from app.queue import enqueue_publication
from app.telegram_engine.engine import TelegramEngineService


ITEMS = [
    (
        "3820388701",
        "ambassadorbali",
        "Всем привет! Собираем небольшую компанию на двухдневную поездку по северу Бали 29–30 июля: дельфины, вулкан Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Есть четыре свободных места в машине. Если хотите присоединиться, напишите в комментариях.",
        0,
    ),
    (
        "1161105353",
        "baliktoletit_life",
        "Ищу попутчиков на 29–30 июля — едем на два дня по северу Бали. Планируем увидеть дельфинов, Батур, Sekumpul, храм на озере, клубничные плантации и диких животных. Осталось четыре места в машине. Кому актуально такое путешествие, откликнитесь здесь.",
        90,
    ),
]


def main() -> None:
    db = SessionLocal()
    workspace = db.scalar(select(Workspace))
    actor = db.scalar(select(User).where(User.id == workspace.owner_id))
    campaign = db.scalar(select(Campaign).where(Campaign.geography.ilike("%Bali%")))
    profile = db.scalar(
        select(TelegramAccountProfile).where(
            TelegramAccountProfile.username == "Alexey_Mifanyuk",
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        )
    )
    engine = TelegramEngineService()
    for external_id, username, content, delay_minutes in ITEMS:
        community = db.scalar(
            select(Community).where(
                Community.workspace_id == workspace.id,
                Community.external_id == external_id,
            )
        )
        if community is None:
            community = Community(
                workspace_id=workspace.id,
                platform="TELEGRAM",
                external_id=external_id,
                title=username,
                username=username,
                url=f"https://t.me/{username}",
                language="ru",
                geography="Bali",
                posting_status="NEEDS_REVIEW",
                classification_status="NEEDS_REVIEW",
                classification_source="OPERATOR",
            )
            db.add(community)
            db.flush()
        community.geography = "Bali"
        dialog = db.scalar(
            select(TelegramDialog).where(
                TelegramDialog.integration_account_id == profile.integration_account_id,
                TelegramDialog.external_dialog_id == external_id,
            )
        )
        if dialog is None:
            raise RuntimeError(f"LIVE_DIALOG_NOT_FOUND:{external_id}")
        dialog.community_id = community.id
        engine.review_rules(
            db,
            community=community,
            actor=actor,
            approved=True,
            allowed_content_types=["COMPANION_SEARCH"],
            allowed_days=[],
            min_interval_hours=30,
            expires_at=None,
        )
        draft = db.scalar(
            select(MessageDraft).where(
                MessageDraft.campaign_id == campaign.id,
                MessageDraft.community_id == community.id,
            )
        )
        if draft is None:
            draft = MessageDraft(
                campaign_id=campaign.id,
                community_id=community.id,
                language="ru",
                content=content,
                facts_snapshot={"dates": "29–30 июля", "location": "север Бали", "available_seats": 4},
                generation_context={"operator_approval": "campaign launch"},
                model_name="operator-approved-campaign-copy",
                prompt_version="pilot-001",
                similarity_score=0.0,
                validation_status="VALID",
                approval_status="APPROVED",
                created_by=actor.id,
                approved_by=actor.id,
                publication_type="COMPANION_SEARCH",
                naturalness_score=95.0,
                human_similarity_score=0.0,
                human_critic={},
            )
            db.add(draft)
            db.flush()
        else:
            draft.content = content
            draft.approval_status = "APPROVED"
            draft.approved_by = actor.id
            draft.validation_status = "VALID"
            draft.publication_type = "COMPANION_SEARCH"
        publication = db.scalar(
            select(Publication).where(Publication.message_draft_id == draft.id)
        )
        if publication is None:
            publication = Publication(
                message_draft_id=draft.id,
                campaign_id=campaign.id,
                community_id=community.id,
                status="DRAFT",
                idempotency_key=f"pilot001:{external_id}",
            )
            db.add(publication)
            db.flush()
            job = enqueue_publication(db, publication)
            job.available_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
            print(f"QUEUED {username} {publication.id} {job.id} {job.available_at.isoformat()}")
        else:
            print(f"EXISTS {username} {publication.status}")
    db.commit()
    db.close()


if __name__ == "__main__":
    main()
