from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user, require_perm
from .db import get_db
from .lead_intelligence.engine import LeadIntelligenceService, token_cosine
from .lead_intelligence_schemas import (
    CommunityScoreResponse,
    IntelligenceRunRequest,
    SearchProfileCreate,
    SearchProfilePatch,
    SimilarityRequest,
)
from .models import (
    AISearchProfile,
    Community,
    Lead,
    LeadIntelligenceAnalysis,
    LeadIntelligenceRun,
    MessageRecommendation,
    User,
)
from .services import accessible_workspace_ids

router = APIRouter(prefix="/api/lead-intelligence", tags=["lead-intelligence"])
service = LeadIntelligenceService()


def _workspace_or_404(db: Session, user: User, workspace_id: str) -> str:
    if workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    require_perm(db, user, workspace_id, "lead.edit")
    return workspace_id


def _lead_or_404(db: Session, user: User, lead_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/runs")
def run_intelligence(payload: IntelligenceRunRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_id = _workspace_or_404(db, user, payload.workspace_id)
    return service.run(db, workspace_id=workspace_id, actor_id=user.id, campaign_id=payload.campaign_id, lead_ids=payload.lead_ids)


@router.get("/runs")
def list_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(LeadIntelligenceRun).where(LeadIntelligenceRun.workspace_id.in_(accessible_workspace_ids(db, user.id))).order_by(LeadIntelligenceRun.created_at.desc())).all())


@router.post("/leads/{lead_id}/analyze")
def analyze_lead(lead_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lead = _lead_or_404(db, user, lead_id)
    require_perm(db, user, lead.workspace_id, "lead.edit")
    run = service.run(db, workspace_id=lead.workspace_id, actor_id=user.id, campaign_id=lead.campaign_id, lead_ids=[lead.id])
    analysis = db.scalar(select(LeadIntelligenceAnalysis).where(LeadIntelligenceAnalysis.run_id == run.id, LeadIntelligenceAnalysis.lead_id == lead.id))
    return {"run": run, "analysis": analysis, "lead": lead}


@router.get("/leads/{lead_id}/analysis")
def lead_analysis(lead_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lead = _lead_or_404(db, user, lead_id)
    return list(db.scalars(select(LeadIntelligenceAnalysis).where(LeadIntelligenceAnalysis.lead_id == lead.id).order_by(LeadIntelligenceAnalysis.created_at.desc())).all())


@router.post("/leads/{lead_id}/recommendation")
def lead_recommendation(lead_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lead = _lead_or_404(db, user, lead_id)
    require_perm(db, user, lead.workspace_id, "lead.edit")
    return service.recommend(db, lead=lead, actor_id=user.id)


@router.get("/recommendations")
def recommendations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(MessageRecommendation).where(MessageRecommendation.workspace_id.in_(accessible_workspace_ids(db, user.id))).order_by(MessageRecommendation.created_at.desc())).all())


@router.get("/profiles")
def list_profiles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(AISearchProfile).where(AISearchProfile.workspace_id.in_(accessible_workspace_ids(db, user.id))).order_by(AISearchProfile.created_at.desc())).all())


@router.post("/profiles", status_code=201)
def create_profile(payload: SearchProfileCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_id = _workspace_or_404(db, user, payload.workspace_id)
    profile = AISearchProfile(workspace_id=workspace_id, campaign_id=payload.campaign_id, name=payload.name, natural_language_query=payload.natural_language_query, criteria=payload.criteria, status="DRAFT", created_by=user.id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/profiles/{profile_id}")
def patch_profile(profile_id: str, payload: SearchProfilePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.get(AISearchProfile, profile_id)
    if profile is None or profile.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="AI search profile not found")
    require_perm(db, user, profile.workspace_id, "lead.edit")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/similarity")
def similarity(payload: SimilarityRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _workspace_or_404(db, user, payload.workspace_id)
    scores = [{"index": index, "score": token_cosine(payload.text, candidate), "blocked": token_cosine(payload.text, candidate) >= payload.threshold} for index, candidate in enumerate(payload.compared_texts)]
    return {"method": "TOKEN_COSINE", "threshold": payload.threshold, "scores": scores}


@router.post("/communities/{community_id}/score", response_model=CommunityScoreResponse)
def score_community(community_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    community = db.get(Community, community_id)
    if community is None or community.workspace_id not in accessible_workspace_ids(db, user.id):
        raise HTTPException(status_code=404, detail="Community not found")
    require_perm(db, user, community.workspace_id, "lead.edit")
    return service.score_community(db, community=community)
