"""Join only remaining Bali groups/supergroups; never join channels or bots."""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, TelegramDialog, Workspace
from app.service_scheduler import actor_for
from app.telegram_engine.engine import TelegramEngineService


TARGETS = (
    "russianubud",
    "balichat62",
    "rgcbali",
    "music_bali_russian",
    "bali_v_russkie_na_ostrove",
)


async def entity_type(client, username: str) -> str:
    await client._connect()
    try:
        entity = await client._client.get_entity(username)
        return client._dialog_type(entity)
    finally:
        await client._client.disconnect()


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
        actor = actor_for(workspace, db)
        engine = TelegramEngineService()
        client = engine._client_for_profile(profile)
        for username in TARGETS:
            existing = db.scalar(
                select(TelegramDialog).where(
                    TelegramDialog.integration_account_id == profile.integration_account_id,
                    TelegramDialog.username.ilike(username),
                )
            )
            if existing is not None and existing.is_joined:
                print(f"ALREADY_JOINED @{username} type={existing.dialog_type}", flush=True)
                continue
            try:
                dialog_type = asyncio.run(entity_type(client, username))
            except Exception as exc:  # noqa: BLE001
                print(f"TYPE_CHECK_FAILED @{username} {type(exc).__name__}", flush=True)
                continue
            if dialog_type not in {"GROUP", "SUPERGROUP"}:
                print(f"SKIP_NOT_CHAT @{username} type={dialog_type}", flush=True)
                continue
            try:
                dialog = engine.join_public_community(
                    db, profile=profile, username=username, actor=actor
                )
                print(
                    f"JOINED_CHAT @{username} type={dialog.dialog_type} can_send={dialog.can_send_messages}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"JOIN_FAILED @{username} {type(exc).__name__}", flush=True)
                if type(exc).__name__ == "FloodWaitError":
                    break
            time.sleep(5)


if __name__ == "__main__":
    main()
