from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Campaign,
    CampaignCommunityScore,
    CampaignIntelligenceRun,
    Community,
    MessageDraft,
    Publication,
)


db = SessionLocal()
try:
    campaigns = db.scalars(select(Campaign).order_by(Campaign.created_at)).all()
    print("CAMPAIGNS")
    for campaign in campaigns:
        print({"id": campaign.id, "name": campaign.name, "status": campaign.status, "geography": campaign.geography, "language": campaign.language, "daily_limit": campaign.daily_limit, "objective": campaign.objective})
        runs = db.scalars(select(CampaignIntelligenceRun).where(CampaignIntelligenceRun.campaign_id == campaign.id).order_by(CampaignIntelligenceRun.created_at.desc())).all()
        for run in runs[:5]:
            print("RUN", {"status": run.status, "discovered": run.discovered_communities, "analyzed": run.analyzed_communities, "recommended": run.recommended_communities, "average_score": run.average_score, "reach": run.projected_reach, "ai_cost": run.ai_cost, "completed_at": run.completed_at.isoformat() if run.completed_at else None})
        scores = db.scalars(select(CampaignCommunityScore).where(CampaignCommunityScore.campaign_id == campaign.id)).all()
        print("SCORES", {"count": len(scores), "avg": round(sum(s.community_score for s in scores) / len(scores), 2) if scores else 0, "recommendations": dict(db.execute(select(CampaignCommunityScore.recommendation, func.count()).where(CampaignCommunityScore.campaign_id == campaign.id).group_by(CampaignCommunityScore.recommendation)).all())})
        drafts = db.scalars(select(MessageDraft).where(MessageDraft.campaign_id == campaign.id)).all()
        pubs = db.scalars(select(Publication).where(Publication.campaign_id == campaign.id)).all()
        print("DRAFTS", {"count": len(drafts), "approved": sum(d.approval_status == "APPROVED" for d in drafts)})
        print("PUBLICATIONS", {"count": len(pubs), "statuses": dict(db.execute(select(Publication.status, func.count()).where(Publication.campaign_id == campaign.id).group_by(Publication.status)).all()), "sent": sum(p.status == "SENT" for p in pubs), "queued": sum(p.status == "QUEUED" for p in pubs)})
finally:
    db.close()
