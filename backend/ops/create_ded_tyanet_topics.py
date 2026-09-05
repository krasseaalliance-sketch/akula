from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


CHAT_TITLE = "чат дед тянет"
TOPICS = ("Флудилка", "Квизы")


async def configure_topics(client) -> None:
    from telethon import functions

    await client._connect()
    try:
        entity = None
        for dialog in await client._client.get_dialogs(limit=500):
            candidate = dialog.entity
            title = (getattr(candidate, "title", "") or "").casefold()
            if title == CHAT_TITLE and client._dialog_type(candidate) == "SUPERGROUP":
                entity = candidate
                break
        if entity is None:
            raise RuntimeError("CHAT_NOT_FOUND")

        if not getattr(entity, "forum", False):
            await client._client(functions.channels.ToggleForumRequest(
                channel=entity,
                enabled=True,
                tabs=False,
            ))
            print("FORUM_ENABLED", flush=True)

        topics = await client._client(functions.messages.GetForumTopicsRequest(
            peer=entity,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100,
            q=None,
        ))
        existing = {
            (getattr(topic, "title", "") or "").casefold()
            for topic in getattr(topics, "topics", [])
        }
        for title in TOPICS:
            if title.casefold() in existing:
                print(f"TOPIC_EXISTS title={title}", flush=True)
                continue
            await client._client(functions.messages.CreateForumTopicRequest(
                peer=entity,
                title=title,
            ))
            print(f"TOPIC_CREATED title={title}", flush=True)
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
        asyncio.run(configure_topics(TelegramEngineService()._client_for_profile(profile)))


if __name__ == "__main__":
    main()
