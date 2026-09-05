from sqlalchemy import select

from app.db import SessionLocal
from app.models import ServiceLog


db = SessionLocal()
try:
    rows = db.scalars(
        select(ServiceLog)
        .where(ServiceLog.service_key == "lead_monitor")
        .order_by(ServiceLog.created_at.desc())
    ).all()
    for row in rows[:20]:
        print({"created_at": row.created_at.isoformat(), "event": row.event, "message": row.message, "metadata": row.metadata_json})
finally:
    db.close()
