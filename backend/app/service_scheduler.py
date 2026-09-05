"""Independent, window-aware service schedulers.

Each service runs in its own container and persists only its own runtime and
logs. The scheduler never sends Telegram messages; publication remains behind
the existing approval/policy worker and the real-send flag.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .db import SessionLocal
from .models import ServiceLog, ServiceRuntime, User, Workspace

logger = logging.getLogger("lead-hunter-service")


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_clock(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


@dataclass(frozen=True)
class ServiceSpec:
    key: str
    display_name: str
    scheduler_name: str
    timezone: str
    window_start: str
    window_end: str
    interval_seconds: int


@dataclass
class TickResult:
    publications: int = 0
    communities: int = 0
    leads: int = 0
    critical_leads: int = 0
    stats: dict[str, object] | None = None


def default_service_specs() -> dict[str, ServiceSpec]:
    return {
        "campaign_engine": ServiceSpec(
            key="campaign_engine",
            display_name="Campaign Engine · Bali Companions",
            scheduler_name="campaign-engine-scheduler",
            timezone=os.getenv("CAMPAIGN_SERVICE_TIMEZONE", "Asia/Makassar"),
            window_start=os.getenv("CAMPAIGN_SERVICE_WINDOW_START", "06:00"),
            window_end=os.getenv("CAMPAIGN_SERVICE_WINDOW_END", "22:00"),
            interval_seconds=max(60, int(os.getenv("CAMPAIGN_SERVICE_INTERVAL_SECONDS", "900"))),
        ),
        "lead_monitor": ServiceSpec(
            key="lead_monitor",
            display_name="Lead Hunter Monitor · IT",
            scheduler_name="lead-monitor-scheduler",
            timezone=os.getenv("LEAD_MONITOR_TIMEZONE", "Asia/Krasnoyarsk"),
            window_start=os.getenv("LEAD_MONITOR_WINDOW_START", "10:00"),
            window_end=os.getenv("LEAD_MONITOR_WINDOW_END", "00:00"),
            interval_seconds=max(60, int(os.getenv("LEAD_MONITOR_INTERVAL_SECONDS", "300"))),
        ),
        "asmet": ServiceSpec(
            key="asmet",
            display_name="ASmeT MAX work processor",
            scheduler_name="asmet-scheduler",
            timezone=os.getenv("ASMET_SERVICE_TIMEZONE", "Asia/Krasnoyarsk"),
            window_start=os.getenv("ASMET_SERVICE_WINDOW_START", "00:00"),
            window_end=os.getenv("ASMET_SERVICE_WINDOW_END", "23:59"),
            interval_seconds=max(30, int(os.getenv("ASMET_SERVICE_INTERVAL_SECONDS", "60"))),
        ),
    }


def _window_bounds(now: datetime, spec: ServiceSpec) -> tuple[datetime, datetime]:
    tz = ZoneInfo(spec.timezone)
    local = now.astimezone(tz)
    start_hour, start_minute = _parse_clock(spec.window_start)
    end_hour, end_minute = _parse_clock(spec.window_end)
    start = local.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = local.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if end <= start:
        end += timedelta(days=1)
    if local < start:
        if end - start > timedelta(hours=23):
            start -= timedelta(days=1)
            end -= timedelta(days=1)
        else:
            return start, end
    if local >= end:
        start += timedelta(days=1)
        end += timedelta(days=1)
    return start, end


def in_window(now: datetime, spec: ServiceSpec) -> bool:
    start, end = _window_bounds(now, spec)
    local = now.astimezone(ZoneInfo(spec.timezone))
    return start <= local < end


def next_window_start(now: datetime, spec: ServiceSpec) -> datetime:
    start, end = _window_bounds(now, spec)
    local = now.astimezone(ZoneInfo(spec.timezone))
    if start <= local < end:
        return local + timedelta(seconds=spec.interval_seconds)
    return start


class IndependentServiceScheduler:
    def __init__(self, spec: ServiceSpec, tick) -> None:
        self.spec = spec
        self.tick = tick

    def _runtime(self, db, workspace: Workspace) -> ServiceRuntime:
        runtime = db.scalar(select(ServiceRuntime).where(
            ServiceRuntime.workspace_id == workspace.id,
            ServiceRuntime.service_key == self.spec.key,
        ))
        if runtime is None:
            runtime = ServiceRuntime(
                workspace_id=workspace.id,
                service_key=self.spec.key,
                display_name=self.spec.display_name,
                status="STARTING",
                scheduler_name=self.spec.scheduler_name,
                timezone=self.spec.timezone,
                window_start=self.spec.window_start,
                window_end=self.spec.window_end,
                settings_json={"interval_seconds": self.spec.interval_seconds},
            )
            db.add(runtime)
            db.flush()
        return runtime

    def _log(self, db, workspace: Workspace, level: str, event: str, message: str, metadata: dict | None = None) -> None:
        db.add(ServiceLog(
            workspace_id=workspace.id,
            service_key=self.spec.key,
            level=level,
            event=event,
            message=message,
            metadata_json=metadata,
        ))
        getattr(logger, level.lower(), logger.info)("%s %s: %s", self.spec.key, event, message)

    def run_once(self) -> None:
        db = SessionLocal()
        try:
            workspace = db.scalar(select(Workspace).where(Workspace.status == "ACTIVE").order_by(Workspace.created_at))
            if workspace is None:
                return
            runtime = self._runtime(db, workspace)
            now = datetime.now(timezone.utc)
            next_run = next_window_start(now, self.spec)
            runtime.next_run_at = _utc_naive(next_run)
            if not in_window(now, self.spec):
                runtime.status = "SCHEDULED"
                runtime.last_error = None
                db.commit()
                return

            runtime.status = "RUNNING"
            runtime.last_run_at = _utc_naive(now)
            db.commit()
            try:
                result: TickResult = self.tick(db, workspace)
                runtime.status = "RUNNING"
                runtime.last_success_at = _utc_naive(datetime.now(timezone.utc))
                runtime.last_error = None
                runtime.today_publications = result.publications
                runtime.today_communities = result.communities
                runtime.today_leads = result.leads
                runtime.today_critical_leads = result.critical_leads
                runtime.stats_json = result.stats or {}
                self._log(db, workspace, "INFO", "tick.completed", "Scheduled tick completed", runtime.stats_json)
            except Exception as exc:
                db.rollback()
                runtime = self._runtime(db, workspace)
                runtime.status = "ERROR"
                runtime.last_error = str(exc)[:1000]
                self._log(db, workspace, "ERROR", "tick.failed", str(exc)[:1000])
            db.commit()
        finally:
            db.close()

    def run_forever(self) -> None:
        logger.info("%s started: %s %s-%s", self.spec.scheduler_name, self.spec.timezone, self.spec.window_start, self.spec.window_end)
        while True:
            cycle_started_at = datetime.now(timezone.utc)
            try:
                self.run_once()
            except Exception:
                logger.exception("%s scheduler cycle failed", self.spec.key)
            now = datetime.now(timezone.utc)
            if in_window(now, self.spec):
                # Keep a fixed cadence from cycle start. Sleeping for the full
                # interval after the work completes would add the tick runtime
                # to the configured interval (5 minutes becoming 6-8 minutes).
                next_tick_at = cycle_started_at + timedelta(seconds=self.spec.interval_seconds)
                delay = max(1.0, (next_tick_at - now).total_seconds())
                time.sleep(delay)
                continue
            # Sleep directly until the next local window start. This keeps the
            # first tick aligned to 06:00/10:00 instead of drifting by a poll
            # interval after a restart or an out-of-window cycle.
            wake_at = next_window_start(now, self.spec)
            delay = max(1.0, (wake_at - now).total_seconds())
            time.sleep(delay)


def actor_for(workspace: Workspace, db) -> User:
    actor = db.get(User, workspace.owner_id)
    if actor is None:
        raise RuntimeError("WORKSPACE_OWNER_NOT_FOUND")
    return actor
