from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user, require_perm
from .db import get_db
from .dialog_triage import DialogTriageService, TriageConflict, slugify
from .dialog_triage_schemas import (
    BatchSaveRequest,
    BulkActionRequest,
    CollectionCreateRequest,
    DecisionPatchRequest,
    ReturnToQueueRequest,
    TagCreateRequest,
)
from .models import (
    DialogTriageCollection,
    DialogTriageTag,
    TelegramAccountProfile,
    TelegramDialog,
    User,
)
from .services import accessible_workspace_ids, audit

router = APIRouter(prefix="/api/dialog-triage", tags=["dialog-triage"])
service = DialogTriageService()


def _workspace(db: Session, user: User, workspace_id: str | None) -> str:
    workspace_ids = accessible_workspace_ids(db, user.id)
    selected = workspace_id or (workspace_ids[0] if workspace_ids else None)
    if selected is None or selected not in workspace_ids:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return selected


def _context(db: Session, user: User, workspace_id: str | None, account_id: str | None, *, write: bool = False) -> tuple[str, TelegramAccountProfile]:
    selected_workspace = _workspace(db, user, workspace_id)
    require_perm(db, user, selected_workspace, "lead.edit" if write else "lead.view")
    try:
        return selected_workspace, service.account(db, workspace_id=selected_workspace, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _dialog(db: Session, user: User, workspace_id: str, account: TelegramAccountProfile, dialog_id: str) -> TelegramDialog:
    dialog = db.scalar(
        select(TelegramDialog).where(
            TelegramDialog.id == dialog_id,
            TelegramDialog.workspace_id == workspace_id,
            TelegramDialog.integration_account_id == account.integration_account_id,
        )
    )
    if dialog is None:
        raise HTTPException(status_code=404, detail="Telegram dialog not found")
    return dialog


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, TriageConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/next-batch")
def next_batch(
    workspace_id: str | None = None,
    account_id: str | None = None,
    limit: int = Query(30, ge=10, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id)
    try:
        return service.next_batch(db, workspace_id=workspace, account_id=account.id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/progress")
def progress(
    workspace_id: str | None = None,
    account_id: str | None = None,
    batch_size: int = Query(30, ge=10, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id)
    try:
        return service.progress(db, workspace_id=workspace, account_id=account.id, batch_size=batch_size)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/batch")
def save_batch(
    payload: BatchSaveRequest,
    workspace_id: str | None = None,
    account_id: str | None = None,
    limit: int = Query(30, ge=10, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id, write=True)
    dialog_ids = [item.dialog_id for item in payload.decisions]
    dialogs = list(
        db.scalars(
            select(TelegramDialog).where(
                TelegramDialog.id.in_(dialog_ids),
                TelegramDialog.workspace_id == workspace,
                TelegramDialog.integration_account_id == account.integration_account_id,
            )
        ).all()
    )
    dialog_by_id = {item.id: item for item in dialogs}
    if len(dialog_by_id) != len(set(dialog_ids)):
        raise HTTPException(status_code=404, detail="One or more dialogs are not available in this account")
    try:
        saved = []
        for item in payload.decisions:
            saved.append(service.save_one(db, workspace_id=workspace, account_id=account.id, dialog=dialog_by_id[item.dialog_id], actor_id=user.id, payload=item.model_dump()))
        downstream = service.refresh_downstream(db, workspace_id=workspace, account_id=account.id, decisions=saved, actor_id=user.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    result: dict[str, Any] = {"saved": len(saved), "decisions": [service.decision_payload(db, item) for item in saved], "progress": service.progress(db, workspace_id=workspace, account_id=account.id, batch_size=limit), "downstream": downstream}
    if payload.advance:
        result["next_batch"] = service.next_batch(db, workspace_id=workspace, account_id=account.id, limit=limit)
        if not result["next_batch"]["dialogs"]:
            result["completion"] = result["next_batch"].get("completion")
    return result


@router.get("/reviewed")
def reviewed(
    workspace_id: str | None = None,
    account_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id)
    try:
        return service.reviewed(db, workspace_id=workspace, account_id=account.id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/collections")
def list_collections(
    workspace_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace = _workspace(db, user, workspace_id)
    require_perm(db, user, workspace, "lead.view")
    service.ensure_system_collections(db, workspace)
    db.commit()
    return list(db.scalars(select(DialogTriageCollection).where(DialogTriageCollection.workspace_id == workspace).order_by(DialogTriageCollection.name)).all())


@router.get("/tags")
def list_tags(
    workspace_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace = _workspace(db, user, workspace_id)
    require_perm(db, user, workspace, "lead.view")
    return list(db.scalars(select(DialogTriageTag).where(DialogTriageTag.workspace_id == workspace).order_by(DialogTriageTag.name)).all())


@router.get("/{dialog_id}")
def triage_dialog(
    dialog_id: str,
    workspace_id: str | None = None,
    account_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id)
    dialog = _dialog(db, user, workspace, account, dialog_id)
    return service.card(db, dialog=dialog, account_id=account.id)


@router.patch("/{dialog_id}")
def patch_triage_dialog(
    dialog_id: str,
    payload: DecisionPatchRequest,
    workspace_id: str | None = None,
    account_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id, write=True)
    dialog = _dialog(db, user, workspace, account, dialog_id)
    values = {key: value for key, value in payload.model_dump().items() if value is not None}
    values["expected_version"] = payload.expected_version
    try:
        decision = service.save_one(db, workspace_id=workspace, account_id=account.id, dialog=dialog, actor_id=user.id, payload=values, allow_existing=True)
        downstream = service.refresh_downstream(db, workspace_id=workspace, account_id=account.id, decisions=[decision], actor_id=user.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"decision": service.decision_payload(db, decision), "downstream": downstream}


@router.post("/{dialog_id}/return-to-queue")
def return_to_queue(
    dialog_id: str,
    payload: ReturnToQueueRequest,
    workspace_id: str | None = None,
    account_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id, write=True)
    dialog = _dialog(db, user, workspace, account, dialog_id)
    try:
        decision = service.return_to_queue(db, workspace_id=workspace, account_id=account.id, dialog=dialog, actor_id=user.id, expected_version=payload.expected_version)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return service.decision_payload(db, decision)


@router.post("/bulk-action")
def bulk_action(
    payload: BulkActionRequest,
    workspace_id: str | None = None,
    account_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace, account = _context(db, user, workspace_id, account_id, write=True)
    dialogs = list(
        db.scalars(
            select(TelegramDialog).where(
                TelegramDialog.id.in_(payload.dialog_ids),
                TelegramDialog.workspace_id == workspace,
                TelegramDialog.integration_account_id == account.integration_account_id,
            )
        ).all()
    )
    if len(dialogs) != len(set(payload.dialog_ids)):
        raise HTTPException(status_code=404, detail="One or more dialogs are not available in this account")
    try:
        decisions = service.bulk_action(db, workspace_id=workspace, account_id=account.id, dialogs=dialogs, actor_id=user.id, action=payload.action, collection_slug=payload.collection_slug, tag_slug=payload.tag_slug, reason=payload.needs_context_reason, confirm_overwrite=payload.confirm_overwrite)
        downstream = service.refresh_downstream(db, workspace_id=workspace, account_id=account.id, decisions=decisions, actor_id=user.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"updated": len(decisions), "decisions": [service.decision_payload(db, item) for item in decisions], "progress": service.progress(db, workspace_id=workspace, account_id=account.id), "downstream": downstream}


@router.post("/collections", status_code=201)
def create_collection(
    payload: CollectionCreateRequest,
    workspace_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace = _workspace(db, user, workspace_id)
    require_perm(db, user, workspace, "lead.edit")
    slug = payload.slug or slugify(payload.name)
    existing = db.scalar(select(DialogTriageCollection).where(DialogTriageCollection.workspace_id == workspace, DialogTriageCollection.slug == slug))
    if existing:
        raise HTTPException(status_code=409, detail="Collection slug already exists")
    collection = DialogTriageCollection(workspace_id=workspace, name=payload.name, slug=slug, is_system=False)
    db.add(collection)
    audit(db, workspace_id=workspace, actor_id=user.id, action="dialog_triage.collection.create", entity_type="DialogTriageCollection", entity_id=collection.id, after={"name": payload.name, "slug": slug})
    db.commit()
    db.refresh(collection)
    return collection


@router.post("/tags", status_code=201)
def create_tag(
    payload: TagCreateRequest,
    workspace_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace = _workspace(db, user, workspace_id)
    require_perm(db, user, workspace, "lead.edit")
    slug = payload.slug or slugify(payload.name)
    existing = db.scalar(select(DialogTriageTag).where(DialogTriageTag.workspace_id == workspace, DialogTriageTag.slug == slug))
    if existing:
        raise HTTPException(status_code=409, detail="Tag slug already exists")
    tag = DialogTriageTag(workspace_id=workspace, name=payload.name, slug=slug)
    db.add(tag)
    audit(db, workspace_id=workspace, actor_id=user.id, action="dialog_triage.tag.create", entity_type="DialogTriageTag", entity_id=tag.id, after={"name": payload.name, "slug": slug})
    db.commit()
    db.refresh(tag)
    return tag
