"""Cancel pending Bali posts and remove the malformed preview message."""

from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Campaign, Publication, PublicationJob, TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


def main() -> None:
    with SessionLocal() as db:
        campaign = db.scalar(select(Campaign).where(
            Campaign.geography.ilike("%Bali%"), Campaign.status == "ACTIVE"
        ).order_by(Campaign.created_at))
        cancelled = 0
        for publication in db.scalars(select(Publication).where(
            Publication.campaign_id == campaign.id,
            Publication.status == "QUEUED",
        )):
            publication.status = "CANCELLED"
            job = db.scalar(select(PublicationJob).where(PublicationJob.publication_id == publication.id))
            if job:
                job.status = "CANCELLED"
                job.cancelled_at = datetime.utcnow()
            cancelled += 1
        db.commit()

        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        profile = db.scalar(select(TelegramAccountProfile).where(
            TelegramAccountProfile.workspace_id == workspace.id,
            TelegramAccountProfile.username == "Alexey_Mifanyuk",
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        ))
        client = TelegramEngineService()._client_for_profile(profile)

        async def remove_preview() -> None:
            await client._connect()
            try:
                await client._client.delete_messages("-5462252245", [638288])
            finally:
                await client._client.disconnect()

        try:
            asyncio.run(remove_preview())
            preview = "DELETED"
        except Exception as exc:  # noqa: BLE001
            preview = type(exc).__name__
        print(f"CANCELLED {cancelled} MALFORMED_PREVIEW {preview}", flush=True)


if __name__ == "__main__":
    main()
