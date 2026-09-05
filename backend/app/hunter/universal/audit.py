from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ModelAuditEvent:
    action: str
    business_id: str
    actor_id: str
    created_at: datetime
    before_version: str | None
    after_version: str | None
    details: dict[str, Any]


def audit_model(action: str, business_id: str, actor_id: str, *, before_version: str | None = None, after_version: str | None = None, details: dict[str, Any] | None = None) -> ModelAuditEvent:
    return ModelAuditEvent(action, business_id, actor_id, datetime.now(UTC), before_version, after_version, details or {})
