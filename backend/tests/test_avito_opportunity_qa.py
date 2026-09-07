from __future__ import annotations

from datetime import UTC, datetime

from app.hunter.dedupe import classify_duplicate, content_fingerprint
from app.hunter.models import RawSignal
from app.hunter.normalization import normalize_signal


def _signal(text: str, identifier: str, source: str = "fixture") -> object:
    return RawSignal(
        id=identifier,
        source=source,
        source_url=f"https://example.test/orders/{identifier}",
        external_id=identifier,
        author_identifier=None,
        published_at=datetime(2026, 8, 11, tzinfo=UTC),
        detected_at=datetime(2026, 8, 11, 0, 1, tzinfo=UTC),
        title="Public project request",
        text=text,
        metadata={"source_scope": "PUBLIC_PAGE_CAPTURE"},
    )


def test_similar_public_listings_are_deduplicated_by_current_hunter_contract() -> None:
    first = normalize_signal(_signal("Нужен сайт для строительной компании, бюджет 200000", "one"))
    repost = normalize_signal(_signal("Нужен сайт для строительной компании, бюджет 200000", "two", "another-source"))

    assert classify_duplicate(repost, [first]) == ("EXACT_DUPLICATE", 1.0)


def test_demand_fingerprint_is_stable_for_reordered_words() -> None:
    assert content_fingerprint("Нужен сайт бюджет 200000 для компании") == content_fingerprint(
        "Для компании нужен сайт бюджет 200000"
    )


def test_different_public_requests_remain_unrelated() -> None:
    first = normalize_signal(_signal("Нужен сайт для строительной компании", "one"))
    other = normalize_signal(_signal("Нужна автоматизация складской логистики", "two", "another-source"))

    assert classify_duplicate(other, [first])[0] == "UNRELATED"
