from datetime import UTC, datetime

from app.hunter.sources.freelance_tasks import _parse_site_datetime


def test_freelance_feed_timestamp_is_converted_from_moscow_to_utc():
    parsed = _parse_site_datetime("12.08.2026 12:00")
    assert parsed == datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
