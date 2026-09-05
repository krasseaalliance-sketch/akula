"""Repair Bali preview/publication text after a transport encoding error."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Campaign, MessageDraft, Publication, TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


TEXTS = {
    "voprosBali": (
        "\u0411\u0430\u043b\u0438, \u043a\u0442\u043e\u2011\u043d\u0438\u0431\u0443\u0434\u044c \u043f\u043b\u0430\u043d\u0438\u0440\u0443\u0435\u0442 \u0432\u044b\u0431\u0440\u0430\u0442\u044c\u0441\u044f \u043d\u0430 \u0441\u0435\u0432\u0435\u0440 \u043e\u0441\u0442\u0440\u043e\u0432\u0430 29\u201330 \u0438\u044e\u043b\u044f? \u0418\u0449\u0435\u043c \u043f\u043e\u043f\u0443\u0442\u0447\u0438\u043a\u043e\u0432 \u043d\u0430 \u0434\u0432\u0443\u0445\u0434\u043d\u0435\u0432\u043d\0443\u044e \u043f\u043e\u0435\u0437\u0434\u043a\u0443: \u0434\u0435\u043b\u044c\u0444\u0438\u043d\u044b, \u0411\u0430\u0442\u0443\u0440, Sekumpul, \u0445\u0440\u0430\u043c \u043d\u0430 \u043e\u0437\u0435\u0440\u0435, \u043a\u043b\u0443\u0431\u043d\u0438\u0447\u043d\u044b\u0435 \u043f\u043b\u0430\u043d\u0442\u0430\u0446\u0438\u0438 \u0438 \u0434\u0438\u043a\u0438\u0435 \u0436\u0438\u0432\u043e\u0442\u043d\044b\u0435. \u0415\u0441\u0442\u044c \u0447\u0435\u0442\u044b\u0440\u0435 \u043c\u0435\u0441\u0442\u0430 \u0432 \u043c\u0430\u0448\u0438\u043d\u0435. \u0415\u0441\u043b\u0438 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u043e, \u043f\u0438\u0448\u0438\u0442\u0435 \u0432 \u043b\u0438\u0447\u043a\u0443 \u2014 \u0440\u0430\u0441\u0441\u043a\u0430\u0436\u0443 \u0434\u0435\u0442\u0430\u043b\u0438."
    ),
    "balichat": (
        "\u0414\u0440\u0443\u0437\u044c\u044f, \u043d\u0430 29\u201330 \u0438\u044e\u043b\u044f \u0441\u043e\u0431\u0438\u0440\u0430\u0435\u043c \u0434\u0432\u0443\u0445\u0434\u043d\u0435\u0432\u043d\0443\u044e \u043f\u043e\u0435\u0437\u0434\u043a\u0443 \u043f\u043e \u0441\u0435\u0432\u0435\u0440\u043d\u043e\u043c\u0443 \u0411\u0430\u043b\u0438. \u0412 \u043c\u0430\u0440\u0448\u0440\u0443\u0442\u0435 \u0434\u0435\u043b\u044c\u0444\u0438\u043d\u044b, \u0411\u0430\u0442\u0443\u0440, Sekumpul, \u0445\u0440\u0430\u043c \u043d\u0430 \u043e\u0437\u0435\u0440\u0435, \u043a\u043b\u0443\u0431\u043d\u0438\u0447\u043d\u044b\u0435 \u043f\u043b\u0430\u043d\u0442\u0430\u0446\u0438\u0438 \u0438 \u0434\u0438\u043a\u0438\u0435 \u0436\u0438\u0432\u043e\u0442\u043d\044b\u0435. \u0415\u0434\u0435\u043c \u043d\u0430 \u043c\u0430\u0448\u0438\u043d\u0435, \u0441\u0432\u043e\u0431\u043e\u0434\u043d\044b \u0447\u0435\u0442\u044b\u0440\u0435 \u043c\u0435\u0441\u0442\u0430. \u041f\u0438\u0448\u0438\u0442\u0435 \u0432 \u043b\u0438\u0447\u043a\u0443, \u0435\u0441\u043b\u0438 \u0445\u043e\u0442\u0438\u0442\u0435 \u043f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438."
    ),
    "russians_in_bali": (
        "\u0415\u0441\u0442\u044c \u0438\u0434\u0435\u044f \u043d\u0430 \u043a\u043e\u043d\u0435\u0446 \u0438\u044e\u043b\u044f: \u0434\u0432\u0430 \u0434\u043d\u044f \u0435\u0434\u0435\u043c \u043f\u043e \u0441\u0435\u0432\u0435\u0440\u0443 \u0411\u0430\u043b\u0438 29\u201330 \u0438\u044e\u043b\u044f. \u0425\u043e\u0447\u0435\u043c \u0443\u0441\u043f\u0435\u0442\u044c \u0434\u0435\u043b\u044c\u0444\u0438\u043d\u043e\u0432, \u0411\u0430\u0442\u0443\u0440, Sekumpul, \u0445\u0440\u0430\u043c \u043d\u0430 \u043e\u0437\u0435\u0440\u0435, \u043a\u043b\u0443\u0431\u043d\u0438\u0447\u043d\u044b\u0435 \u043f\u043b\u0430\u043d\u0442\u0430\u0446\u0438\u0438 \u0438 \u043c\u0435\u0441\u0442\u0430 \u0441 \u0434\u0438\u043a\u0438\u043c\u0438 \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u043c\u0438. \u041e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u0447\u0435\u0442\u044b\u0440\u0435 \u043c\u0435\u0441\u0442\u0430 \u0432 \u043c\u0430\u0448\u0438\u043d\u0435. \u041f\u0438\u0448\u0438\u0442\u0435 \u0432 \u043b\u0438\u0447\u043a\u0443 \u2014 \u043e\u0442\u0432\u0435\u0447\u0443 \u043d\u0430 \u0432\u043e\u043f\u0440\u043e\u0441\u044b."
    ),
}


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        campaign = db.scalar(select(Campaign).where(Campaign.geography.ilike("%Bali%"), Campaign.status == "ACTIVE").order_by(Campaign.created_at))
        for username, content in TEXTS.items():
            publication = db.scalar(select(Publication).where(
                Publication.campaign_id == campaign.id,
                Publication.idempotency_key == "campaign-bali-distributed-" + username,
            ))
            if publication:
                draft = db.get(MessageDraft, publication.message_draft_id)
                draft.content = content
        first = db.scalar(select(Publication).where(Publication.idempotency_key == "campaign-bali-companions-first-live-bali_russia_choogl"))
        if first:
            db.get(MessageDraft, first.message_draft_id).content = "\u0415\u0441\u043b\u0438 \u0445\u043e\0442\u0438\u0442\u0435 \u043f\u0440\u0438\u0441\u043e\u0435\u0434\u0438\u043d\u0438\u0442\u044c\u0441\u044f, \u043f\u0438\u0448\u0438\u0442\u0435 \u0432 \u043b\u0438\u0447\u043a\u0443 \u2014 \u0440\u0430\u0441\u0441\u043a\u0430\u0436\u0443 \u0434\u0435\u0442\u0430\u043b\u0438."
        db.commit()

        profile = db.scalar(select(TelegramAccountProfile).where(
            TelegramAccountProfile.workspace_id == workspace.id,
            TelegramAccountProfile.username == "Alexey_Mifanyuk",
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        ))
        client = TelegramEngineService()._client_for_profile(profile)
        preview = "\U0001f4cb Bali Companions — исправленное превью\n\n" + "\n\n".join(
            f"@{username}\n{content}" for username, content in TEXTS.items()
        )

        async def edit_preview() -> bool:
            await client._connect()
            try:
                await client._client.edit_message("-5462252245", 638288, preview)
                return True
            finally:
                await client._client.disconnect()

        try:
            edited = asyncio.run(edit_preview())
        except Exception as exc:  # noqa: BLE001
            edited = False
            print(f"EDIT_PREVIEW_FAILED {type(exc).__name__}", flush=True)
        if edited:
            print("PREVIEW_EDITED 638288", flush=True)
        else:
            result = TelegramEngineService().send_operator_notification(
                profile=profile,
                content=preview,
                target=os.getenv("TELEGRAM_BALI_LEADS_CHAT_ID", "-5462252245"),
            )
            print(f"PREVIEW_SENT_CORRECTED {result}", flush=True)


if __name__ == "__main__":
    main()
