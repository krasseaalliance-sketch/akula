from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

_STAGE2 = run_path("tools/run_lead_hunter_stage2.py")
SOURCE_CATALOG = _STAGE2["SOURCE_CATALOG"]
_schedule = _STAGE2["_schedule"]
demand_fingerprint = _STAGE2["demand_fingerprint"]


def test_stage2_registry_has_twelve_source_classes_and_adapter_contract() -> None:
    required = {"source_id", "source_class", "endpoint", "access_mode", "status", "schedule_class", "cost_class"}
    assert len(SOURCE_CATALOG) == 12
    assert all(required <= row.keys() for row in SOURCE_CATALOG)
    assert sum(row["status"] == "ACTIVE" for row in SOURCE_CATALOG) == 7
    assert sum(row["status"] == "CANDIDATE" for row in SOURCE_CATALOG) == 5


def test_cross_source_fingerprint_ignores_order_id_and_url() -> None:
    first = {"id": "a-1", "title": "Создать интернет-магазин для мебельной компании", "text": "Нужны каталог и CRM https://one.example/"}
    repost = {"id": "b-9", "title": "Создать интернет-магазин для мебельной компании", "text": "Нужны каталог и CRM https://two.example/"}
    assert demand_fingerprint(first) == demand_fingerprint(repost)


def test_scheduler_is_score_ordered_and_candidate_sources_do_not_enter_queue() -> None:
    rows = [
        {"source_id": "low", "source": "low", "status": "ACTIVE", "source_economic_score": 10, "cost_class": "FREE_AUTOMATED"},
        {"source_id": "high", "source": "high", "status": "ACTIVE", "source_economic_score": 70, "cost_class": "FREE_AUTOMATED"},
        {"source_id": "candidate", "source": "candidate", "status": "CANDIDATE", "source_economic_score": 100, "cost_class": "FREE_AUTOMATED"},
    ]
    queue = _schedule(rows, datetime(2026, 8, 11, tzinfo=UTC))
    assert [item["source"] for item in queue] == ["high", "low"]
    assert queue[0]["interval_minutes"] == 10
    assert queue[1]["interval_minutes"] == 180


def test_generated_stage2_artifacts_keep_provenance_health_and_no_outbound() -> None:
    root = Path(__file__).resolve().parents[2]
    registry_path = next((root / "artifacts").glob("lead_hunter_stage2_source_registry_*.json"))
    health_path = next((root / "artifacts").glob("lead_hunter_stage2_source_health_*.json"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    health = json.loads(health_path.read_text(encoding="utf-8"))
    active = [row for row in registry["sources"] if row["status"] == "ACTIVE"]
    assert active
    assert all({"source_id", "endpoint", "parser_version", "last_scan_at", "source_health", "source_economic_score"} <= row.keys() for row in active)
    assert all({"source", "source_health", "parser_success", "timestamp_extraction_rate", "duplicate_rate"} <= row.keys() for row in health["sources"])
    report = (root / "LEAD_HUNTER_STAGE_2_REPORT.md").read_text(encoding="utf-8")
    assert "Outreach" in report and "forbidden" in report.casefold()
    assert "OPPORTUNITY" in report
