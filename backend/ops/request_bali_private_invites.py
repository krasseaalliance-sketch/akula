"""Submit join requests for explicitly provided private Bali invite links."""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


INVITES = {
    "VibeTrip": "DXaf8gqY4TA4Yjg6",
    "Свои на Бали": "1IGkrqSElxAxMDZi",
    "Bali | women's secrets": "Fjv5IAdbHR44NTYy",
    "ГалЁрка Бали": "aPBZkuChvwhkOGMy",
}


async def submit(client, name: str, invite_hash: str) -> str:
    from telethon import functions

    await client._connect()
    try:
        result = await client._client(functions.messages.ImportChatInviteRequest(invite_hash))
        return type(result).__name__
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
        engine = TelegramEngineService()
        for name, invite_hash in INVITES.items():
            try:
                status = asyncio.run(submit(engine._client_for_profile(profile), name, invite_hash))
                print(f"INVITE_SUBMITTED {name} {status}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"INVITE_RESULT {name} {type(exc).__name__}", flush=True)
                if type(exc).__name__ == "FloodWaitError":
                    break
            time.sleep(5)


if __name__ == "__main__":
    main()
