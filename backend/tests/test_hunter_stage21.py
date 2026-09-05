from __future__ import annotations

import json
from pathlib import Path
from runpy import run_path

_STAGE21 = run_path("tools/run_lead_hunter_stage21.py")
_event_status = _STAGE21["_event_status"]
_schedule = _STAGE21["_schedule"]


def test_incremental_cursor_distinguishes_new_updated_and_previous() -> None:
    row = {"source": "test", "external_id": "42", "id": "signal-42", "title": "Build site", "text": "catalog"}
    cursor = {"seen_signals": {}}
    assert _event_status(row, cursor) == "NEW"
    cursor["seen_signals"]["test|42"] = {"content_hash": "wrong"}
    assert _event_status(row, cursor) == "UPDATED"
    cursor["seen_signals"]["test|42"] = {"content_hash": _STAGE21["_content_hash"](row)}
    assert _event_status(row, cursor) == "PREVIOUSLY_SEEN"


def test_operational_health_does_not_follow_commercial_yield() -> None:
    assert _schedule("HEALTHY", "LOW", "public_telegram_project_channel", 20) == ("SLOW", 180)
    assert _schedule("HEALTHY", "UNKNOWN", "public_telegram_project_channel", None) == ("NORMAL", 45)
    assert _schedule("BROKEN", "HIGH", "public_telegram_project_channel", 90) == ("PAUSED", None)


def test_live_stage21_artifacts_prove_recovery_and_dedupe() -> None:
    root = Path(__file__).resolve().parents[2]
    state = json.loads((root / "artifacts/lead_hunter_stage21_state.json").read_text(encoding="utf-8"))
    assert state["version"] == 2
    assert len(state["cycles"]) >= 2
    assert state["cycles"][0]["new_money_now"] >= 1
    assert state["cycles"][-1]["new_money_now"] == 0
    assert set(state["recovery"]["restored_sources"]) >= {
        "myworkfinder.ru",
        "telegram:@job_developer",
        "telegram:@digitaltender",
        "telegram:@FreelancehuntProjects",
    }
    report = (root / "LEAD_HUNTER_STAGE_2_1_REPORT.md").read_text(encoding="utf-8")
    assert "Stage 3 is not started." in report
    assert "outreach" in report.casefold()
