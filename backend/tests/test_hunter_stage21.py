from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.hunter.dedupe import classify_duplicate, content_fingerprint
from app.hunter.freshness import classify_freshness
from app.hunter.models import RawSignal
from app.hunter.normalization import normalize_signal


def _signal(identifier: str, text: str) -> RawSignal:
    return RawSignal(
        id=identifier, source="fixture", source_url=f"https://example.test/{identifier}", external_id=identifier,
        author_identifier=None, published_at=datetime(2026, 8, 11, tzinfo=UTC),
        detected_at=datetime(2026, 8, 11, 0, 1, tzinfo=UTC), title="Request", text=text, metadata={},
    )


def test_incremental_dedupe_fingerprint_distinguishes_updated_content() -> None:
    old = {"source": "fixture", "external_id": "42", "title": "Website", "text": "Нужен корпоративный сайт компании"}
    updated = {**old, "text": "Нужен корпоративный сайт компании каталог"}

    assert content_fingerprint(old["text"]) != content_fingerprint(updated["text"])


def test_current_freshness_contract_pauses_stale_signals() -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)

    assert classify_freshness(now - timedelta(hours=2), now).bucket == "ULTRA_FRESH"
    assert classify_freshness(now - timedelta(days=10), now).bucket == "STALE"
    assert classify_freshness(now - timedelta(days=31), now).bucket == "DEAD"


def test_reposted_signal_is_not_reprocessed_as_a_new_demand() -> None:
    first = normalize_signal(_signal("a", "Нужен сайт для компании, бюджет 200000"))
    repost = normalize_signal(_signal("b", "Нужен сайт для компании, бюджет 200000"))

    assert classify_duplicate(repost, [first])[0] == "EXACT_DUPLICATE"
