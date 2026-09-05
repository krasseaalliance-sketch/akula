import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .human_writing.engine import HumanWritingEngine
from .integrations import MockLeadSourceAdapter, MockMessageGenerationProvider, validate_message
from .models import (
    Audience,
    AuditEvent,
    Brand,
    Campaign,
    Community,
    CommunityPermission,
    Company,
    Conversation,
    ConversationMessage,
    IntegrationAccount,
    Lead,
    MessageDraft,
    Offer,
    Publication,
    PublicationJob,
    TelegramAccountProfile,
    User,
    Workspace,
    WorkspaceMember,
)
from .policy import PolicyEngine
from .queue import enqueue_publication, notify_publication
from .schemas import (
    AudienceIn,
    AudienceResponse,
    BrandIn,
    BrandPatch,
    BrandResponse,
    CampaignIn,
    CampaignPatch,
    CampaignResponse,
    CommunityIn,
    CommunityPatch,
    CommunityPermissionIn,
    CommunityPermissionResponse,
    CommunityResponse,
    CompanyIn,
    CompanyPatch,
    CompanyResponse,
    ConversationResponse,
    GenerateMessageRequest,
    LeadDiscoveryRequest,
    LeadPatch,
    LeadResponse,
    LoginRequest,
    MessageResponse,
    OfferIn,
    OfferResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PublicationIn,
    PublicationResponse,
    QueueJobResponse,
    ReplyRequest,
    SafetyStateResponse,
    TokenResponse,
    UserResponse,
    WorkspaceIn,
    WorkspacePatch,
    WorkspaceResponse,
)
from .security import create_access_token, decode_access_token, verify_password
from .services import (
    ROLE_PERMISSIONS,
    accessible_workspace_ids,
    audit,
    dedupe_key,
    has_permission,
    model_dict,
    normalize_text,
    require_permission,
    role_for,
    set_system_flag,
    system_flag,
    within_interval,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_access_token(credentials.credentials) if credentials else None
    user = db.get(User, user_id) if user_id else None
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_workspace(db: Session, user: User, workspace_id: str) -> Workspace:
    if workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def require_perm(db: Session, user: User, workspace_id: str, permission: str) -> str:
    try:
        return require_permission(db, user.id, workspace_id, permission)
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}") from None


def entity_workspace_id(db: Session, entity: Any) -> str:
    if entity is None:
        return ""
    if isinstance(entity, Workspace):
        return entity.id
    if isinstance(entity, (Company, Community, Lead, Conversation, Audience, IntegrationAccount)):
        return entity.workspace_id
    if isinstance(entity, (Brand,)):
        company = db.get(Company, entity.company_id)
        return company.workspace_id if company else ""
    if isinstance(entity, Offer):
        return entity_workspace_id(db, db.get(Brand, entity.brand_id))
    if isinstance(entity, Campaign):
        return entity_workspace_id(db, db.get(Brand, entity.brand_id))
    if isinstance(entity, MessageDraft):
        return (
            entity_workspace_id(db, db.get(Campaign, entity.campaign_id))
            if entity.campaign_id
            else entity_workspace_id(db, db.get(Community, entity.community_id))
        )
    if isinstance(entity, Publication):
        return entity_workspace_id(db, db.get(MessageDraft, entity.message_draft_id))
    if isinstance(entity, PublicationJob):
        return entity_workspace_id(db, db.get(Publication, entity.publication_id))
    if isinstance(entity, CommunityPermission):
        return entity.workspace_id
    if isinstance(entity, AuditEvent):
        return entity.workspace_id
    return ""


def guard_entity(db: Session, user: User, entity: Any) -> Any:
    if entity is None or entity_workspace_id(db, entity) not in accessible_workspace_ids(
        db, user.id
    ):
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


def list_scoped(model: Any, user: User, db: Session, column: Any) -> list[Any]:
    ids = accessible_workspace_ids(db, user.id)
    return list(
        db.scalars(select(model).where(column.in_(ids)).order_by(model.created_at.desc())).all()
    )


def related_workspace_for_brand(db: Session, user: User, brand_id: str) -> tuple[Brand, str]:
    brand = guard_entity(db, user, db.get(Brand, brand_id))
    return brand, entity_workspace_id(db, brand)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.last_login_at = datetime.utcnow()
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserResponse.model_validate(user)
    )


@router.post("/auth/logout")
def logout(_: User = Depends(current_user)):
    return {"ok": True}


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user


@router.get("/workspaces", response_model=list[WorkspaceResponse])
def list_workspaces(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(Workspace)
            .where(Workspace.id.in_(accessible_workspace_ids(db, user.id)))
            .order_by(Workspace.name)
        ).all()
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
def create_workspace(
    payload: WorkspaceIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if db.scalar(select(Workspace).where(Workspace.slug == payload.slug)):
        raise HTTPException(status_code=409, detail="Workspace slug already exists")
    entity = Workspace(owner_id=user.id, **payload.model_dump())
    db.add(entity)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=entity.id, user_id=user.id, role="OWNER", joined_at=datetime.utcnow()
        )
    )
    audit(
        db,
        workspace_id=entity.id,
        actor_id=user.id,
        action="workspace.create",
        entity_type="Workspace",
        entity_id=entity.id,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/workspaces/{entity_id}", response_model=WorkspaceResponse)
def get_workspace(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return guard_entity(db, user, db.get(Workspace, entity_id))


@router.patch("/workspaces/{entity_id}", response_model=WorkspaceResponse)
def patch_workspace(
    entity_id: str,
    payload: WorkspacePatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Workspace, entity_id))
    require_perm(db, user, entity.id, "workspace.manage")
    before = model_dict(entity)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    audit(
        db,
        workspace_id=entity.id,
        actor_id=user.id,
        action="workspace.update",
        entity_type="Workspace",
        entity_id=entity.id,
        before=before,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list_scoped(Company, user, db, Company.workspace_id)


@router.post("/companies", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    workspace = require_workspace(db, user, payload.workspace_id)
    require_perm(db, user, workspace.id, "company.manage")
    entity = Company(**payload.model_dump())
    db.add(entity)
    db.flush()
    audit(
        db,
        workspace_id=entity.workspace_id,
        actor_id=user.id,
        action="company.create",
        entity_type="Company",
        entity_id=entity.id,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/companies/{entity_id}", response_model=CompanyResponse)
def get_company(entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return guard_entity(db, user, db.get(Company, entity_id))


@router.patch("/companies/{entity_id}", response_model=CompanyResponse)
def patch_company(
    entity_id: str,
    payload: CompanyPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Company, entity_id))
    require_perm(db, user, entity.workspace_id, "company.manage")
    before = model_dict(entity)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    audit(
        db,
        workspace_id=entity.workspace_id,
        actor_id=user.id,
        action="company.update",
        entity_type="Company",
        entity_id=entity.id,
        before=before,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/brands", response_model=list[BrandResponse])
def list_brands(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        item
        for item in db.scalars(select(Brand).order_by(Brand.created_at.desc())).all()
        if entity_workspace_id(db, item) in accessible_workspace_ids(db, user.id)
    ]


@router.post("/brands", response_model=BrandResponse, status_code=201)
def create_brand(
    payload: BrandIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    company = guard_entity(db, user, db.get(Company, payload.company_id))
    require_perm(db, user, company.workspace_id, "brand.manage")
    entity = Brand(**payload.model_dump())
    db.add(entity)
    db.flush()
    audit(
        db,
        workspace_id=company.workspace_id,
        actor_id=user.id,
        action="brand.create",
        entity_type="Brand",
        entity_id=entity.id,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/brands/{entity_id}", response_model=BrandResponse)
def get_brand(entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return guard_entity(db, user, db.get(Brand, entity_id))


@router.patch("/brands/{entity_id}", response_model=BrandResponse)
def patch_brand(
    entity_id: str,
    payload: BrandPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Brand, entity_id))
    require_perm(db, user, entity_workspace_id(db, entity), "brand.manage")
    before = model_dict(entity)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    audit(
        db,
        workspace_id=entity_workspace_id(db, entity),
        actor_id=user.id,
        action="brand.update",
        entity_type="Brand",
        entity_id=entity.id,
        before=before,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/offers", response_model=list[OfferResponse])
def list_offers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        item
        for item in db.scalars(select(Offer).order_by(Offer.created_at.desc())).all()
        if entity_workspace_id(db, item) in accessible_workspace_ids(db, user.id)
    ]


@router.post("/offers", response_model=OfferResponse, status_code=201)
def create_offer(
    payload: OfferIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    _brand, workspace_id = related_workspace_for_brand(db, user, payload.brand_id)
    require_perm(db, user, workspace_id, "brand.manage")
    entity = Offer(**payload.model_dump())
    db.add(entity)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="offer.create",
        entity_type="Offer",
        entity_id=entity.id,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/offers/{entity_id}", response_model=OfferResponse)
def get_offer(entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return guard_entity(db, user, db.get(Offer, entity_id))


@router.patch("/offers/{entity_id}", response_model=OfferResponse)
def patch_offer(
    entity_id: str,
    payload: OfferIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Offer, entity_id))
    require_perm(db, user, entity_workspace_id(db, entity), "brand.manage")
    for key, value in payload.model_dump(exclude={"brand_id"}).items():
        setattr(entity, key, value)
    db.commit()
    return entity


@router.get("/audiences", response_model=list[AudienceResponse])
def list_audiences(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list_scoped(Audience, user, db, Audience.workspace_id)


@router.post("/audiences", response_model=AudienceResponse, status_code=201)
def create_audience(
    payload: AudienceIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    workspace = require_workspace(db, user, payload.workspace_id)
    require_perm(db, user, workspace.id, "campaign.create")
    entity = Audience(**payload.model_dump())
    db.add(entity)
    db.commit()
    return entity


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        item
        for item in db.scalars(select(Campaign).order_by(Campaign.created_at.desc())).all()
        if entity_workspace_id(db, item) in accessible_workspace_ids(db, user.id)
    ]


@router.post("/campaigns", response_model=CampaignResponse, status_code=201)
def create_campaign(
    payload: CampaignIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    _brand, workspace_id = related_workspace_for_brand(db, user, payload.brand_id)
    require_perm(db, user, workspace_id, "campaign.create")
    if (
        payload.offer_id
        and entity_workspace_id(db, db.get(Offer, payload.offer_id)) != workspace_id
    ):
        raise HTTPException(status_code=404, detail="Offer not found")
    entity = Campaign(**payload.model_dump())
    db.add(entity)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="campaign.create",
        entity_type="Campaign",
        entity_id=entity.id,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/campaigns/{entity_id}", response_model=CampaignResponse)
def get_campaign(entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return guard_entity(db, user, db.get(Campaign, entity_id))


@router.patch("/campaigns/{entity_id}", response_model=CampaignResponse)
def patch_campaign(
    entity_id: str,
    payload: CampaignPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Campaign, entity_id))
    workspace_id = entity_workspace_id(db, entity)
    require_perm(db, user, workspace_id, "campaign.create")
    before = model_dict(entity)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="campaign.update",
        entity_type="Campaign",
        entity_id=entity.id,
        before=before,
        after=model_dict(entity),
    )
    db.commit()
    return entity


def campaign_action(entity_id: str, action: str, user: User, db: Session) -> Campaign:
    entity = guard_entity(db, user, db.get(Campaign, entity_id))
    workspace_id = entity_workspace_id(db, entity)
    require_perm(db, user, workspace_id, "campaign.publish")
    role = role_for(db, user.id, workspace_id) or "VIEWER"
    decision = PolicyEngine(
        safety_lock=system_flag(db, "SAFETY_LOCK") or system_flag(db, "EMERGENCY_STOP")
    ).can_activate_campaign(role=role, status=entity.status)
    if not decision.allowed:
        raise HTTPException(
            status_code=403 if decision.code == "FORBIDDEN" else 409, detail=decision.reason
        )
    entity.status = "ACTIVE" if action == "activate" else "PAUSED"
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action=f"campaign.{action}",
        entity_type="Campaign",
        entity_id=entity.id,
        after={"status": entity.status},
    )
    db.commit()
    return entity


@router.post("/campaigns/{entity_id}/activate", response_model=CampaignResponse)
def activate_campaign(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return campaign_action(entity_id, "activate", user, db)


@router.post("/campaigns/{entity_id}/pause", response_model=CampaignResponse)
def pause_campaign(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return campaign_action(entity_id, "pause", user, db)


@router.get("/communities", response_model=list[CommunityResponse])
def list_communities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list_scoped(Community, user, db, Community.workspace_id)


@router.post("/communities", response_model=CommunityResponse, status_code=201)
def create_community(
    payload: CommunityIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    workspace = require_workspace(db, user, payload.workspace_id)
    require_perm(db, user, workspace.id, "integration.manage")
    entity = Community(**payload.model_dump())
    db.add(entity)
    db.flush()
    audit(
        db,
        workspace_id=entity.workspace_id,
        actor_id=user.id,
        action="community.create",
        entity_type="Community",
        entity_id=entity.id,
        after=model_dict(entity),
    )
    db.commit()
    return entity


@router.get("/communities/{entity_id}", response_model=CommunityResponse)
def get_community(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return guard_entity(db, user, db.get(Community, entity_id))


@router.patch("/communities/{entity_id}", response_model=CommunityResponse)
def patch_community(
    entity_id: str,
    payload: CommunityPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Community, entity_id))
    require_perm(db, user, entity.workspace_id, "integration.manage")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    db.commit()
    return entity


def community_action(entity_id: str, state: str, user: User, db: Session) -> Community:
    entity = guard_entity(db, user, db.get(Community, entity_id))
    require_perm(db, user, entity.workspace_id, "integration.manage")
    entity.posting_status = state
    audit(
        db,
        workspace_id=entity.workspace_id,
        actor_id=user.id,
        action=f"community.{state.lower()}",
        entity_type="Community",
        entity_id=entity.id,
        after={"posting_status": state},
    )
    db.commit()
    return entity


@router.post("/communities/{entity_id}/approve", response_model=CommunityResponse)
def approve_community(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return community_action(entity_id, "APPROVED", user, db)


@router.post("/communities/{entity_id}/reject", response_model=CommunityResponse)
def reject_community(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return community_action(entity_id, "REJECTED", user, db)


@router.get("/community-permissions", response_model=list[CommunityPermissionResponse])
def list_community_permissions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        item
        for item in db.scalars(select(CommunityPermission)).all()
        if entity_workspace_id(db, item) in accessible_workspace_ids(db, user.id)
    ]


@router.post("/community-permissions", response_model=CommunityPermissionResponse, status_code=201)
def create_community_permission(
    payload: CommunityPermissionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    community = guard_entity(db, user, db.get(Community, payload.community_id))
    require_perm(db, user, community.workspace_id, "integration.manage")
    if db.scalar(
        select(CommunityPermission).where(
            CommunityPermission.community_id == community.id,
            CommunityPermission.workspace_id == community.workspace_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Community permission already exists")
    entity = CommunityPermission(
        workspace_id=community.workspace_id, approved_by=user.id, **payload.model_dump()
    )
    db.add(entity)
    db.commit()
    return entity


@router.get("/leads", response_model=list[LeadResponse])
def list_leads(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    lead_status: str | None = Query(default=None, alias="status"),
):
    stmt = (
        select(Lead)
        .where(Lead.workspace_id.in_(accessible_workspace_ids(db, user.id)))
        .order_by(Lead.created_at.desc())
    )
    if lead_status:
        stmt = stmt.where(Lead.status == lead_status)
    return list(db.scalars(stmt).all())


@router.post("/leads/discover", response_model=LeadResponse, status_code=201)
def discover_lead(
    payload: LeadDiscoveryRequest, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    workspace = require_workspace(db, user, payload.workspace_id)
    require_perm(db, user, workspace.id, "lead.edit")
    sample = MockLeadSourceAdapter().discover(payload.scenario)
    raw_text = normalize_text(payload.raw_text or sample.raw_text)
    key = dedupe_key(
        author_username=sample.author_username,
        normalized_text=raw_text,
        source_platform=payload.source_platform,
        campaign_id=payload.campaign_id,
    )
    existing_query = select(Lead).where(Lead.workspace_id == workspace.id, Lead.dedupe_key == key)
    if payload.campaign_id:
        existing_query = existing_query.where(Lead.campaign_id == payload.campaign_id)
    else:
        existing_query = existing_query.where(Lead.campaign_id.is_(None))
    existing = db.scalar(existing_query)
    if existing:
        return existing
    status_value = "NEW"
    if payload.scenario == "irrelevant":
        status_value = "REJECTED_IRRELEVANT"
    elif payload.scenario == "spam":
        status_value = "REJECTED_SPAM"
    elif payload.scenario == "do_not_contact":
        status_value = "DO_NOT_CONTACT"
    entity = Lead(
        workspace_id=workspace.id,
        campaign_id=payload.campaign_id,
        source_platform=payload.source_platform,
        source_url=sample.source_url,
        author_name=sample.author_name,
        author_username=sample.author_username,
        raw_text=raw_text,
        normalized_text=raw_text,
        detected_need=raw_text,
        status=status_value,
        score=0.8 if status_value == "NEW" else 0.0,
        confidence=0.9 if status_value == "NEW" else 1.0,
        dedupe_key=key,
    )
    db.add(entity)
    audit(
        db,
        workspace_id=workspace.id,
        actor_id=user.id,
        action="lead.discover",
        entity_type="Lead",
        entity_id=entity.id,
        after={"status": status_value, "source": payload.source_platform},
    )
    db.commit()
    return entity


@router.get("/leads/{entity_id}", response_model=LeadResponse)
def get_lead(entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return guard_entity(db, user, db.get(Lead, entity_id))


@router.patch("/leads/{entity_id}", response_model=LeadResponse)
def patch_lead(
    entity_id: str,
    payload: LeadPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Lead, entity_id))
    require_perm(db, user, entity.workspace_id, "lead.edit")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    db.commit()
    return entity


@router.post("/leads/{entity_id}/assign", response_model=LeadResponse)
def assign_lead(
    entity_id: str,
    assigned_to: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entity = guard_entity(db, user, db.get(Lead, entity_id))
    require_perm(db, user, entity.workspace_id, "lead.edit")
    if (
        db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == entity.workspace_id,
                WorkspaceMember.user_id == assigned_to,
                WorkspaceMember.status == "ACTIVE",
            )
        )
        is None
    ):
        raise HTTPException(status_code=422, detail="Assignee is not a workspace member")
    entity.assigned_to = assigned_to
    db.commit()
    return entity


@router.get("/messages", response_model=list[MessageResponse])
def list_messages(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        item
        for item in db.scalars(select(MessageDraft).order_by(MessageDraft.created_at.desc())).all()
        if entity_workspace_id(db, item) in accessible_workspace_ids(db, user.id)
    ]


@router.post("/messages/generate", response_model=MessageResponse, status_code=201)
def generate_message(
    payload: GenerateMessageRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    campaign = guard_entity(db, user, db.get(Campaign, payload.campaign_id))
    workspace_id = entity_workspace_id(db, campaign)
    require_perm(db, user, workspace_id, "campaign.create")
    offer = db.get(Offer, campaign.offer_id) if campaign.offer_id else None
    lead = guard_entity(db, user, db.get(Lead, payload.lead_id)) if payload.lead_id else None
    community = (
        guard_entity(db, user, db.get(Community, payload.community_id))
        if payload.community_id
        else None
    )
    if community and community.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Community not found")
    facts = {
        "campaign": campaign.name,
        "objective": campaign.objective,
        "offer": offer.name if offer else None,
        "verified": True,
    }
    human_result = None
    if community is not None:
        human_result = HumanWritingEngine().generate(
            db,
            workspace_id=workspace_id,
            campaign=campaign,
            community=community,
            lead=lead,
            actor_id=user.id,
        )
        generated_content = human_result.selected.content
        generated_similarity = human_result.selected.similarity_score
        generated_facts = {**facts, "persona": human_result.persona.name, "community_style": human_result.style.style_summary}
        generated_context = {"human_writing": True, "run_id": human_result.run.id, "variant_count": 3}
        generated_model = human_result.selected.model
        generated_prompt = "human-writing-v1"
    else:
        generated = MockMessageGenerationProvider().generate(
            campaign_name=campaign.name,
            objective=campaign.objective,
            facts=facts,
            language=campaign.language,
        )
        generated_content = generated.content
        generated_similarity = generated.similarity_score
        generated_facts = generated.facts_snapshot
        generated_context = generated.generation_context
        generated_model = generated.model_name
        generated_prompt = generated.prompt_version
    validation = validate_message(
        generated_content, language=campaign.language, similarity_score=generated_similarity
    )
    entity = MessageDraft(
        campaign_id=campaign.id,
        lead_id=lead.id if lead else None,
        community_id=community.id if community else None,
        audience_id=payload.audience_id,
        content=validation.normalized_content,
        created_by=user.id,
        facts_snapshot=generated_facts,
        generation_context=generated_context,
        model_name=generated_model,
        prompt_version=generated_prompt,
        similarity_score=validation.similarity_score,
        validation_status="VALID" if validation.valid else "INVALID",
        publication_type=payload.publication_type,
        human_writing_run_id=human_result.run.id if human_result else None,
        human_variant_id=human_result.selected.id if human_result else None,
        naturalness_score=human_result.selected.naturalness_score if human_result else None,
        human_similarity_score=human_result.selected.similarity_score if human_result else None,
        human_critic={"flags": human_result.selected.critic_flags, "reasons": human_result.selected.critic_reasons} if human_result else None,
    )
    db.add(entity)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="message.generate",
        entity_type="MessageDraft",
        entity_id=entity.id,
        after={"validation_status": entity.validation_status, "reasons": validation.reasons},
    )
    db.commit()
    return entity


@router.get("/messages/{entity_id}", response_model=MessageResponse)
def get_message(entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return guard_entity(db, user, db.get(MessageDraft, entity_id))


@router.patch("/messages/{entity_id}", response_model=MessageResponse)
def patch_message(
    entity_id: str, content: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    entity = guard_entity(db, user, db.get(MessageDraft, entity_id))
    workspace_id = entity_workspace_id(db, entity)
    require_perm(db, user, workspace_id, "campaign.create")
    validation = validate_message(content)
    entity.content = validation.normalized_content
    entity.validation_status = "VALID" if validation.valid else "INVALID"
    db.commit()
    return entity


def set_message_approval(entity_id: str, state: str, user: User, db: Session) -> MessageDraft:
    entity = guard_entity(db, user, db.get(MessageDraft, entity_id))
    workspace_id = entity_workspace_id(db, entity)
    require_perm(db, user, workspace_id, "message.approve")
    if state == "APPROVED" and entity.validation_status != "VALID":
        raise HTTPException(status_code=422, detail="Only valid messages can be approved")
    entity.approval_status = state
    entity.approved_by = user.id if state == "APPROVED" else None
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action=f"message.{state.lower()}",
        entity_type="MessageDraft",
        entity_id=entity.id,
        after={"approval_status": state},
    )
    db.commit()
    return entity


@router.post("/messages/{entity_id}/approve", response_model=MessageResponse)
def approve_message(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return set_message_approval(entity_id, "APPROVED", user, db)


@router.post("/messages/{entity_id}/reject", response_model=MessageResponse)
def reject_message(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return set_message_approval(entity_id, "REJECTED", user, db)


@router.get("/publications", response_model=list[PublicationResponse])
def list_publications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        item
        for item in db.scalars(select(Publication).order_by(Publication.created_at.desc())).all()
        if entity_workspace_id(db, item) in accessible_workspace_ids(db, user.id)
    ]


@router.post("/publications", response_model=PublicationResponse, status_code=201)
def create_publication(
    payload: PublicationIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    draft = guard_entity(db, user, db.get(MessageDraft, payload.message_draft_id))
    campaign = (
        guard_entity(db, user, db.get(Campaign, payload.campaign_id or draft.campaign_id))
        if payload.campaign_id or draft.campaign_id
        else None
    )
    community = (
        guard_entity(db, user, db.get(Community, payload.community_id or draft.community_id))
        if payload.community_id or draft.community_id
        else None
    )
    if campaign is None or community is None:
        raise HTTPException(status_code=422, detail="campaign_id and community_id are required")
    workspace_id = entity_workspace_id(db, campaign)
    require_perm(db, user, workspace_id, "campaign.publish")
    if entity_workspace_id(db, community) != workspace_id or (
        draft.community_id and draft.community_id != community.id
    ):
        raise HTTPException(status_code=404, detail="Publication target not found")
    duplicate = db.scalar(
        select(Publication).where(Publication.idempotency_key == payload.idempotency_key)
    )
    if duplicate:
        guard_entity(db, user, duplicate)
        return duplicate
    brand = db.get(Brand, campaign.brand_id)
    company = db.get(Company, brand.company_id) if brand else None
    offer = db.get(Offer, campaign.offer_id) if campaign.offer_id else None
    permission = db.scalar(
        select(CommunityPermission).where(
            CommunityPermission.workspace_id == workspace_id,
            CommunityPermission.community_id == community.id,
            CommunityPermission.status == "ACTIVE",
        )
    )
    integrations = list(db.scalars(select(IntegrationAccount).where(
        IntegrationAccount.workspace_id == workspace_id,
        IntegrationAccount.platform == community.platform,
    )).all())
    integration = next((item for item in integrations if item.status == "CONNECTED"), None) or (
        integrations[0] if integrations else None
    )
    telegram_account_safe = True
    if community.platform == "TELEGRAM":
        profile = db.scalar(select(TelegramAccountProfile).where(
            TelegramAccountProfile.integration_account_id == integration.id
        )) if integration else None
        now = datetime.utcnow()
        telegram_account_safe = bool(
            integration
            and profile
            and integration.status == "CONNECTED"
            and integration.health_status == "HEALTHY"
            and not integration.safety_lock
            and profile.authorization_status == "AUTHORIZED"
            and profile.safety_status == "HEALTHY"
            and not profile.manual_unlock_required
            and (profile.flood_wait_until is None or profile.flood_wait_until <= now)
        )
    sent_today = (
        db.scalar(
            select(func.count(Publication.id)).where(
                Publication.campaign_id == campaign.id, Publication.status == "PUBLISHED_CONFIRMED"
            )
        )
        or 0
    )
    decision = PolicyEngine(
        publication_mode=get_settings().publication_mode, safety_lock=system_flag(db, "SAFETY_LOCK")
    ).can_publish(
        safety_lock=system_flag(db, "EMERGENCY_STOP"),
        campaign_status=campaign.status,
        message_approved=draft.approval_status == "APPROVED",
        community_status=community.posting_status,
        sent_today=int(sent_today),
        daily_limit=campaign.daily_limit,
        workspace_status="ACTIVE" if company else "INACTIVE",
        company_status=company.status if company else "INACTIVE",
        brand_status=brand.status if brand else "INACTIVE",
        offer_status=offer.status if offer else "INACTIVE",
        permission_active=permission is not None,
        integration_healthy=(telegram_account_safe if community.platform == "TELEGRAM" else (
            integration is None or integration.health_status in {"HEALTHY", "UNKNOWN"}
        )),
        content_type_allowed=(
            draft.validation_status == "VALID"
            and (not permission or not permission.allowed_content_types
                 or draft.publication_type in permission.allowed_content_types)
        ),
        publication_date_allowed=True,
        community_interval_ok=within_interval(
            db, community.id, minutes=(permission.min_interval_hours * 60 if permission and permission.min_interval_hours else 30)
        ),
    )
    entity = Publication(
        message_draft_id=draft.id,
        campaign_id=campaign.id,
        community_id=community.id,
        idempotency_key=payload.idempotency_key,
    )
    if not decision.allowed:
        entity.status = "BLOCKED_BY_POLICY"
        entity.error_code = decision.code
        entity.error_message = decision.reason
    db.add(entity)
    db.flush()
    if decision.allowed:
        job = enqueue_publication(db, entity)
        audit(
            db,
            workspace_id=workspace_id,
            actor_id=user.id,
            action="publication.queued",
            entity_type="Publication",
            entity_id=entity.id,
            after={"job_id": job.id, "decision": decision.__dict__},
        )
    else:
        audit(
            db,
            workspace_id=workspace_id,
            actor_id=user.id,
            action="publication.blocked",
            entity_type="Publication",
            entity_id=entity.id,
            after={"decision": decision.__dict__},
        )
    db.commit()
    if decision.allowed:
        try:
            notify_publication(job.id)
        except RedisError as exc:
            # Queue notification is best effort; the worker's DB poller keeps delivery durable.
            logger.warning("publication queue notification failed: %s", exc)
    return entity


@router.get("/publications/{entity_id}", response_model=PublicationResponse)
def get_publication(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return guard_entity(db, user, db.get(Publication, entity_id))


@router.get("/queue/jobs", response_model=list[QueueJobResponse])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        job
        for job in db.scalars(
            select(PublicationJob).order_by(PublicationJob.created_at.desc())
        ).all()
        if entity_workspace_id(db, job) in accessible_workspace_ids(db, user.id)
    ]


@router.post("/publications/{entity_id}/cancel", response_model=PublicationResponse)
def cancel_publication(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    entity = guard_entity(db, user, db.get(Publication, entity_id))
    require_perm(db, user, entity_workspace_id(db, entity), "campaign.publish")
    entity.status = "CANCELLED"
    job = db.scalar(select(PublicationJob).where(PublicationJob.publication_id == entity.id))
    if job:
        job.status = "CANCELLED"
        job.cancelled_at = datetime.utcnow()
    db.commit()
    return entity


@router.post("/publications/{entity_id}/pause", response_model=PublicationResponse)
def pause_publication(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    entity = guard_entity(db, user, db.get(Publication, entity_id))
    require_perm(db, user, entity_workspace_id(db, entity), "campaign.publish")
    job = db.scalar(select(PublicationJob).where(PublicationJob.publication_id == entity.id))
    if job:
        job.status = "PAUSED"
        job.paused_at = datetime.utcnow()
    entity.status = "PAUSED"
    db.commit()
    return entity


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list_scoped(Conversation, user, db, Conversation.workspace_id)


@router.get("/conversations/{entity_id}", response_model=ConversationResponse)
def get_conversation(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return guard_entity(db, user, db.get(Conversation, entity_id))


@router.post("/conversations/{entity_id}/reply")
def reply_conversation(
    entity_id: str,
    payload: ReplyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conversation = guard_entity(db, user, db.get(Conversation, entity_id))
    require_perm(db, user, conversation.workspace_id, "lead.edit")
    message = ConversationMessage(
        conversation_id=conversation.id,
        direction="OUTBOUND",
        sender=user.name,
        content=payload.content,
    )
    db.add(message)
    conversation.last_message_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "simulated": True, "message_id": message.id}


@router.get("/analytics/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = accessible_workspace_ids(db, user.id)
    campaign_ids = [
        item.id
        for item in db.scalars(select(Campaign)).all()
        if entity_workspace_id(db, item) in ids
    ]
    return {
        "active_campaigns": db.scalar(
            select(func.count(Campaign.id)).where(
                Campaign.id.in_(campaign_ids), Campaign.status == "ACTIVE"
            )
        )
        or 0,
        "new_leads": db.scalar(
            select(func.count(Lead.id)).where(
                Lead.workspace_id.in_(ids), Lead.status.in_(["NEW", "REVIEW"])
            )
        )
        or 0,
        "qualified_leads": db.scalar(
            select(func.count(Lead.id)).where(
                Lead.workspace_id.in_(ids), Lead.status == "QUALIFIED"
            )
        )
        or 0,
        "pending_messages": db.scalar(
            select(func.count(MessageDraft.id)).where(
                MessageDraft.approval_status == "PENDING",
                MessageDraft.campaign_id.in_(campaign_ids),
            )
        )
        or 0,
        "successful_publications": db.scalar(
            select(func.count(Publication.id)).where(
                Publication.campaign_id.in_(campaign_ids),
                Publication.status == "PUBLISHED_CONFIRMED",
            )
        )
        or 0,
        "open_conversations": db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.workspace_id.in_(ids), Conversation.status == "OPEN"
            )
        )
        or 0,
        "integration_health": "MOCK / HEALTHY",
        "safety_lock": system_flag(db, "EMERGENCY_STOP") or system_flag(db, "SAFETY_LOCK"),
    }


@router.get("/analytics/campaigns/{entity_id}")
def campaign_analytics(
    entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    campaign = guard_entity(db, user, db.get(Campaign, entity_id))
    return {
        "campaign_id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "daily_limit": campaign.daily_limit,
        "leads": db.scalar(select(func.count(Lead.id)).where(Lead.campaign_id == campaign.id)) or 0,
        "publications": db.scalar(
            select(func.count(Publication.id)).where(Publication.campaign_id == campaign.id)
        )
        or 0,
    }


@router.get("/integrations")
def integrations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        model_dict(item)
        for item in db.scalars(select(IntegrationAccount)).all()
        if item.workspace_id in accessible_workspace_ids(db, user.id)
    ]


@router.get("/control/safety", response_model=SafetyStateResponse)
def safety_state(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return SafetyStateResponse(
        emergency_stop=system_flag(db, "EMERGENCY_STOP"), safety_lock=system_flag(db, "SAFETY_LOCK")
    )


@router.post("/control/emergency-stop", response_model=SafetyStateResponse)
def enable_emergency_stop(user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_id = (
        accessible_workspace_ids(db, user.id)[0] if accessible_workspace_ids(db, user.id) else None
    )
    if workspace_id is None:
        raise HTTPException(status_code=403, detail="No workspace access")
    require_perm(db, user, workspace_id, "workspace.manage")
    set_system_flag(db, "EMERGENCY_STOP", True)
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="safety.emergency_stop.enable",
        entity_type="SystemState",
        entity_id="EMERGENCY_STOP",
        after={"enabled": True},
    )
    db.commit()
    return safety_state(user, db)


@router.delete("/control/emergency-stop", response_model=SafetyStateResponse)
def disable_emergency_stop(user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_id = (
        accessible_workspace_ids(db, user.id)[0] if accessible_workspace_ids(db, user.id) else None
    )
    if workspace_id is None:
        raise HTTPException(status_code=403, detail="No workspace access")
    require_perm(db, user, workspace_id, "workspace.manage")
    set_system_flag(db, "EMERGENCY_STOP", False)
    audit(
        db,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="safety.emergency_stop.disable",
        entity_type="SystemState",
        entity_id="EMERGENCY_STOP",
        after={"enabled": False},
    )
    db.commit()
    return safety_state(user, db)


@router.post("/permissions/check", response_model=PermissionCheckResponse)
def permission_check(
    payload: PermissionCheckRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace_id = (
        accessible_workspace_ids(db, user.id)[0] if accessible_workspace_ids(db, user.id) else ""
    )
    role = role_for(db, user.id, workspace_id) or "NONE"
    return PermissionCheckResponse(
        allowed=payload.permission in ROLE_PERMISSIONS.get(role, set()),
        role=role,
        permission=payload.permission,
    )


@router.get("/audit")
def audit_log(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = accessible_workspace_ids(db, user.id)
    if not ids:
        return []
    if not any(has_permission(db, user.id, workspace_id, "audit.view") for workspace_id in ids):
        raise HTTPException(status_code=403, detail="Permission required: audit.view")
    return [
        model_dict(item)
        for item in db.scalars(
            select(AuditEvent)
            .where(AuditEvent.workspace_id.in_(ids))
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        ).all()
    ]
