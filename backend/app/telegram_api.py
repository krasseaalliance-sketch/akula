from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import current_user, require_perm, require_workspace
from .db import get_db
from .models import (
    Community,
    IntegrationAccount,
    Lead,
    TelegramAccountIncident,
    TelegramAccountProfile,
    TelegramAuthorizationAttempt,
    TelegramCommunityCandidate,
    TelegramCommunitySnapshot,
    TelegramDialog,
    TelegramDiscoveryRun,
    TelegramImportRun,
    TelegramMessageRecord,
    User,
)
from .services import accessible_workspace_ids
from .telegram_engine.engine import TelegramEngineService
from .telegram_schemas import (
    AuthorizationCodeRequest,
    AuthorizationPasswordRequest,
    AuthorizationStartRequest,
    DiscoveryRequest,
    ImportRowsRequest,
    IncidentResolveRequest,
    LeadDiscoveryRequestV2,
    RulesReviewRequest,
    SafetyLockRequest,
    SyncRequest,
    TelegramAccountCreate,
    TelegramAccountResponse,
    TelegramDialogResponse,
)

router = APIRouter(prefix="/api/integrations/telegram", tags=["telegram"])
engine = TelegramEngineService()


def _profile(db: Session, user: User, account_id: str, *, manage: bool = False) -> TelegramAccountProfile:
    profile = db.get(TelegramAccountProfile, account_id)
    if profile is None or profile.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Telegram account not found")
    if manage:
        require_perm(db, user, profile.workspace_id, "integration.manage")
    return profile


def _community(db: Session, user: User, community_id: str) -> Community:
    community = db.get(Community, community_id)
    if community is None or community.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Community not found")
    return community


def _response(db: Session, profile: TelegramAccountProfile) -> dict[str, Any]:
    integration = db.get(IntegrationAccount, profile.integration_account_id)
    return {
        "id": profile.id,
        "workspace_id": profile.workspace_id,
        "integration_account_id": profile.integration_account_id,
        "display_name": integration.display_name if integration else "Telegram account",
        "username": profile.username,
        "phone_masked": profile.phone_masked,
        "authorization_status": profile.authorization_status,
        "safety_status": profile.safety_status,
        "connection_status": profile.connection_status,
        "last_successful_sync_at": profile.last_successful_sync_at,
        "flood_wait_until": profile.flood_wait_until,
        "manual_unlock_required": profile.manual_unlock_required,
        "safety_lock": bool(integration and integration.safety_lock),
    }


def _error(exc: Exception) -> HTTPException:
    message = str(exc)
    status = 422 if message in {"INVALID_CODE", "INVALID_2FA_PASSWORD"} else 409
    return HTTPException(status_code=status, detail=message)


@router.get("/accounts", response_model=list[TelegramAccountResponse])
def list_accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    profiles = list(db.scalars(select(TelegramAccountProfile).where(
        TelegramAccountProfile.workspace_id.in_(accessible_workspace_ids(db, user.id))
    ).order_by(TelegramAccountProfile.created_at.desc())).all())
    return [_response(db, profile) for profile in profiles]


@router.post("/accounts", response_model=TelegramAccountResponse, status_code=201)
def create_account(payload: TelegramAccountCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, payload.workspace_id)
    require_perm(db, user, payload.workspace_id, "integration.manage")
    profile = engine.create_account(db, workspace_id=payload.workspace_id, display_name=payload.display_name,
                                    phone=payload.phone, api_credential_reference=payload.api_credential_reference,
                                    actor=user)
    return _response(db, profile)


@router.get("/accounts/{account_id}", response_model=TelegramAccountResponse)
def get_account(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _response(db, _profile(db, user, account_id))


@router.patch("/accounts/{account_id}", response_model=TelegramAccountResponse)
def patch_account(account_id: str, payload: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    integration = db.get(IntegrationAccount, profile.integration_account_id)
    if integration and isinstance(payload.get("display_name"), str):
        integration.display_name = payload["display_name"]
    db.commit()
    return _response(db, profile)


@router.post("/accounts/{account_id}/authorize/start")
def authorize_start(account_id: str, payload: AuthorizationStartRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    try:
        attempt = engine.start_authorization(db, profile=profile, phone=payload.phone, actor=user)
    except Exception as exc:
        raise _error(exc) from exc
    return {"attempt_id": attempt.id, "status": attempt.status, "expires_at": attempt.expires_at}


@router.post("/accounts/{account_id}/authorize/code", response_model=TelegramAccountResponse)
def authorize_code(account_id: str, payload: AuthorizationCodeRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    attempt = db.get(TelegramAuthorizationAttempt, payload.attempt_id)
    if attempt is None or attempt.telegram_account_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Authorization attempt not found")
    try:
        return _response(db, engine.complete_authorization(db, attempt=attempt, code=payload.code, actor=user))
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/accounts/{account_id}/authorize/password", response_model=TelegramAccountResponse)
def authorize_password(account_id: str, payload: AuthorizationPasswordRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    attempt = db.get(TelegramAuthorizationAttempt, payload.attempt_id)
    if attempt is None or attempt.telegram_account_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Authorization attempt not found")
    try:
        return _response(db, engine.complete_password_authorization(db, attempt=attempt, password=payload.password, actor=user))
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/accounts/{account_id}/disconnect", response_model=TelegramAccountResponse)
def disconnect_account(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    engine.disconnect(db, profile=profile, actor=user)
    return _response(db, profile)


@router.post("/accounts/{account_id}/health-check")
def health_check(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    return {"healthy": engine.health_check(db, profile=profile, actor=user), "account": _response(db, profile)}


@router.post("/accounts/{account_id}/safety-lock", response_model=TelegramAccountResponse)
def safety_lock(account_id: str, payload: SafetyLockRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    engine.create_incident(db, profile=profile, incident_type="OTHER", severity="HIGH", details={"reason": payload.reason}, actor=user)
    return _response(db, profile)


@router.post("/accounts/{account_id}/unlock", response_model=TelegramAccountResponse)
def unlock_account(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, account_id, manage=True)
    try:
        engine.unlock(db, profile=profile, actor=user)
    except Exception as exc:
        raise _error(exc) from exc
    return _response(db, profile)


@router.get("/dialogs", response_model=list[TelegramDialogResponse])
def list_dialogs(account_id: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(TelegramDialog).where(TelegramDialog.workspace_id.in_(accessible_workspace_ids(db, user.id)))
    if account_id:
        profile = _profile(db, user, account_id)
        query = query.where(TelegramDialog.integration_account_id == profile.integration_account_id)
    return list(db.scalars(query.order_by(TelegramDialog.title)).all())


@router.get("/dialogs/{dialog_id}", response_model=TelegramDialogResponse)
def get_dialog(dialog_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dialog = db.get(TelegramDialog, dialog_id)
    if dialog is None or dialog.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Telegram dialog not found")
    return dialog


@router.post("/dialogs/sync")
def sync_dialogs(payload: SyncRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, payload.account_id, manage=True)
    try:
        return engine.sync_dialogs(db, profile=profile, actor=user)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/dialogs/{dialog_id}/import-community")
def import_dialog_community(dialog_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dialog = db.get(TelegramDialog, dialog_id)
    if dialog is None or dialog.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Telegram dialog not found")
    require_perm(db, user, dialog.workspace_id, "integration.manage")
    return engine.import_community(db, workspace_id=dialog.workspace_id, actor=user, payload={
        "account_id": dialog.integration_account_id, "title": dialog.title, "username": dialog.username,
        "url": f"https://t.me/{dialog.username}" if dialog.username else None, "external_id": dialog.external_dialog_id,
        "language": "ru", "idempotency_key": f"dialog-import:{dialog.id}", "dry_run": False,
    })


@router.post("/imports/preview")
def preview_import(payload: ImportRowsRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_id = next(iter(accessible_workspace_ids(db, user.id)), None)
    if workspace_id is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    require_perm(db, user, workspace_id, "integration.manage")
    return engine.import_rows(db, workspace_id=workspace_id, actor=user, rows=payload.rows,
                              idempotency_key=payload.idempotency_key, account_id=payload.account_id, dry_run=payload.dry_run)


@router.post("/discovery/run")
def run_discovery(payload: DiscoveryRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, payload.account_id, manage=True)
    try:
        return engine.discover(db, profile=profile, actor=user, query=payload.query, discovery_profile_id=payload.profile_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/discovery/runs")
def discovery_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(TelegramDiscoveryRun).where(TelegramDiscoveryRun.workspace_id.in_(accessible_workspace_ids(db, user.id))).order_by(TelegramDiscoveryRun.created_at.desc())).all())


@router.get("/discovery/candidates")
def discovery_candidates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(TelegramCommunityCandidate).where(TelegramCommunityCandidate.workspace_id.in_(accessible_workspace_ids(db, user.id))).order_by(TelegramCommunityCandidate.relevance_score.desc())).all())


@router.post("/discovery/candidates/{candidate_id}/accept")
def accept_candidate(candidate_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    candidate = db.get(TelegramCommunityCandidate, candidate_id)
    if candidate is None or candidate.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    require_perm(db, user, candidate.workspace_id, "integration.manage")
    return engine.decide_candidate(db, candidate=candidate, status="ACCEPTED", actor=user)


@router.post("/discovery/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    candidate = db.get(TelegramCommunityCandidate, candidate_id)
    if candidate is None or candidate.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    require_perm(db, user, candidate.workspace_id, "integration.manage")
    return engine.decide_candidate(db, candidate=candidate, status="REJECTED", actor=user)


@router.post("/communities/{community_id}/sync-rules")
def sync_rules(community_id: str, account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    community = _community(db, user, community_id)
    require_perm(db, user, community.workspace_id, "integration.manage")
    profile = _profile(db, user, account_id, manage=True)
    try:
        snapshot = engine.sync_rules(db, profile=profile, community=community, actor=user)
        analysis = engine.analyze_rules(db, community=community, actor=user)
        return {"snapshot": snapshot, "analysis": analysis}
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/communities/{community_id}/snapshots")
def rule_snapshots(community_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    community = _community(db, user, community_id)
    return list(db.scalars(select(TelegramCommunitySnapshot).where(TelegramCommunitySnapshot.community_id == community.id).order_by(TelegramCommunitySnapshot.observed_at.desc())).all())


@router.post("/communities/{community_id}/review-rules")
def review_rules(community_id: str, payload: RulesReviewRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    community = _community(db, user, community_id)
    require_perm(db, user, community.workspace_id, "integration.manage")
    permission = engine.review_rules(db, community=community, actor=user, approved=payload.approved,
                                     allowed_content_types=payload.allowed_content_types, allowed_days=payload.allowed_days,
                                     min_interval_hours=payload.min_interval_hours, expires_at=payload.expires_at)
    return {"approved": payload.approved, "community": community, "permission": permission}


@router.post("/messages/sync")
def sync_messages(payload: SyncRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, payload.account_id, manage=True)
    if not payload.dialog_id:
        raise HTTPException(status_code=422, detail="dialog_id is required for message sync")
    dialog = db.get(TelegramDialog, payload.dialog_id)
    if dialog is None or dialog.integration_account_id != profile.integration_account_id:
        raise HTTPException(status_code=404, detail="Telegram dialog not found")
    try:
        return engine.sync_messages(db, profile=profile, dialog=dialog, actor=user, max_messages=payload.max_messages, since=payload.since)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/messages")
def list_messages(account_id: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(TelegramMessageRecord).where(TelegramMessageRecord.workspace_id.in_(accessible_workspace_ids(db, user.id)))
    if account_id:
        profile = _profile(db, user, account_id)
        query = query.where(TelegramMessageRecord.integration_account_id == profile.integration_account_id)
    return list(db.scalars(query.order_by(TelegramMessageRecord.sent_at.desc())).all())


@router.get("/messages/{message_id}")
def get_message(message_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    message = db.get(TelegramMessageRecord, message_id)
    if message is None or message.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Telegram message not found")
    return message


@router.post("/incoming/sync")
def sync_incoming(payload: SyncRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, payload.account_id, manage=True)
    try:
        return engine.sync_incoming(db, profile=profile, actor=user, dialog_id=payload.dialog_id, max_messages=payload.max_messages)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/leads/discover")
def discover_leads(payload: LeadDiscoveryRequestV2, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = _profile(db, user, payload.account_id, manage=True)
    return engine.discover_leads(db, profile=profile, actor=user, campaign_id=payload.campaign_id,
                                 dialog_id=payload.dialog_id, max_messages=payload.max_messages)


@router.get("/leads/runs")
def lead_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(TelegramImportRun).where(TelegramImportRun.workspace_id.in_(accessible_workspace_ids(db, user.id))).order_by(TelegramImportRun.created_at.desc())).all())
    return rows


@router.get("/leads/candidates")
def lead_candidates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .models import Lead
    return list(db.scalars(select(Lead).where(Lead.workspace_id.in_(accessible_workspace_ids(db, user.id)), Lead.source_platform == "TELEGRAM").order_by(Lead.created_at.desc())).all())


@router.get("/incidents")
def incidents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    account_ids = list(db.scalars(select(IntegrationAccount.id).where(IntegrationAccount.workspace_id.in_(accessible_workspace_ids(db, user.id)))).all())
    return list(db.scalars(select(TelegramAccountIncident).where(TelegramAccountIncident.integration_account_id.in_(account_ids)).order_by(TelegramAccountIncident.detected_at.desc())).all())


@router.get("/incidents/{incident_id}")
def incident(incident_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(TelegramAccountIncident, incident_id)
    if item is None or db.scalar(select(IntegrationAccount.workspace_id).where(IntegrationAccount.id == item.integration_account_id)) not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Telegram incident not found")
    return item


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str, payload: IncidentResolveRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(TelegramAccountIncident, incident_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Telegram incident not found")
    workspace_id = db.scalar(select(IntegrationAccount.workspace_id).where(IntegrationAccount.id == item.integration_account_id))
    if workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Telegram incident not found")
    require_perm(db, user, workspace_id, "integration.manage")
    return engine.resolve_incident(db, incident=item, actor=user, resolution_notes=payload.resolution_notes)


@router.get("/metrics")
def telegram_metrics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_ids = accessible_workspace_ids(db, user.id)
    account_ids = list(db.scalars(select(IntegrationAccount.id).where(IntegrationAccount.workspace_id.in_(workspace_ids))).all())
    profiles = list(db.scalars(select(TelegramAccountProfile).where(TelegramAccountProfile.workspace_id.in_(workspace_ids))).all())
    return {"metrics": {
        "telegram_accounts_total": len(profiles),
        "telegram_accounts_healthy": sum(item.safety_status == "HEALTHY" for item in profiles),
        "telegram_accounts_safety_locked": sum(item.manual_unlock_required for item in profiles),
        "telegram_dialogs_total": db.scalar(select(func.count(TelegramDialog.id)).where(TelegramDialog.integration_account_id.in_(account_ids))) or 0,
        "telegram_communities_discovered": db.scalar(select(func.count(TelegramCommunityCandidate.id)).where(TelegramCommunityCandidate.workspace_id.in_(workspace_ids))) or 0,
        "telegram_communities_approved": db.scalar(select(func.count(Community.id)).where(Community.workspace_id.in_(workspace_ids), Community.posting_status.in_(["APPROVED", "APPROVED_WITH_CONDITIONS"]))) or 0,
        "telegram_messages_synced": db.scalar(select(func.count(TelegramMessageRecord.id)).where(TelegramMessageRecord.workspace_id.in_(workspace_ids))) or 0,
        "telegram_leads_discovered": db.scalar(select(func.count(Lead.id)).where(Lead.workspace_id.in_(workspace_ids), Lead.source_platform == "TELEGRAM")) or 0,
    }}
