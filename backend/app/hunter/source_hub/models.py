from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SourceAccount:
    id: str = field(default_factory=lambda: str(uuid4()))
    platform: str = "TELEGRAM"
    account_alias: str = ""
    credential_ref: str | None = None
    session_ref: str | None = None
    access_mode: str = "READ_ONLY"
    read_only: bool = True
    status: str = "AUTH_REQUIRED"
    last_auth_success_at: str | None = None
    last_auth_failure_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceEndpoint:
    id: str = field(default_factory=lambda: str(uuid4()))
    source_account_id: str = ""
    platform: str = "TELEGRAM"
    external_id: str = ""
    username: str | None = None
    title: str = ""
    endpoint_type: str = "PUBLIC_CHANNEL"
    enabled: bool = False
    priority: int = 50
    commercial_domain: str | None = None
    country: str | None = None
    language: str | None = None
    detected_language: str | None = None
    locale: str | None = None
    last_cursor: str | None = None
    last_seen_message_id: str | None = None
    last_seen_at: str | None = None
    last_scan_at: str | None = None
    last_success_at: str | None = None
    operational_health: str = "DEGRADED"
    commercial_yield: str = "UNKNOWN"
    scheduling_state: str = "PAUSED"
    discovery_state: str = "ACCESS_REVIEW"
    discovery_reason: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
