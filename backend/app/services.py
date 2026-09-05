import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, SystemState, WorkspaceMember

PERMISSIONS = {
    "workspace.manage",
    "company.manage",
    "brand.manage",
    "campaign.create",
    "campaign.publish",
    "lead.view",
    "lead.edit",
    "message.approve",
    "integration.manage",
    "analytics.view",
    "audit.view",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "OWNER": set(PERMISSIONS),
    "ADMIN": set(PERMISSIONS) - {"workspace.manage"},
    "MANAGER": {
        "company.manage",
        "brand.manage",
        "campaign.create",
        "campaign.publish",
        "lead.view",
        "lead.edit",
        "message.approve",
        "analytics.view",
        "audit.view",
    },
    "OPERATOR": {"campaign.publish", "lead.view", "lead.edit", "message.approve", "analytics.view"},
    "ANALYST": {"lead.view", "analytics.view", "audit.view"},
    "VIEWER": {"lead.view", "analytics.view"},
}


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def model_dict(obj: Any) -> dict[str, Any]:
    return {column.name: json_safe(getattr(obj, column.name)) for column in obj.__table__.columns}


def accessible_workspace_ids(db: Session, user_id: str) -> list[str]:
    return list(
        db.scalars(
            select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.user_id == user_id, WorkspaceMember.status == "ACTIVE"
            )
        ).all()
    )


def role_for(db: Session, user_id: str, workspace_id: str) -> str | None:
    return db.scalar(
        select(WorkspaceMember.role).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.status == "ACTIVE",
        )
    )


def has_permission(db: Session, user_id: str, workspace_id: str, permission: str) -> bool:
    role = role_for(db, user_id, workspace_id)
    return role in ROLE_PERMISSIONS and permission in ROLE_PERMISSIONS[role]


def require_permission(db: Session, user_id: str, workspace_id: str, permission: str) -> str:
    role = role_for(db, user_id, workspace_id)
    if role not in ROLE_PERMISSIONS or permission not in ROLE_PERMISSIONS[role]:
        raise PermissionError(permission)
    return role


def system_flag(db: Session, key: str) -> bool:
    state = db.get(SystemState, key)
    return bool(state and state.enabled and state.value.lower() == "true")


def set_system_flag(db: Session, key: str, enabled: bool) -> SystemState:
    state = db.get(SystemState, key)
    if state is None:
        state = SystemState(key=key, value="true" if enabled else "false", enabled=enabled)
        db.add(state)
    else:
        state.value = "true" if enabled else "false"
        state.enabled = enabled
    return state


def audit(
    db: Session,
    *,
    workspace_id: str,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before": json_safe(before),
        "after": json_safe(after),
        "metadata": json_safe(metadata),
    }
    event_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    db.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before,
            after_state=after,
            metadata_json=metadata,
            event_hash=event_hash,
        )
    )


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\u0000", " ")
    # Some legacy captures were decoded as cp1251 before being stored. Repair
    # only when the round-trip clearly reduces mojibake markers; ordinary
    # Russian/Latin input is returned unchanged.
    try:
        repaired = value.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        repaired = value
    if repaired.count("Р") + repaired.count("С") < value.count("Р") + value.count("С"):
        value = repaired
    value = re.sub(r"\s+", " ", value).strip()
    return value


def dedupe_key(
    *,
    author_username: str | None,
    normalized_text: str,
    source_platform: str,
    campaign_id: str | None = None,
) -> str:
    """Build a stable lead identity inside a campaign scope.

    A source message may legitimately match more than one active campaign. The
    campaign scope prevents one campaign from hiding the same demand from
    another while preserving the old workspace-wide behavior when no campaign
    was supplied.
    """
    raw = "|".join(
        (
            source_platform.lower(),
            campaign_id or "__workspace__",
            (author_username or "").lower(),
            normalized_text.lower(),
        )
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def within_interval(db: Session, community_id: str, minutes: int = 30) -> bool:
    from .models import Publication

    latest = db.scalar(
        select(Publication.sent_at)
        .where(
            Publication.community_id == community_id,
            Publication.status.in_(["SENT", "PUBLISHED_CONFIRMED"]),
            Publication.sent_at.is_not(None),
        )
        .order_by(Publication.sent_at.desc())
        .limit(1)
    )
    return latest is None or latest <= datetime.utcnow() - timedelta(minutes=minutes)
