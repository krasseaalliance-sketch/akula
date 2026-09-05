"""Create separate private supergroups for the Ded Tyanet community."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


GROUPS = (
    ("Флудилка", "Свободное общение участников чата «Дед Тянет»."),
    ("Квизы", "Квизы и обсуждение результатов для участников чата «Дед Тянет»."),
)


async def create_groups(client) -> None:
    from telethon import functions

    await client._connect()
    try:
        dialogs = await client._client.get_dialogs(limit=500)
        existing = {
            getattr(dialog.entity, "title", "").casefold(): dialog.entity
            for dialog in dialogs
            if getattr(dialog.entity, "title", None)
        }
        for title, about in GROUPS:
            entity = existing.get(title.casefold())
            if entity is None:
                result = await client._client(functions.channels.CreateChannelRequest(
                    title=title,
                    about=about,
                    broadcast=False,
                    megagroup=True,
                ))
                entity = result.chats[0]
                existing[title.casefold()] = entity
                print(f"CREATED title={title} id={entity.id}", flush=True)
            else:
                print(f"ALREADY_EXISTS title={title} id={entity.id}", flush=True)
            try:
                invite = await client._client(functions.messages.ExportChatInviteRequest(peer=entity))
                link = getattr(invite, "link", None)
                if link:
                    print(f"INVITE title={title} link={link}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"INVITE_FAILED title={title} error={type(exc).__name__}", flush=True)
    finally:
        await client._client.disconnect()


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        profile = db.scalar(select(TelegramAccountProfile).where(
            TelegramAccountProfile.workspace_id == workspace.id,
            TelegramAccountProfile.username == "Alexey_Mifanyuk",
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        ))
        client = TelegramEngineService()._client_for_profile(profile)
        asyncio.run(create_groups(client))


if __name__ == "__main__":
    main()
