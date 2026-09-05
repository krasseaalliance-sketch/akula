from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import ServiceRuntime, TelegramDialog, TelegramMessageRecord


db = SessionLocal()
try:
    runtimes = db.scalars(select(ServiceRuntime).where(ServiceRuntime.service_key == "lead_monitor")).all()
    for runtime in runtimes:
        print({"status": runtime.status, "last_run": runtime.last_run_at.isoformat() if runtime.last_run_at else None, "last_success": runtime.last_success_at.isoformat() if runtime.last_success_at else None, "stats": runtime.stats_json, "error": runtime.last_error})
    print("LOCAL_DIALOGS", db.scalar(select(func.count(TelegramDialog.id))))
    print("LOCAL_MESSAGES", db.scalar(select(func.count(TelegramMessageRecord.id))))
finally:
    db.close()
