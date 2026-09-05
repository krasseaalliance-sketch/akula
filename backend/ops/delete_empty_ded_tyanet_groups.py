from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


TARGETS = {"флудилка", "квизы"}


async def delete_groups(client) -> None:
    from telethon import functions

    await client._connect()
    try:
        for dialog in await client._client.get_dialogs(limit=500):
            entity = dialog.entity
            title = (getattr(entity, "title", "") or "").casefold()
            if title not in TARGETS or client._dialog_type(entity) not in {"GROUP", "SUPERGROUP"}:
                continue
            await client._client(functions.channels.DeleteChannelRequest(channel=entity))
            print(f"DELETED title={getattr(entity, 'title', title)} id={getattr(entity, 'id', None)}", flush=True)
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
        asyncio.run(delete_groups(TelegramEngineService()._client_for_profile(profile)))


if __name__ == "__main__":
    main()
