from __future__ import annotations

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Lead, Workspace


def main() -> None:
    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at))
        counts = db.execute(
            select(Lead.status, func.count(Lead.id))
            .where(Lead.workspace_id == workspace.id, Lead.source_platform == "TELEGRAM")
            .group_by(Lead.status)
        ).all()
        print(f"TOTAL={sum(int(count) for _, count in counts)}", flush=True)
        print(f"STATUS={dict(counts)}", flush=True)
        for lead in db.scalars(
            select(Lead)
            .where(Lead.workspace_id == workspace.id, Lead.source_platform == "TELEGRAM")
            .order_by(Lead.created_at.desc())
            .limit(20)
        ):
            print({
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
                "status": lead.status,
                "score": lead.score,
                "author": lead.author_username or lead.author_name,
                "need": lead.detected_need,
                "url": lead.source_message_url or lead.source_url,
                "text": (lead.raw_text or "").replace("\\n", " ")[:180],
            }, flush=True)


if __name__ == "__main__":
    main()
