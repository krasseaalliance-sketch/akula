"""Replace malformed Bali preview with clean operator-review text."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Campaign, MessageDraft, Publication, TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


TEXTS = {
    "voprosBali": "Бали, кто-нибудь планирует выбраться на север острова 29–30 июля? Ищем попутчиков на двухдневную поездку: дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Есть четыре места в машине. Пишите в личку.",
    "balichat": "Друзья, на 29–30 июля собираем двухдневную поездку по северному Бали. В маршруте дельфины, Батур, Sekumpul, храм на озере, клубничные плантации и дикие животные. Едем на машине, свободны четыре места. Пишите в личку.",
    "russians_in_bali": "Есть идея на конец июля: два дня едем по северу Бали 29–30 июля. Хотим успеть дельфинов, Батур, Sekumpul, храм на озере, клубничные плантации и места с дикими животными. Осталось четыре места в машине. Пишите в личку.",
}


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        campaign = db.scalar(select(Campaign).where(Campaign.geography.ilike("%Bali%"), Campaign.status == "ACTIVE").order_by(Campaign.created_at))
        for username, content in TEXTS.items():
            publication = db.scalar(select(Publication).where(Publication.campaign_id == campaign.id, Publication.idempotency_key == "campaign-bali-distributed-" + username))
            if publication:
                db.get(MessageDraft, publication.message_draft_id).content = content
        db.commit()

        profile = db.scalar(select(TelegramAccountProfile).where(TelegramAccountProfile.workspace_id == workspace.id, TelegramAccountProfile.username == "Alexey_Mifanyuk", TelegramAccountProfile.authorization_status == "AUTHORIZED"))
        service = TelegramEngineService()
        client = service._client_for_profile(profile)
        preview = "📋 Bali Companions — чистое превью\n\n" + "\n\n".join(f"@{username}\n{content}" for username, content in TEXTS.items())

        async def remove_old() -> None:
            await client._connect()
            try:
                dialogs = await client._client.get_dialogs(limit=500)
                entity = next(item.entity for item in dialogs if str(getattr(item.entity, "id", "")) == "5462252245")
                await client._client.delete_messages(entity, [638295])
            finally:
                await client._client.disconnect()

        try:
            asyncio.run(remove_old())
        except Exception as exc:  # noqa: BLE001
            print(f"OLD_PREVIEW_DELETE {type(exc).__name__}", flush=True)
        result = service.send_operator_notification(profile=profile, content=preview, target=os.getenv("TELEGRAM_BALI_LEADS_CHAT_ID", "-5462252245"))
        print(f"CLEAN_PREVIEW_SENT {result}", flush=True)


if __name__ == "__main__":
    main()
