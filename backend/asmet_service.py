"""ASmeT MAX polling service.

The service is safe-by-configuration: without an explicit chat id and an
authorized Telegram profile it records an error and performs no read or send.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from sqlalchemy import select

from app.asmet_service import backfill_max_history, sync_max_once
from app.config import get_settings
from app.models import ConstructiveOrganization
from app.service_scheduler import IndependentServiceScheduler, TickResult, default_service_specs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("asmet-service")


def run_tick(db, workspace) -> TickResult:
    settings = get_settings()
    chat_id = settings.telegram_asmet_chat_id
    if not chat_id:
        raise RuntimeError("ASMET_CHAT_NOT_CONFIGURED")
    organization = db.scalar(select(ConstructiveOrganization).where(
        ConstructiveOrganization.workspace_id == workspace.id,
        ConstructiveOrganization.status == "ACTIVE",
    ))
    if organization is None:
        raise RuntimeError("CONSTRUCTIVE_ORGANIZATION_NOT_CONFIGURED")
    history_from = os.getenv("ASMET_BACKFILL_FROM")
    history_to = os.getenv("ASMET_BACKFILL_TO")
    if history_from and history_to:
        result = backfill_max_history(db, organization_id=organization.id, external_chat_id=chat_id, period_start=datetime.fromisoformat(history_from), period_end=datetime.fromisoformat(history_to), profile_id=settings.telegram_asmet_profile_id, actor_id=workspace.owner_id)
    else:
        result = sync_max_once(db, organization_id=organization.id, external_chat_id=chat_id, profile_id=settings.telegram_asmet_profile_id, actor_id=workspace.owner_id)
    return TickResult(stats=result)


if __name__ == "__main__":
    IndependentServiceScheduler(default_service_specs()["asmet"], run_tick).run_forever()
