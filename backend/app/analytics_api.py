from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import current_user
from .db import get_db
from .models import Brand, Campaign, Community, Company, Conversation, Lead, Publication, User
from .services import accessible_workspace_ids

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/leads")
def lead_analytics(
    campaign_id: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace_ids = accessible_workspace_ids(db, user.id)
    query = select(Lead).where(Lead.workspace_id.in_(workspace_ids))
    if campaign_id:
        query = query.where(Lead.campaign_id == campaign_id)
    leads = list(db.scalars(query).all())
    by_status: dict[str, int] = {}
    by_intent: dict[str, int] = {}
    for lead in leads:
        by_status[lead.status] = by_status.get(lead.status, 0) + 1
        by_intent[lead.intent or "UNKNOWN"] = by_intent.get(lead.intent or "UNKNOWN", 0) + 1
    return {
        "total": len(leads),
        "found": len(leads),
        "qualified": sum(1 for lead in leads if lead.status == "QUALIFIED"),
        "rejected": sum(1 for lead in leads if lead.status.startswith("REJECTED") or lead.status == "DO_NOT_CONTACT"),
        "average_score": round(sum(lead.score for lead in leads) / len(leads), 2) if leads else 0,
        "by_status": by_status,
        "by_intent": by_intent,
        "responses": db.scalar(select(func.count(Conversation.id)).where(Conversation.workspace_id.in_(workspace_ids))) or 0,
        "ctr": None,
        "conversion": round(sum(1 for lead in leads if lead.status == "CONVERTED") / len(leads), 4) if leads else 0,
        "roi": None,
    }


@router.get("/campaigns/{campaign_id}/dashboard")
def campaign_dashboard(campaign_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = db.scalar(select(Campaign).join(Brand, Brand.id == Campaign.brand_id).join(Company, Company.id == Brand.company_id).where(Campaign.id == campaign_id, Company.workspace_id.in_(accessible_workspace_ids(db, user.id))))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    leads = list(db.scalars(select(Lead).where(Lead.campaign_id == campaign.id)).all())
    publications = list(db.scalars(select(Publication).where(Publication.campaign_id == campaign.id)).all())
    communities = list(db.scalars(select(Community).where(Community.id.in_([item.source_community_id for item in leads if item.source_community_id]))).all())
    return {
        "campaign": {"id": campaign.id, "name": campaign.name, "status": campaign.status},
        "communities": [{"id": item.id, "title": item.title, "score": item.community_score} for item in communities],
        "leads": len(leads),
        "qualified_leads": sum(1 for lead in leads if lead.status == "QUALIFIED"),
        "publications": len(publications),
        "successful_publications": sum(1 for item in publications if item.status in {"SENT", "DRY_RUN"}),
        "replies": db.scalar(select(func.count(Conversation.id)).where(Conversation.campaign_id == campaign.id)) or 0,
        "cost": 0,
        "effectiveness": round(sum(lead.score for lead in leads) / len(leads), 2) if leads else 0,
    }


@router.get("/communities")
def community_analytics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = accessible_workspace_ids(db, user.id)
    communities = list(db.scalars(select(Community).where(Community.workspace_id.in_(ids)).order_by(Community.community_score.desc(), Community.title)).all())
    return [{"id": item.id, "title": item.title, "platform": item.platform, "score": item.community_score, "activity": item.activity_score, "lead_quality": item.lead_quality_score, "conversion_rate": item.conversion_rate, "rules": bool(item.rules_text), "geography": item.geography, "category": item.category} for item in communities]


@router.get("/roi")
def roi_analytics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = accessible_workspace_ids(db, user.id)
    sent = db.scalar(select(func.count(Publication.id)).join(Campaign, Campaign.id == Publication.campaign_id).join(Brand, Brand.id == Campaign.brand_id).join(Company, Company.id == Brand.company_id).where(Publication.status == "PUBLISHED_CONFIRMED", Company.workspace_id.in_(ids))) or 0
    conversions = db.scalar(select(func.count(Lead.id)).where(Lead.workspace_id.in_(ids), Lead.status == "CONVERTED")) or 0
    return {"revenue": None, "cost": 0, "roi": None, "sent_publications": sent, "conversions": conversions, "status": "REVENUE_TRACKING_NOT_CONFIGURED"}
