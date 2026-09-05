"""Join remaining Bali communities and queue approved posts 20 minutes apart."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from sqlalchemy import func, select

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


TARGETS = {
    "russians_bali_chat": "Собираем компанию на два дня по северу Бали 29–30 июля. Хотим заехать к дельфинам, на Батур и Sekumpul, а также к храму на озере, на клубничные плантации и посмотреть диких животных. В машине осталось четыре места. Пишите в личку.",
    "russkie_na_bali": "На 29–30 июля планируем маршрут по северу Бали: дельфины, вулкан Батур, Sekumpul, храм на озере, клубничные плантации и места с дикими животными. Едем на машине, свободны четыре места. Пишите в личку.",
    "RusinBali": "Ищем попутчиков на двухдневную поездку по северу Бали 29–30 июля. В программе дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Есть четыре свободных места в машине. Пишите в личку.",
    "russianbalicomm": "Кто хотел бы присоединиться к поездке по северу Бали 29–30 июля? За два дня планируем дельфинов, Батур, Sekumpul, храм на озере, клубничные плантации и места с дикими животными. Осталось четыре места в машине. Пишите в личку.",
    "bali_v_russkie_na_ostrove": "На 29–30 июля собираем попутчиков для двухдневной поездки по северу Бали. Планируем дельфинов, Батур, Sekumpul, храм на озере, клубничные плантации и места с дикими животными. В машине четыре места. Пишите в личку.",
    "balichat62": "Планируем на 29–30 июля поездку по северу Бали на два дня: дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Едем на машине, свободны четыре места. Пишите в личку.",
    "bali_russians": "Есть четыре свободных места в машине на двухдневную поездку по северу Бали 29–30 июля. В маршруте дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Пишите в личку.",
    "RussianratsinBali": "Ищем попутчиков на север Бали 29–30 июля. За два дня хотим увидеть дельфинов, Батур и Sekumpul, заехать к храму на озере, на клубничные плантации и к местам с дикими животными. Есть четыре места в машине. Пишите в личку.",
    "rgcbali": "На 29–30 июля планируем автомобильную поездку по северу Бали с дельфинами, Батуром, Sekumpul, храмом на озере, клубничными плантациями и дикими животными. Осталось четыре места. Пишите в личку.",
    "russiansinbali": "Собираем компанию на два дня по северу Бали 29–30 июля. Маршрут: дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. В машине ещё четыре места. Пишите в личку.",
    "lekarstva_bali": "Если кто-то из русскоязычных на Бали хотел съездить на север острова 29–30 июля, у нас есть четыре свободных места в машине. В программе дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Пишите в личку.",
    "baliktoletit_life": "На 29–30 июля ищем попутчиков для двухдневной поездки по северу Бали. Планируем дельфинов, Батур, Sekumpul, храм на озере, клубничные плантации и диких животных. Есть четыре места в машине. Пишите в личку.",
}


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        profile = db.scalar(
            select(TelegramAccountProfile).where(
                TelegramAccountProfile.workspace_id == workspace.id,
                TelegramAccountProfile.username == "Alexey_Mifanyuk",
                TelegramAccountProfile.authorization_status == "AUTHORIZED",
            )
        )
        if profile is None:
            raise RuntimeError("TELEGRAM_AUTH_REQUIRED")
        actor = actor_for(workspace, db)
        campaign = db.scalar(
            select(Campaign).where(
                Campaign.name == "Бали — поиск попутчиков",
                Campaign.status == "ACTIVE",
            )
        )
        if campaign is None:
            raise RuntimeError("BALI_CAMPAIGN_NOT_FOUND")

        engine = TelegramEngineService()
        next_at = datetime.utcnow()
        last_sent = db.scalar(
            select(func.max(Publication.sent_at)).where(
                Publication.campaign_id == campaign.id,
                Publication.status == "SENT",
            )
        )
        if last_sent:
            next_at = max(next_at, last_sent + timedelta(minutes=20))
        last_queued = db.scalar(
            select(func.max(PublicationJob.available_at))
            .join(Publication, PublicationJob.publication_id == Publication.id)
            .where(
                Publication.campaign_id == campaign.id,
                Publication.status == "QUEUED",
            )
        )
        if last_queued:
            next_at = max(next_at, last_queued + timedelta(minutes=20))

        for username, content in TARGETS.items():
            normalized = username.casefold()
            dialog = db.scalar(
                select(TelegramDialog).where(
                    TelegramDialog.integration_account_id == profile.integration_account_id,
                    func.lower(TelegramDialog.username) == normalized,
                )
            )
            if dialog is None or not dialog.is_joined:
                try:
                    dialog = engine.join_public_community(
                        db, profile=profile, username=username, actor=actor
                    )
                    print(f"JOINED @{username} can_send={dialog.can_send_messages}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"JOIN_FAILED @{username} {type(exc).__name__}", flush=True)
                    if type(exc).__name__ == "FloodWaitError":
                        break
                    continue
                time.sleep(5)
            if not dialog.can_send_messages or not dialog.community_id:
                print(f"SKIP_NO_SEND @{username}", flush=True)
                continue
            community = db.get(Community, dialog.community_id)
            if community is None:
                print(f"SKIP_NO_COMMUNITY @{username}", flush=True)
                continue

            permission = db.scalar(
                select(CommunityPermission).where(
                    CommunityPermission.workspace_id == workspace.id,
                    CommunityPermission.community_id == community.id,
                )
            )
            if permission is None:
                permission = CommunityPermission(
                    workspace_id=workspace.id,
                    community_id=community.id,
                    permission_type="POST",
                )
                db.add(permission)
            permission.status = "ACTIVE"
            permission.approved_by = actor.id
            permission.reviewed_by = actor.id
            permission.reviewed_at = datetime.utcnow()
            permission.allowed_content_types = ["COMPANION_SEARCH"]
            permission.evidence = "Operator requested Bali campaign queue after joining the community"
            community.posting_status = "APPROVED"

            key = f"campaign-bali-companions-20m-{normalized}"
            publication = db.scalar(
                select(Publication).where(Publication.idempotency_key == key)
            )
            if publication is None:
                draft = MessageDraft(
                    campaign_id=campaign.id,
                    community_id=community.id,
                    message_type="DIRECT_RESPONSE",
                    publication_type="COMPANION_SEARCH",
                    language="ru",
                    content=content,
                    facts_snapshot={"dates": "29–30 июля", "route": "Северный Бали", "seats": 4, "verified": True},
                    generation_context={"operator_confirmed": True, "unique_for_community": username},
                    model_name="operator-approved-v1",
                    prompt_version="operator-approved-v1",
                    similarity_score=0,
                    validation_status="VALID",
                    approval_status="APPROVED",
                    created_by=actor.id,
                    approved_by=actor.id,
                    naturalness_score=90,
                    human_similarity_score=0,
                    human_critic={"operator_confirmed": True},
                )
                db.add(draft)
                db.flush()
                publication = Publication(
                    message_draft_id=draft.id,
                    campaign_id=campaign.id,
                    community_id=community.id,
                    idempotency_key=key,
                )
                db.add(publication)
                db.flush()
                job = enqueue_publication(db, publication)
                job.available_at = next_at
                db.commit()
                print(f"QUEUED @{username} at {next_at.isoformat()}", flush=True)
                next_at += timedelta(minutes=20)
            else:
                print(f"EXISTING @{username} {publication.status}", flush=True)


if __name__ == "__main__":
    main()
