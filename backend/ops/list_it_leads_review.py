from sqlalchemy import select

from app.db import SessionLocal
from app.models import Lead


db = SessionLocal()
try:
    leads = db.scalars(
        select(Lead)
        .where(Lead.source_platform == "TELEGRAM")
        .order_by(Lead.score.desc(), Lead.created_at.desc())
    ).all()
    for lead in leads[:40]:
        print({
            "score": lead.score,
            "status": lead.status,
            "url": lead.source_message_url or lead.source_url,
            "need": lead.detected_need,
            "text": lead.raw_text[:300].replace("\n", " "),
        })
finally:
    db.close()
