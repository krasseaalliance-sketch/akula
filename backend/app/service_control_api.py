from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import current_user
from .db import get_db
from .models import ServiceLog, ServiceRuntime, User
from .service_scheduler import default_service_specs, next_window_start
from .services import accessible_workspace_ids

router = APIRouter(prefix="/api/operations", tags=["operations"])


def _serialize(runtime: ServiceRuntime | None, spec, workspace_id: str) -> dict:
    if runtime is None:
        next_run = next_window_start(datetime.now(timezone.utc), spec).replace(tzinfo=None)
        return {
            "workspace_id": workspace_id,
            "service_key": spec.key,
            "display_name": spec.display_name,
            "status": "NOT_STARTED",
            "scheduler": spec.scheduler_name,
            "timezone": spec.timezone,
            "window_start": spec.window_start,
            "window_end": spec.window_end,
            "next_run": next_run,
            "last_run": None,
            "today_publications": 0,
            "today_communities": 0,
            "today_leads": 0,
            "critical_leads": 0,
            "last_error": None,
            "stats": {},
        }
    return {
        "workspace_id": runtime.workspace_id,
        "service_key": runtime.service_key,
        "display_name": runtime.display_name,
        "status": runtime.status,
        "scheduler": runtime.scheduler_name,
        "timezone": runtime.timezone,
        "window_start": runtime.window_start,
        "window_end": runtime.window_end,
        "next_run": runtime.next_run_at,
        "last_run": runtime.last_run_at,
        "last_success": runtime.last_success_at,
        "today_publications": runtime.today_publications,
        "today_communities": runtime.today_communities,
        "today_leads": runtime.today_leads,
        "critical_leads": runtime.today_critical_leads,
        "last_error": runtime.last_error,
        "stats": runtime.stats_json or {},
    }


@router.get("/services")
def service_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    workspace_ids = accessible_workspace_ids(db, user.id)
    specs = default_service_specs()
    runtimes = list(db.scalars(select(ServiceRuntime).where(ServiceRuntime.workspace_id.in_(workspace_ids))).all())
    by_key = {(row.workspace_id, row.service_key): row for row in runtimes}
    return [
        _serialize(by_key.get((workspace_id, key)), spec, workspace_id)
        for workspace_id in workspace_ids
        for key, spec in specs.items()
    ]


@router.get("/services/{service_key}/logs")
def service_logs(
    service_key: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    workspace_ids = accessible_workspace_ids(db, user.id)
    return list(db.scalars(select(ServiceLog).where(
        ServiceLog.workspace_id.in_(workspace_ids),
        ServiceLog.service_key == service_key,
    ).order_by(ServiceLog.created_at.desc()).limit(limit)).all())
