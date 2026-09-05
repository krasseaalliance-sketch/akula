"""Read-only inspection of operator-provided Bali chat links."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, TelegramDialog, Workspace
from app.telegram_engine.engine import TelegramEngineService


LINKS = (
    "https://t.me/baliontheway",
    "https://t.me/balibless",
    "https://t.me/bali_russia_choogl",
    "https://t.me/c/1656459620/60295",
    "https://t.me/+GYe4apNZzqVhMGVi",
    "https://t.me/+DXaf8gqY4TA4Yjg6",
    "https://t.me/+1IGkrqSElxAxMDZi",
    "https://t.me/balichatik",
    "https://t.me/+Fjv5IAdbHR44NTYy",
    "https://t.me/+aPBZkuChvwhkOGMy",
    "https://t.me/canggu_people",
    "https://t.me/networkingbali",
    "https://t.me/bali_modelling",
    "https://t.me/Nice_Bali_Trip",
    "https://t.me/toursbali",
    "https://t.me/baliannachat",
    "https://t.me/buzz_bali",
    "https://t.me/CangguLadies",
    "https://t.me/balitusa2025",
)


def public_name(link: str) -> str | None:
    match = re.search(r"t\.me/([A-Za-z0-9_]+)$", link)
    return match.group(1) if match else None


def invite_hash(link: str) -> str | None:
    match = re.search(r"t\.me/\+([A-Za-z0-9_-]+)$", link)
    return match.group(1) if match else None


def private_message_id(link: str) -> str | None:
    match = re.search(r"t\.me/c/(\d+)/(\d+)$", link)
    return f"{match.group(1)}/{match.group(2)}" if match else None


async def inspect(profile, joined_map: dict[str, TelegramDialog]) -> list[dict]:
    from telethon import functions, types
    from telethon.tl.types import ChatInvite, ChatInviteAlready, PeerChannel

    service = TelegramEngineService()
    client = service._client_for_profile(profile)
    await client._connect()
    result: list[dict] = []
    try:
        for link in LINKS:
            name = public_name(link)
            invite = invite_hash(link)
            private = private_message_id(link)
            row = {"link": link, "kind": "UNKNOWN"}
            try:
                if invite:
                    checked = await client._client(functions.messages.CheckChatInviteRequest(invite))
                    if isinstance(checked, ChatInviteAlready):
                        entity = checked.chat
                        row.update(kind="INVITE_ALREADY_JOINED", title=getattr(entity, "title", None),
                                   entity_type=client._dialog_type(entity), members=getattr(entity, "participants_count", None))
                    elif isinstance(checked, ChatInvite):
                        row.update(kind="PRIVATE_INVITE", title=checked.title,
                                   entity_type="CHANNEL" if checked.broadcast else "GROUP",
                                   members=checked.participants_count)
                    else:
                        row.update(kind=type(checked).__name__)
                elif private:
                    channel_id = int(private.split("/", 1)[0])
                    entity = await client._client.get_entity(PeerChannel(channel_id))
                    row.update(kind="PRIVATE_MESSAGE", title=getattr(entity, "title", None),
                               entity_type=client._dialog_type(entity), members=getattr(entity, "participants_count", None))
                elif name:
                    entity = await client._client.get_entity(name)
                    row.update(kind="PUBLIC", title=getattr(entity, "title", None) or name,
                               entity_type=client._dialog_type(entity), members=getattr(entity, "participants_count", None),
                               username=getattr(entity, "username", None))
                    messages = await client._client.get_messages(entity, limit=3)
                    if messages:
                        latest = messages[0]
                        row["latest"] = latest.date.isoformat() if latest.date else None
                        row["latest_text"] = (latest.message or "").replace("\n", " ")[:160]
                    dialog = joined_map.get(name.casefold())
                    if dialog:
                        row["joined"] = dialog.is_joined
                        row["can_send"] = dialog.can_send_messages
            except Exception as exc:  # noqa: BLE001
                row.update(kind="ERROR", error=type(exc).__name__)
            result.append(row)
    finally:
        await client._client.disconnect()
    return result


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        profile = db.scalar(select(TelegramAccountProfile).where(
            TelegramAccountProfile.workspace_id == workspace.id,
            TelegramAccountProfile.username == "Alexey_Mifanyuk",
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        ))
        dialogs = db.scalars(select(TelegramDialog).where(
            TelegramDialog.integration_account_id == profile.integration_account_id,
            TelegramDialog.username.is_not(None),
        )).all()
        joined_map = {dialog.username.casefold(): dialog for dialog in dialogs if dialog.username}
        for row in asyncio.run(inspect(profile, joined_map)):
            print(row, flush=True)


if __name__ == "__main__":
    main()
