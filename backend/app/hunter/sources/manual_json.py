from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import RawSignal, SourcePolicy


class ManualJsonSourceAdapter:
    """Read-only adapter for a manually/browser-captured public source file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> tuple[SourcePolicy, list[RawSignal]]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        policy = SourcePolicy(**payload["source_policy"])
        if policy.status != "APPROVED_FOR_READ_ONLY_CAPTURE":
            raise ValueError(f"source policy is not approved: {policy.status}")
        signals: list[RawSignal] = []
        for row in payload.get("signals", []):
            signals.append(
                RawSignal(
                    id=str(row["id"]), source=str(row["source"]),
                    source_url=str(row["source_url"]), external_id=str(row["external_id"]),
                    author_identifier=row.get("author_identifier"),
                    published_at=_parse_dt(row.get("published_at")),
                    detected_at=_parse_dt(row.get("detected_at")) or datetime.now(UTC),
                    title=str(row.get("title") or ""), text=str(row.get("text") or ""),
                    metadata=dict(row.get("metadata") or {}),
                    lead_type_hint=row.get("lead_type_hint"),
                )
            )
        return policy, signals


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
