from __future__ import annotations

import json
from datetime import UTC, datetime

from app.hunter.dedupe import classify_duplicate
from app.hunter.normalization import normalize_signal
from app.hunter.pipeline import HunterPipeline
from app.hunter.sources import ManualJsonSourceAdapter
from app.hunter.models import RawSignal


def _policy() -> dict[str, object]:
    return {
        "source": "fixture public source",
        "access_mode": "PUBLIC_HTTP_READ_CAPTURE",
        "public_scope": "PUBLIC_ORDER_FEED",
        "rate_limit": "ONE_PAGE_PER_RUN",
        "terms_risk": "REVIEW_REQUIRED",
        "automation_allowed": False,
        "data_retention_rule": "retain_public_url_and_minimal_excerpt_only",
    }


def _signal(identifier: str, url: str, source: str = "fixture") -> dict[str, object]:
    return {
        "id": identifier,
        "source": source,
        "source_url": url,
        "external_id": identifier,
        "title": "Website request",
        "text": "Нужен сайт для строительной компании, бюджет 200000",
        "published_at": "2026-08-11T10:00:00+00:00",
        "detected_at": "2026-08-11T10:01:00+00:00",
        "metadata": {"actionable_now": "YES", "verification_status": "FIXTURE"},
    }


def test_current_manual_source_contract_preserves_policy_and_signals(tmp_path) -> None:
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"source_policy": _policy(), "signals": [_signal("a", "https://example.test/a")]}, ensure_ascii=False), encoding="utf-8")

    policy, signals = ManualJsonSourceAdapter(path).read()

    assert policy.public_scope == "PUBLIC_ORDER_FEED"
    assert signals[0].external_id == "a"


def test_current_dedupe_contract_detects_reposts_across_sources() -> None:
    first = RawSignal(
        id="a", source="one", source_url="https://example.test/a", external_id="a",
        author_identifier=None, published_at=None, detected_at=datetime(2026, 8, 11, tzinfo=UTC),
        title="Website request", text="Нужен сайт для строительной компании, бюджет 200000", metadata={},
    )
    repost = RawSignal(
        id="b", source="two", source_url="https://example.test/b", external_id="b",
        author_identifier=None, published_at=None, detected_at=datetime(2026, 8, 11, tzinfo=UTC),
        title="Website request", text="Нужен сайт для строительной компании, бюджет 200000", metadata={},
    )

    assert classify_duplicate(normalize_signal(repost), [normalize_signal(first)])[0] == "EXACT_DUPLICATE"


def test_current_pipeline_reports_source_provenance_without_outbound_actions(tmp_path) -> None:
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"source_policy": _policy(), "signals": [_signal("a", "https://example.test/a")]}, ensure_ascii=False), encoding="utf-8")

    result = HunterPipeline().run(str(path), now=datetime(2026, 8, 11, 12, tzinfo=UTC))

    assert result.source_policies[0].status == "APPROVED_FOR_READ_ONLY_CAPTURE"
    assert result.metrics["source_metrics"]["fixture"]["signals_seen"] == 1
    assert result.metrics["source_metrics"]["fixture"]["manual_reviewed"] == 0
