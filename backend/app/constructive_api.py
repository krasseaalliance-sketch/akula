from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user
from .constructive_access import constructive_role, visible_constructive_data
from .asmet_queries import answer_asmet_question, persist_creator_history_report, visible_asmet_messages
from .db import get_db
from .models import ConstructiveAsmetMessage, ConstructiveCabinet, ConstructiveCabinetInvite, ConstructiveOrganization, User
from .security import create_access_token, hash_password


@dataclass(frozen=True)
class MasterInviteResult:
    url: str
    token: str
    asmet_message_id: str


@dataclass(frozen=True)
class RegisteredMaster:
    user_id: str
    email: str
    role: str
    access_token: str


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_master_invite(
    db: Session,
    creator: User,
    organization_id: str,
    master_name: str,
    email: str,
    *,
    base_url: str,
) -> MasterInviteResult:
    if constructive_role(db, creator.id, organization_id) != "CREATOR":
        raise PermissionError("constructive.cabinet.create_master")
    if db.get(ConstructiveOrganization, organization_id) is None:
        raise LookupError("constructive organization not found")
    raw_token = secrets.token_urlsafe(32)
    invite = ConstructiveCabinetInvite(
        organization_id=organization_id,
        email=email.lower().strip(),
        role="MASTER",
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(days=7),
        created_by=creator.id,
    )
    db.add(invite)
    db.flush()
    message = ConstructiveAsmetMessage(
        organization_id=organization_id,
        external_chat_id=f"user:{invite.email}",
        external_message_id=f"invite:{invite.id}",
        text=f"{master_name}, Constructive приглашает вас в кабинет Мастера. Откройте персональную ссылку: {base_url.rstrip('/')}/constructive/register/{raw_token}",
        processed_at=datetime.utcnow(),
        status="OUTBOUND",
    )
    db.add(message)
    db.commit()
    return MasterInviteResult(f"{base_url.rstrip('/')}/constructive/register/{raw_token}", raw_token, message.id)


def register_master_invite(db: Session, token: str, name: str, password: str) -> RegisteredMaster:
    invite = db.scalar(select(ConstructiveCabinetInvite).where(ConstructiveCabinetInvite.token_hash == _hash_token(token)))
    if invite is None:
        raise ValueError("INVITE_NOT_FOUND")
    if invite.used_at is not None:
        raise ValueError("INVITE_ALREADY_USED")
    if invite.expires_at <= datetime.utcnow():
        raise ValueError("INVITE_EXPIRED")
    user = db.scalar(select(User).where(User.email == invite.email))
    if user is None:
        user = User(email=invite.email, name=name.strip(), password_hash=hash_password(password))
        db.add(user)
        db.flush()
    else:
        user.name = name.strip()
        user.password_hash = hash_password(password)
    cabinet = db.scalar(select(ConstructiveCabinet).where(ConstructiveCabinet.organization_id == invite.organization_id, ConstructiveCabinet.user_id == user.id))
    if cabinet is None:
        db.add(ConstructiveCabinet(organization_id=invite.organization_id, user_id=user.id, role="MASTER"))
    else:
        cabinet.role = "MASTER"
        cabinet.status = "ACTIVE"
    invite.used_at = datetime.utcnow()
    db.commit()
    return RegisteredMaster(user.id, user.email, "MASTER", create_access_token(user.id))


class MasterInviteIn(BaseModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=160)
    email: str


class MasterRegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=200)


class AsmetQuestionIn(BaseModel):
    organization_id: str
    question: str = Field(min_length=1, max_length=2000)
    period_start: datetime | None = None
    period_end: datetime | None = None


class AsmetHistoryReportIn(BaseModel):
    organization_id: str
    period_start: datetime
    period_end: datetime


router = APIRouter(prefix="/api/constructive", tags=["constructive"])


@router.get("/cabinets/me")
def cabinet_me(organization_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cabinet = db.scalar(select(ConstructiveCabinet).where(ConstructiveCabinet.user_id == user.id, ConstructiveCabinet.status == "ACTIVE").order_by(ConstructiveCabinet.created_at))
    if organization_id:
        cabinet = db.scalar(select(ConstructiveCabinet).where(ConstructiveCabinet.user_id == user.id, ConstructiveCabinet.organization_id == organization_id, ConstructiveCabinet.status == "ACTIVE"))
    if cabinet is None:
        raise HTTPException(status_code=404, detail="Constructive cabinet not found")
    try:
        return visible_constructive_data(db, user, cabinet.organization_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/cabinets/master-invite", status_code=201)
def issue_master_invite(payload: MasterInviteIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        result = create_master_invite(db, user, payload.organization_id, payload.name, payload.email, base_url=str(request.base_url).rstrip("/"))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"url": result.url, "invite_token": result.token, "asmet_message_id": result.asmet_message_id, "expires_in_days": 7}


@router.post("/invites/{token}/register")
def register_master(token: str, payload: MasterRegisterIn, db: Session = Depends(get_db)):
    try:
        result = register_master_invite(db, token, payload.name, payload.password)
    except ValueError as exc:
        detail = str(exc)
        status = 409 if detail in {"INVITE_ALREADY_USED", "INVITE_EXPIRED"} else 404
        raise HTTPException(status_code=status, detail=detail) from exc
    return {"user_id": result.user_id, "email": result.email, "role": result.role, "access_token": result.access_token, "redirect": "/constructive"}


@router.get("/asmet")
def asmet_history(organization_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cabinet = db.scalar(select(ConstructiveCabinet).where(ConstructiveCabinet.user_id == user.id, ConstructiveCabinet.status == "ACTIVE", *( [ConstructiveCabinet.organization_id == organization_id] if organization_id else [] )))
    if cabinet is None:
        raise HTTPException(status_code=404, detail="Constructive cabinet not found")
    try:
        return {"organization_id": cabinet.organization_id, "messages": visible_asmet_messages(db, user, cabinet.organization_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/asmet/query")
def query_asmet(payload: AsmetQuestionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        answer = answer_asmet_question(
            db,
            user,
            payload.organization_id,
            payload.question,
            period_start=payload.period_start,
            period_end=payload.period_end,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "organization_id": answer.organization_id,
        "role": answer.role,
        "recognized": answer.recognized,
        "answer": answer.text,
    }


@router.post("/asmet/history/report")
def report_asmet_history(payload: AsmetHistoryReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return persist_creator_history_report(db, user, payload.organization_id, payload.period_start, payload.period_end)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
