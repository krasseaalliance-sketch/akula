from __future__ import annotations

import json
from datetime import UTC, datetime

from app.hunter.pipeline import HunterPipeline
from app.hunter.sources import (
    FreelanceNewestTasksAdapter,
    ManualJsonSourceAdapter,
    MyWorkFinderOrdersAdapter,
    PublicTelegramChannelAdapter,
)


def _capture() -> dict[str, object]:
    return {
        "source_policy": {
            "source": "fixture public order feed",
            "access_mode": "PUBLIC_HTTP_READ_CAPTURE",
            "public_scope": "PUBLIC_ORDER_FEED",
            "rate_limit": "ONE_PAGE_PER_RUN",
            "terms_risk": "REVIEW_REQUIRED",
            "automation_allowed": False,
            "data_retention_rule": "retain_public_url_and_minimal_excerpt_only",
        },
        "signals": [
            {
                "id": "order-1",
                "source": "fixture",
                "source_url": "https://example.test/order/1",
                "external_id": "order-1",
                "title": "Website request",
                "text": "Нужен сайт для компании, бюджет 200000",
                "published_at": "2026-08-11T10:00:00+00:00",
                "detected_at": "2026-08-11T10:01:00+00:00",
                "metadata": {"actionable_now": "YES", "verification_status": "FIXTURE"},
            }
        ],
    }


def test_current_read_only_source_registry_contains_real_adapters() -> None:
    assert {
        FreelanceNewestTasksAdapter,
        ManualJsonSourceAdapter,
        MyWorkFinderOrdersAdapter,
        PublicTelegramChannelAdapter,
    }


def test_current_pipeline_keeps_a_fresh_actionable_fixture_as_a_lead(tmp_path) -> None:
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(_capture(), ensure_ascii=False), encoding="utf-8")

    result = HunterPipeline().run(str(path), now=datetime(2026, 8, 11, 12, tzinfo=UTC))

    assert result.signals_ingested == 1
    assert result.signals_analyzed == 1
    assert result.leads
    assert result.leads[0].source_url == "https://example.test/order/1"
    assert result.metrics["actionable_demand"] == 1
