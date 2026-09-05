from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .asmet_processing import AsmetProcessingResult, process_max_message
from .asmet_queries import persist_creator_history_report
from .config import get_settings
from .models import ConstructiveOrganization, TelegramAccountProfile, TelegramDialog, User, Workspace
from .telegram_engine.engine import TelegramEngineService


def sync_max_once(
    db: Session,
    *,
    organization_id: str,
    external_chat_id: str,
    profile_id: str | None = None,
    actor_id: str | None = None,
    max_messages: int = 100,
    since: datetime | None = None,
    historical: bool = False,
) -> dict[str, Any]:
    """Poll an explicitly configured MAX work chat and process current messages."""
    organization = db.get(ConstructiveOrganization, organization_id)
    if organization is None:
        raise LookupError("constructive organization not found")
    profile_query = select(TelegramAccountProfile).where(TelegramAccountProfile.workspace_id == organization.workspace_id)
    if profile_id:
        profile_query = profile_query.where(TelegramAccountProfile.id == profile_id)
    profile = db.scalar(profile_query.order_by(TelegramAccountProfile.created_at.asc()))
    if profile is None:
        raise LookupError("TELEGRAM_ASMET_PROFILE_NOT_FOUND")
    actor = db.get(User, actor_id) if actor_id else None
    if actor is None:
        workspace = db.get(Workspace, organization.workspace_id)
        actor = db.get(User, workspace.owner_id) if workspace else None
    if actor is None:
        raise LookupError("ASMET_SYNC_ACTOR_NOT_FOUND")
    dialog = db.scalar(select(TelegramDialog).where(
        TelegramDialog.integration_account_id == profile.integration_account_id,
        TelegramDialog.external_dialog_id == external_chat_id,
    ))
    if dialog is None:
        dialog = TelegramDialog(
            workspace_id=profile.workspace_id,
            integration_account_id=profile.integration_account_id,
            external_dialog_id=external_chat_id,
            title="ASmeT MAX work chat",
            dialog_type="GROUP",
            is_joined=True,
            can_view_history=True,
            can_send_messages=True,
        )
        db.add(dialog)
        db.flush()
    records = TelegramEngineService().sync_messages(
        db,
        profile=profile,
        dialog=dialog,
        actor=actor,
        max_messages=max_messages,
        since=since or datetime.utcnow() - timedelta(days=2),
    )
    results: list[AsmetProcessingResult] = []
    for record in records:
        if record.direction != "INBOUND" or not record.text:
            continue
        results.append(process_max_message(
            db,
            organization_id=organization_id,
            external_chat_id=external_chat_id,
            external_message_id=record.external_message_id,
            text=record.text,
            sent_at=record.sent_at,
            edited_at=record.edited_at,
            historical=historical,
            profile=profile,
        ))
    return {
        "organization_id": organization_id,
        "chat_id": external_chat_id,
        "messages_seen": len(records),
        "messages_processed": len(results),
        "rows_inserted": sum(item.rows_inserted for item in results),
        "acknowledgements_required": sum(item.acknowledgement_required for item in results),
        "rejections": [rejection for item in results for rejection in item.rejections],
        "live_send_enabled": get_settings().telegram_operator_notifications_enabled,
    }


def backfill_max_history(
    db: Session,
    *,
    organization_id: str,
    external_chat_id: str,
    period_start: datetime,
    period_end: datetime,
    profile_id: str | None = None,
    actor_id: str | None = None,
    max_messages: int = 1000,
) -> dict[str, Any]:
    """Import a bounded historical period without acknowledgements or group sends."""
    result = sync_max_once(
        db,
        organization_id=organization_id,
        external_chat_id=external_chat_id,
        profile_id=profile_id,
        actor_id=actor_id,
        max_messages=max_messages,
        since=period_start,
        historical=True,
    )
    actor = db.get(User, actor_id) if actor_id else None
    if actor is None:
        workspace = db.get(Workspace, db.get(ConstructiveOrganization, organization_id).workspace_id)
        actor = db.get(User, workspace.owner_id) if workspace else None
    if actor is None:
        raise LookupError("ASMET_SYNC_ACTOR_NOT_FOUND")
    report = persist_creator_history_report(db, actor, organization_id, period_start, period_end)
    return {**result, "history_report": report}
