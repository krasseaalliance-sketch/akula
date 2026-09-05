from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


async def inspect(client) -> None:
    await client._connect()
    try:
        for dialog in await client._client.get_dialogs(limit=500):
            entity = dialog.entity
            title = getattr(entity, "title", "") or ""
            if "дед" in title.casefold() or "тянет" in title.casefold():
                from telethon import functions
                full = await client._client(functions.channels.GetFullChannelRequest(channel=entity))
                print({
                    "title": title,
                    "type": client._dialog_type(entity),
                    "id": getattr(entity, "id", None),
                    "username": getattr(entity, "username", None),
                    "megagroup": getattr(entity, "megagroup", None),
                    "forum": getattr(entity, "forum", None),
                    "linked_chat_id": getattr(full.full_chat, "linked_chat_id", None),
                    "linked_entities": [
                        {
                            "title": getattr(item, "title", None),
                            "id": getattr(item, "id", None),
                            "type": client._dialog_type(item),
                            "username": getattr(item, "username", None),
                        }
                        for item in getattr(full, "chats", [])
                    ],
                }, flush=True)
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
        asyncio.run(inspect(TelegramEngineService()._client_for_profile(profile)))


if __name__ == "__main__":
    main()
