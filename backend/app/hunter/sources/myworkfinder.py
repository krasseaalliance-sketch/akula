from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ..models import RawSignal, SourcePolicy


class MyWorkFinderOrdersAdapter:
    """Read-only capture of the public live-order JSON feed."""

    URL = "https://myworkfinder.ru/landing/orders-feed"

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def read(self, *, now: datetime | None = None, max_age_hours: int = 72) -> tuple[SourcePolicy, list[RawSignal]]:
        now = now or datetime.now(UTC)
        policy = SourcePolicy(
            source="myworkfinder.ru public live order feed",
            access_mode="PUBLIC_HTTP_READ_CAPTURE",
            public_scope="PUBLIC_LIVE_ORDER_FEED",
            rate_limit="ONE_FEED_REQUEST_PER_RUN",
            terms_risk="REVIEW_REQUIRED",
            automation_allowed=False,
            data_retention_rule="retain_public_url_order_id_and_minimal_public_excerpt_only",
        )
        with httpx.Client(headers={"User-Agent": "LeadHunter-Stage1R2-ReadOnly/1.0"}, timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(self.URL)
            response.raise_for_status()
            payload = response.json()
        signals: list[RawSignal] = []
        for item in payload.get("items", []):
            published_at = _parse_datetime(item.get("published_at"))
            if published_at is None or (now - published_at).total_seconds() > max_age_hours * 3600:
                continue
            order_id = str(item.get("id"))
            source_url = f"{self.URL}#order-{order_id}"
            title = str(item.get("title") or "").replace("🔥 ", "").strip()
            summary = str(item.get("summary") or "").strip()
            category = str(item.get("category") or "").strip()
            budget = str(item.get("budget") or "").strip()
            signals.append(
                RawSignal(
                    id=f"myworkfinder-order-{order_id}", source="myworkfinder.ru", source_url=source_url,
                    external_id=order_id, author_identifier=None, published_at=published_at, detected_at=now,
                    title=title, text=" ".join(part for part in (summary, category, budget) if part),
                    metadata={
                        "source_scope": "PUBLIC_LIVE_ORDER_FEED", "verification_status": "PUBLIC_LIVE_ORDER_CARD",
                        "actionable_now": "UNKNOWN", "manual_verified": False, "source_origin": item.get("source"),
                        "order_id": order_id, "budget_label": budget, "published_label": item.get("published_label"),
                        "actionability_evidence": "public live-order feed item with order id and published timestamp",
                        "contact_channel": None,
                    }, lead_type_hint="HOT_DEMAND",
                )
            )
        return policy, signals


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
