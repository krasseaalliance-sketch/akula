import os
from datetime import datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Lead, TelegramAccountProfile, Workspace
from app.telegram_engine.engine import TelegramEngineService


def main() -> None:
    db = SessionLocal()
    workspace = db.scalar(select(Workspace))
    profile = db.scalar(select(TelegramAccountProfile).where(
        TelegramAccountProfile.workspace_id == workspace.id,
        TelegramAccountProfile.username == "Alexey_Mifanyuk",
        TelegramAccountProfile.authorization_status == "AUTHORIZED",
    ))
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    leads = list(db.scalars(select(Lead).where(
        Lead.workspace_id == workspace.id,
        Lead.created_at >= today,
        Lead.source_message_url.is_not(None),
    ).order_by(Lead.score.desc(), Lead.created_at.desc())).all())
    lines = ["Lead Hunter Monitor · IT", f"Все лиды за сегодня: {len(leads)}", ""]
    for index, lead in enumerate(leads, 1):
        marker = " 🔥" if float(lead.score or 0) >= 70 else ""
        lines.append(f"{index}. {int(lead.score or 0)}/100{marker} · {lead.detected_need or 'IT спрос'}")
        lines.append(str(lead.source_message_url))
    result = TelegramEngineService().send_operator_notification(
        profile=profile,
        content="\n".join(lines),
        target=os.getenv("TELEGRAM_IT_LEADS_CHAT_ID", "-5177668431"),
    )
    print(f"SENT {len(leads)} {result}")
    db.close()


if __name__ == "__main__":
    main()
