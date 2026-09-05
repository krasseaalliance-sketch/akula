from datetime import datetime
from zoneinfo import ZoneInfo

from app.service_scheduler import ServiceSpec, in_window, next_window_start


def test_campaign_window_is_makassar_and_end_is_exclusive():
    spec = ServiceSpec("campaign_engine", "Campaign", "campaign", "Asia/Makassar", "06:00", "22:00", 900)
    assert in_window(datetime(2026, 7, 27, 5, 59, tzinfo=ZoneInfo("Asia/Makassar")), spec) is False
    assert in_window(datetime(2026, 7, 27, 6, 0, tzinfo=ZoneInfo("Asia/Makassar")), spec) is True
    assert in_window(datetime(2026, 7, 27, 21, 59, tzinfo=ZoneInfo("Asia/Makassar")), spec) is True
    assert in_window(datetime(2026, 7, 27, 22, 0, tzinfo=ZoneInfo("Asia/Makassar")), spec) is False


def test_monitor_window_crosses_midnight_in_krasnoyarsk():
    spec = ServiceSpec("lead_monitor", "Monitor", "monitor", "Asia/Krasnoyarsk", "10:00", "00:00", 300)
    assert in_window(datetime(2026, 7, 27, 9, 59, tzinfo=ZoneInfo("Asia/Krasnoyarsk")), spec) is False
    assert in_window(datetime(2026, 7, 27, 10, 0, tzinfo=ZoneInfo("Asia/Krasnoyarsk")), spec) is True
    assert in_window(datetime(2026, 7, 27, 23, 59, tzinfo=ZoneInfo("Asia/Krasnoyarsk")), spec) is True
    assert in_window(datetime(2026, 7, 28, 0, 0, tzinfo=ZoneInfo("Asia/Krasnoyarsk")), spec) is False


def test_next_run_is_independent_for_each_scheduler():
    campaign = ServiceSpec("campaign_engine", "Campaign", "campaign", "Asia/Makassar", "06:00", "22:00", 900)
    monitor = ServiceSpec("lead_monitor", "Monitor", "monitor", "Asia/Krasnoyarsk", "10:00", "00:00", 300)
    now = datetime(2026, 7, 27, 12, 0, tzinfo=ZoneInfo("Asia/Krasnoyarsk"))
    assert next_window_start(now, campaign) != next_window_start(now, monitor)
