from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class OutboundOperationForbidden(RuntimeError):
    """Raised whenever a read-only Hunter source attempts a write operation."""


@dataclass(frozen=True)
class AuditEvent:
    actor: str
    action: str
    source_account_id: str | None
    endpoint_id: str | None
    timestamp: str
    result: str
    metadata: dict[str, Any]


def block_outbound(
    action: str,
    *,
    actor: str = "hunter-runtime",
    source_account_id: str | None = None,
    endpoint_id: str | None = None,
    audit_sink: Callable[[AuditEvent], None] | None = None,
) -> None:
    event = AuditEvent(
        actor=actor,
        action=action,
        source_account_id=source_account_id,
        endpoint_id=endpoint_id,
        timestamp=datetime.now(UTC).isoformat(),
        result="BLOCKED_OUTBOUND_OPERATION",
        metadata={"read_only": True},
    )
    if audit_sink:
        audit_sink(event)
    raise OutboundOperationForbidden(action)
