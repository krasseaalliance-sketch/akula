"""Discover public Bali groups and join only GROUP/SUPERGROUP entities."""

from __future__ import annotations

import time

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TelegramAccountProfile, TelegramDialog, Workspace
from app.service_scheduler import actor_for
from app.telegram_engine.engine import TelegramEngineService, _run


QUERIES = (
    "русские на Бали",
    "Бали чат",
    "Bali русские",
    "Бали экспаты",
    "Убуд русские",
    "Чангу русские",
    "Bali travel русские",
)
EXCLUDED = (
    "bot",
    "guide",
    "объяв",
    "барахол",
    "обменник",
    "реклама",
    "турфирм",
    "магазин",
)


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
        if profile is None:
            raise RuntimeError("TELEGRAM_AUTH_REQUIRED")
        actor = actor_for(workspace, db)
        engine = TelegramEngineService()
        found = {}
        for query in QUERIES:
            try:
                rows = _run(engine._client_for_profile(profile).search_communities(query))
            except Exception as exc:  # noqa: BLE001
                print(f"SEARCH_FAILED {query!r} {type(exc).__name__}", flush=True)
                continue
            for item in rows:
                username = (item.username or "").lstrip("@").strip()
                haystack = f"{username} {item.title}".casefold()
                if not username or item.dialog_type not in {"GROUP", "SUPERGROUP"}:
                    continue
                if any(term in haystack for term in EXCLUDED):
                    continue
                found[username.casefold()] = item

        joined = {
            item.username.casefold()
            for item in db.scalars(
                select(TelegramDialog).where(
                    TelegramDialog.integration_account_id == profile.integration_account_id,
                    TelegramDialog.username.is_not(None),
                    TelegramDialog.is_joined.is_(True),
                )
            ).all()
            if item.username
        }
        print(
            "FOUND_CHATS "
            + str([(item.username, item.title, item.dialog_type) for item in found.values()]),
            flush=True,
        )
        attempts = 0
        for key, item in found.items():
            if key in joined:
                continue
            try:
                dialog = engine.join_public_community(
                    db, profile=profile, username=item.username or key, actor=actor
                )
                print(
                    f"JOINED_CHAT @{dialog.username} type={dialog.dialog_type} can_send={dialog.can_send_messages}",
                    flush=True,
                )
                attempts += 1
                time.sleep(5)
                if attempts >= 5:
                    break
            except Exception as exc:  # noqa: BLE001
                print(f"JOIN_FAILED @{item.username or key} {type(exc).__name__}", flush=True)
                if type(exc).__name__ == "FloodWaitError":
                    break


if __name__ == "__main__":
    main()
