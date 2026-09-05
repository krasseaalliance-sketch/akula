from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Community, Lead, MessageDraft, Publication, PublicationJob


db = SessionLocal()
try:
    rows = db.execute(
        select(Publication, PublicationJob, Community, MessageDraft)
        .join(PublicationJob, PublicationJob.publication_id == Publication.id, isouter=True)
        .join(Community, Community.id == Publication.community_id, isouter=True)
        .join(MessageDraft, MessageDraft.id == Publication.message_draft_id, isouter=True)
        .order_by(Publication.created_at.desc())
    ).all()
    print(f"PUB_COUNT={len(rows)}")
    for publication, job, community, draft in rows[:20]:
        print({
            "community": (community.username or community.title) if community else None,
            "url": community.url if community else None,
            "status": publication.status,
            "job": job.status if job else None,
            "available_at": job.available_at.isoformat() if job else None,
            "external_id": publication.external_message_id,
            "error": publication.error_code or (job.error_code if job else None),
            "message": publication.error_message or (job.error_message if job else None),
            "draft_approval": draft.approval_status if draft else None,
        })
    print("LEAD_COUNTS", db.execute(select(Lead.status, func.count()).group_by(Lead.status)).all())
finally:
    db.close()
