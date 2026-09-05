from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import current_user, require_perm
from .campaign_intelligence import CampaignIntelligenceEngine
from .campaign_intelligence_schemas import (
    CampaignAnalyzeRequest,
    CampaignLearningRequest,
    CampaignWizardRequest,
)
from .db import get_db
from .models import Brand, Campaign, CampaignAudienceProfile, Company, Offer, User
from .services import accessible_workspace_ids, audit

router = APIRouter(prefix="/api/campaign-intelligence", tags=["campaign-intelligence"])
engine = CampaignIntelligenceEngine()


def _workspace(db: Session, user: User, workspace_id: str) -> str:
    if workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    require_perm(db, user, workspace_id, "campaign.create")
    return workspace_id


def _campaign(db: Session, user: User, campaign_id: str) -> tuple[Campaign, str]:
    campaign = db.scalar(select(Campaign).join(Brand, Brand.id == Campaign.brand_id).join(Company, Company.id == Brand.company_id).where(Campaign.id == campaign_id, Company.workspace_id.in_(accessible_workspace_ids(db, user.id))))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    workspace_id = db.scalar(select(Company.workspace_id).join(Brand, Brand.company_id == Company.id).where(Brand.id == campaign.brand_id))
    if workspace_id is None:
        raise HTTPException(status_code=404, detail="Campaign workspace not found")
    return campaign, workspace_id


@router.post("/wizard")
def campaign_wizard(payload: CampaignWizardRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_id = _workspace(db, user, payload.workspace_id)
    brand_query = select(Brand).join(Company, Company.id == Brand.company_id).where(Company.workspace_id == workspace_id).order_by(Brand.created_at)
    if payload.brand_id:
        brand_query = brand_query.where(Brand.id == payload.brand_id)
    brand = db.scalar(brand_query)
    if brand is None:
        raise HTTPException(status_code=422, detail="Create a brand before starting the Campaign Wizard")
    if payload.offer_id:
        offer = db.scalar(select(Offer).where(Offer.id == payload.offer_id, Offer.brand_id == brand.id))
        if offer is None:
            raise HTTPException(status_code=422, detail="Offer does not belong to the selected workspace brand")
    campaign_name = payload.campaign_name or f"{payload.offer[:80]} — {payload.goal}"
    language = payload.languages[0] if payload.languages else "ru"
    campaign = Campaign(brand_id=brand.id, offer_id=payload.offer_id, name=campaign_name, objective=payload.goal, geography=payload.geography or (payload.geographies[0] if payload.geographies else None), language=language, daily_limit=max(1, min(10000, int(payload.budget / 10) if payload.budget else 50)), status="READY", campaign_type="LEAD_DISCOVERY", publication_policy="APPROVAL_REQUIRED")
    db.add(campaign)
    db.flush()
    profile = engine.create_profile(db, campaign=campaign, workspace_id=workspace_id, answers=payload.model_dump(), actor_id=user.id, use_llm=payload.use_llm)
    audit(db, workspace_id=workspace_id, actor_id=user.id, action="campaign.wizard.create", entity_type="Campaign", entity_id=campaign.id, after={"profile_id": profile.id, "provider": profile.provider, "goal": profile.goal})
    db.commit()
    db.refresh(campaign)
    db.refresh(profile)
    return {"campaign": campaign, "audience_profile": profile, "wizard_answers": payload.model_dump()}


@router.post("/campaigns/{campaign_id}/analyze")
def analyze_campaign(campaign_id: str, payload: CampaignAnalyzeRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign, workspace_id = _campaign(db, user, campaign_id)
    require_perm(db, user, workspace_id, "lead.edit")
    return engine.analyze(db, campaign=campaign, workspace_id=workspace_id, actor_id=user.id, use_llm=payload.use_llm if payload else True)


@router.get("/campaigns/{campaign_id}/dashboard")
def campaign_dashboard(campaign_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign, workspace_id = _campaign(db, user, campaign_id)
    return engine.dashboard(db, campaign=campaign, workspace_id=workspace_id)


@router.get("/campaigns/{campaign_id}/scores")
def campaign_scores(campaign_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign, _workspace_id = _campaign(db, user, campaign_id)
    from .models import CampaignCommunityScore
    return list(db.scalars(select(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == campaign.id).order_by(CampaignCommunityScore.rank, CampaignCommunityScore.community_score.desc())).all())


@router.post("/campaigns/{campaign_id}/learn")
def learn_campaign(campaign_id: str, payload: CampaignLearningRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign, workspace_id = _campaign(db, user, campaign_id)
    require_perm(db, user, workspace_id, "lead.edit")
    return engine.learn(db, campaign=campaign, workspace_id=workspace_id, actor_id=user.id)


@router.get("/summary")
def intelligence_summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_ids = accessible_workspace_ids(db, user.id)
    campaigns = list(db.scalars(select(Campaign).join(Brand, Brand.id == Campaign.brand_id).join(Company, Company.id == Brand.company_id).where(Company.workspace_id.in_(workspace_ids))).all())
    return {"campaigns": len(campaigns), "wizard_campaigns": int(db.scalar(select(func.count(CampaignAudienceProfile.id)).where(CampaignAudienceProfile.workspace_id.in_(workspace_ids))) or 0)}
