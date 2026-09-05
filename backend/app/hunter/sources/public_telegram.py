from __future__ import annotations

from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from ..models import RawSignal, SourcePolicy


class PublicTelegramChannelAdapter:
    """Read-only HTML capture for a public Telegram channel preview."""

    def __init__(self, channel: str = "job_developer", timeout: float = 20.0):
        self.channel = channel
        self.timeout = timeout

    def read(self, *, now: datetime | None = None, max_age_hours: int = 72) -> tuple[SourcePolicy, list[RawSignal]]:
        now = now or datetime.now(UTC)
        source_url = f"https://t.me/s/{self.channel}"
        policy = SourcePolicy(
            source=f"public Telegram @{self.channel}", access_mode="PUBLIC_HTML_READ_CAPTURE",
            public_scope="PUBLIC_CHANNEL_PREVIEW", rate_limit="ONE_PAGE_PER_RUN",
            terms_risk="REVIEW_REQUIRED", automation_allowed=False,
            data_retention_rule="retain_public_url_and_minimal_excerpt_only",
        )
        with httpx.Client(headers={"User-Agent": "LeadHunter-Stage1R2-ReadOnly/1.0"}, timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(source_url)
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        signals: list[RawSignal] = []
        for node in soup.select(".tgme_widget_message_wrap"):
            time_node = node.select_one("time[datetime]")
            if not time_node:
                continue
            published_at = _parse_datetime(time_node.get("datetime"))
            if published_at is None or (now - published_at).total_seconds() > max_age_hours * 3600:
                continue
            message = node.select_one(".tgme_widget_message_text")
            text = " ".join((message.get_text(" ", strip=True) if message else "").split())
            link = node.select_one("a.tgme_widget_message_date[href]")
            url = link.get("href") if link else source_url
            external_id = url.rstrip("/").split("/")[-1] if url else str(len(signals))
            if not text:
                continue
            signals.append(RawSignal(
                id=f"telegram-{self.channel}-{external_id}", source=f"telegram:@{self.channel}", source_url=url,
                external_id=external_id, author_identifier=f"public_channel:{self.channel}",
                published_at=published_at, detected_at=now, title=text[:120], text=text,
                metadata={"source_scope": "PUBLIC_CHANNEL_PREVIEW", "verification_status": "PUBLIC_TELEGRAM_PREVIEW", "actionable_now": "UNKNOWN", "manual_verified": False, "contact_channel": None},
                lead_type_hint="HOT_DEMAND",
            ))
        return policy, signals


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
