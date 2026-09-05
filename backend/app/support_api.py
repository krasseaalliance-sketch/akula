"""Customer support chat with one Telegram forum topic per customer."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user
from .config import get_settings
from .db import get_db
from .models import ProductCampaign, ProductCompany, ProductTeamMember, SupportMessage, SupportThread, TelegramAccountProfile, User, Workspace, WorkspaceMember
from .telegram_engine.engine import TelegramEngineService


router = APIRouter(prefix="/api/support", tags=["support"])


class SupportMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    campaign_id: str | None = None


def _now() -> datetime:
    return datetime.utcnow()


def _workspace(db: Session, user: User) -> Workspace:
    workspace = db.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id, WorkspaceMember.status == "ACTIVE")
        .order_by(Workspace.created_at)
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _campaign_title(db: Session, user: User, campaign_id: str | None) -> tuple[str | None, str | None]:
    if not campaign_id:
        return None, None
    campaign = db.scalar(select(ProductCampaign).join(ProductTeamMember, ProductTeamMember.campaign_id == ProductCampaign.id).where(ProductCampaign.id == campaign_id, ProductTeamMember.user_id == user.id, ProductTeamMember.status == "ACTIVE"))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    company = db.get(ProductCompany, campaign.company_id)
    return campaign.id, campaign.name or (company.name if company else "Campaign")


def _thread(db: Session, user: User, workspace: Workspace, campaign_id: str | None = None) -> SupportThread:
    campaign_id, title = _campaign_title(db, user, campaign_id)
    query = select(SupportThread).where(SupportThread.workspace_id == workspace.id, SupportThread.user_id == user.id)
    query = query.where(SupportThread.campaign_id == campaign_id) if campaign_id else query.where(SupportThread.campaign_id.is_(None))
    thread = db.scalar(query)
    if thread is None:
        topic_title = f"{user.name} · {title}" if title else f"{user.name} · {workspace.name}"
        thread = SupportThread(workspace_id=workspace.id, user_id=user.id, campaign_id=campaign_id, topic_title=topic_title[:240])
        db.add(thread)
        db.flush()
    return thread


def _message_view(row: SupportMessage) -> dict[str, Any]:
    return {"id": row.id, "sender_type": row.sender_type, "content": row.content, "created_at": row.created_at.isoformat(), "telegram_status": row.telegram_status}


def _telegram_target(db: Session, workspace: Workspace) -> TelegramAccountProfile | None:
    settings = get_settings()
    query = select(TelegramAccountProfile).where(TelegramAccountProfile.workspace_id == workspace.id, TelegramAccountProfile.authorization_status == "AUTHORIZED")
    if settings.telegram_support_profile_id:
        query = query.where(TelegramAccountProfile.id == settings.telegram_support_profile_id)
    return db.scalar(query.order_by(TelegramAccountProfile.created_at.desc()))


def _forward_to_telegram(db: Session, thread: SupportThread, message: SupportMessage, user: User, workspace: Workspace) -> None:
    settings = get_settings()
    if not settings.telegram_operator_notifications_enabled or not settings.telegram_support_group_id:
        message.telegram_status = "NOT_CONFIGURED"
        return
    profile = _telegram_target(db, workspace)
    if profile is None:
        message.telegram_status = "NO_AUTHORIZED_PROFILE"
        return
    payload = ("🟢 SCOUT SUPPORT\n" f"Кабинет: {workspace.name} ({workspace.slug})\n" f"Пользователь: {user.name} <{user.email}>\n" f"User ID: {user.id}\n" f"Время: {_now().isoformat()} UTC\n\n" f"{message.content}")
    try:
        telegram = TelegramEngineService()
        if not thread.telegram_thread_id:
            topic_title = thread.topic_title or f"{user.name} · {workspace.slug}"
            thread.telegram_thread_id = telegram.create_forum_topic(profile=profile, target=settings.telegram_support_group_id, title=topic_title)
        external_id = telegram.send_operator_notification(profile=profile, content=payload, target=settings.telegram_support_group_id, thread_id=thread.telegram_thread_id)
        message.telegram_status = "SENT" if external_id else "NOT_SENT"
        message.telegram_message_id = external_id
        thread.telegram_chat_id = settings.telegram_support_group_id
    except Exception as exc:  # support remains usable if Telegram is temporarily unavailable
        message.telegram_status = "FAILED"
        message.telegram_error = type(exc).__name__[:240]


@router.get("/thread")
def get_thread(campaign_id: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace = _workspace(db, user)
    thread = _thread(db, user, workspace, campaign_id)
    messages = db.scalars(select(SupportMessage).where(SupportMessage.thread_id == thread.id).order_by(SupportMessage.created_at.asc())).all()
    db.commit()
    settings = get_settings()
    return {"thread_id": thread.id, "campaign_id": thread.campaign_id, "topic_title": thread.topic_title, "workspace": workspace.name, "telegram": {"configured": bool(settings.telegram_operator_notifications_enabled and settings.telegram_support_group_id), "chat_id": settings.telegram_support_group_id}, "messages": [_message_view(row) for row in messages]}


@router.post("/messages", status_code=201)
def create_message(payload: SupportMessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace = _workspace(db, user)
    thread = _thread(db, user, workspace, payload.campaign_id)
    message = SupportMessage(thread_id=thread.id, sender_id=user.id, sender_type="CUSTOMER", content=payload.content.strip())
    thread.last_message_at = _now()
    db.add(message)
    db.commit()
    db.refresh(message)
    _forward_to_telegram(db, thread, message, user, workspace)
    db.commit()
    return _message_view(message) | {"thread_id": thread.id}
