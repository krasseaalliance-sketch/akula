"""Create/update the explicit Telegram dialog folder for the Bali lead set."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


TARGETS = (
    "voprosBali",
    "balichat",
    "russians_in_bali",
    "Chatik_bali",
    "bali_russia_choogl",
    "russians_bali_chat",
    "russkie_na_bali",
    "RusinBali",
    "russianbalicomm",
    "bali_russians",
    "RussianratsinBali",
    "russiansinbali",
    "lekarstva_bali",
    "baliktoletit_life",
    "events_travels_group",
    "balirental",
    "balichatnash",
)
TITLE = "\u041b\u0438\u0434\u044b \u0411\u0430\u043b\u0438"


async def update_folder(client) -> tuple[int, int]:
    from telethon import functions, types

    await client._connect()
    try:
        peers = []
        for username in TARGETS:
            entity = await client._client.get_entity(username)
            if client._dialog_type(entity) not in {"GROUP", "SUPERGROUP"}:
                continue
            access_hash = getattr(entity, "access_hash", None)
            if access_hash is None:
                continue
            peers.append(types.InputPeerChannel(channel_id=int(entity.id), access_hash=int(access_hash)))

        filters = await client._client(functions.messages.GetDialogFiltersRequest())
        existing = None
        used_ids: set[int] = set()
        for item in getattr(filters, "filters", []):
            item_id = getattr(item, "id", None)
            if item_id is not None:
                used_ids.add(int(item_id))
            item_title = getattr(getattr(item, "title", None), "text", None) or ""
            if item_title == TITLE:
                existing = item

        folder_id = int(getattr(existing, "id", 0)) if existing is not None else next(
            item_id for item_id in range(2, 100) if item_id not in used_ids
        )
        folder = types.DialogFilter(
            id=folder_id,
            title=types.TextWithEntities(text=TITLE, entities=[]),
            pinned_peers=[],
            include_peers=peers,
            exclude_peers=[],
            contacts=False,
            non_contacts=False,
            groups=False,
            broadcasts=False,
            bots=False,
            exclude_muted=False,
            exclude_read=False,
            exclude_archived=False,
        )
        await client._client(functions.messages.UpdateDialogFilterRequest(id=folder_id, filter=folder))
        return folder_id, len(peers)
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
        folder_id, peer_count = asyncio.run(update_folder(client))
        print(f"TELEGRAM_FOLDER_UPDATED title={TITLE.encode('unicode_escape').decode()} id={folder_id} peers={peer_count}", flush=True)


if __name__ == "__main__":
    main()
