from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .filters import TELEGRAM_RULESET_VITRINA_V1, FastIntentFilter


@dataclass
class ShadowCandidate:
    endpoint_id: str
    message_id: str
    source_url: str | None
    published_at: str | None
    detected_at: str
    text: str
    score: int
    reason: str


class TelegramShadowIngestor:
    """Authenticated-source shadow pipeline; never touches Stage 2.1 state."""

    def __init__(self, *, filter_: FastIntentFilter | None = None):
        self.filter = filter_ or FastIntentFilter(TELEGRAM_RULESET_VITRINA_V1)

    def ingest(self, endpoint_id: str, messages: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        candidates: list[ShadowCandidate] = []
        rejected = {"seller_rejected": 0, "vacancy_rejected": 0, "spam_rejected": 0, "informational_rejected": 0}
        seen: set[str] = set()
        for message in messages:
            message_id = str(message.get("message_id") or message.get("id") or "")
            text = " ".join(str(message.get("text") or "").split())
            fingerprint = hashlib.sha256(f"{endpoint_id}|{text.casefold()}".encode()).hexdigest()[:24]
            if not message_id or not text or fingerprint in seen:
                rejected["spam_rejected"] += 1
                continue
            seen.add(fingerprint)
            result = self.filter.evaluate(text, published_at=_parse_dt(message.get("published_at")), now=now, metadata={"username": str(message.get("username") or "")})
            if result.seller_language:
                rejected["seller_rejected"] += 1
            if result.vacancy_language:
                rejected["vacancy_rejected"] += 1
            if result.informational:
                rejected["informational_rejected"] += 1
            if result.passed:
                candidates.append(ShadowCandidate(endpoint_id, message_id, message.get("source_url"), message.get("published_at"), now.isoformat(), text, result.score, result.reason))
        return {"mode": "SHADOW", "endpoint_id": endpoint_id, "messages_scanned": len(messages), "new_messages": len(messages), "updated_messages": 0, "previously_seen": 0, "filter_pass": len(candidates), "filter_reject": len(messages) - len(candidates), "candidate_count": len(candidates), "median_message_age": None, "detection_latency": None, **rejected, "errors": 0, "rate_limits": 0, "write_operations": 0, "stage2_1_mutation": False, "production_alerts": 0, "candidates": [asdict(candidate) for candidate in candidates]}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=UTC)
