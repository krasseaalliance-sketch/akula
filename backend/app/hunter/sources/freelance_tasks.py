from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from ..models import RawSignal, SourcePolicy


class FreelanceNewestTasksAdapter:
    """Low-rate, public newest-first capture for Freelance.ru task feed."""

    def __init__(self, pages: int = 5, timeout: float = 20.0):
        self.pages = pages
        self.timeout = timeout

    def read(self, *, now: datetime | None = None, max_age_hours: int = 72) -> tuple[SourcePolicy, list[RawSignal]]:
        now = now or datetime.now(UTC)
        policy = SourcePolicy(
            source="freelance.ru public newest task feed",
            access_mode="PUBLIC_HTTP_READ_CAPTURE",
            public_scope="PUBLIC_NEWEST_TASK_FEED",
            rate_limit="LOW_RATE_SEQUENTIAL_CAPTURE",
            terms_risk="REVIEW_REQUIRED",
            automation_allowed=True,
            data_retention_rule="retain_public_url_and_minimal_excerpt_only",
        )
        signals: list[RawSignal] = []
        seen: set[str] = set()
        with httpx.Client(headers={"User-Agent": "LeadHunter-Stage1R1-ReadOnly/1.0"}, timeout=self.timeout, follow_redirects=True) as client:
            for page in range(1, self.pages + 1):
                response = client.get("https://freelance.ru/task", params={"page": page})
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                for card in soup.select("article.task-card"):
                    link = card.select_one("a.task-card__title-link[href]")
                    timestamp = card.select_one(".task-card__foot-item[title]")
                    if not link or not timestamp:
                        continue
                    published_at = _parse_site_datetime(timestamp.get("title"))
                    if published_at is None or (now - published_at).total_seconds() > max_age_hours * 3600:
                        continue
                    url = link["href"]
                    if url.startswith("/"):
                        url = "https://freelance.ru" + url
                    if url in seen:
                        continue
                    seen.add(url)
                    title = " ".join(link.get_text(" ", strip=True).split())
                    description_node = card.select_one(".task-card__desc")
                    description = " ".join((description_node.get_text(" ", strip=True) if description_node else "").split())
                    category = " ".join(node.get_text(" ", strip=True) for node in card.select(".task-chip--cat"))
                    premium = bool(card.select_one(".task-badge--premium"))
                    signals.append(
                        RawSignal(
                            id=f"freelance-task-{url.rstrip('/').split('/')[-1]}", source="freelance.ru",
                            source_url=url, external_id=url, author_identifier=None,
                            published_at=published_at, detected_at=now, title=title, text=f"{description} {category}".strip(),
                            metadata={
                                "source_scope": "PUBLIC_NEWEST_TASK_FEED",
                                "verification_status": "ACTIVE_PUBLIC_TASK_FEED" if not premium else "PUBLIC_TASK_PREMIUM_RESTRICTED",
                                "actionable_now": "YES" if not premium else "UNKNOWN",
                                "task_visibility": "PUBLIC_LISTING" if not premium else "PUBLIC_LISTING_PREMIUM_DETAIL",
                                "published_label": timestamp.get("title"), "category": category,
                            },
                            lead_type_hint="HOT_DEMAND",
                        )
                    )
        return policy, signals


def _parse_site_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Freelance.ru renders this feed timestamp in Moscow local time;
        # treating it as UTC creates future-dated signals and fake freshness.
        local = datetime.strptime(value.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=ZoneInfo("Europe/Moscow"))
        return local.astimezone(UTC)
    except ValueError:
        return None
