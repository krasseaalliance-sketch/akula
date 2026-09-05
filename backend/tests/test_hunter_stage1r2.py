from __future__ import annotations

from runpy import run_path

_STAGE1R2 = run_path("tools/run_lead_hunter_stage1r2.py")
SOURCE_CLASSES = _STAGE1R2["SOURCE_CLASSES"]
_quality_decision = _STAGE1R2["_quality_decision"]
_quality_score = _STAGE1R2["_quality_score"]


def test_stage1r2_registry_has_ten_public_source_classes() -> None:
    assert 8 <= len(SOURCE_CLASSES) <= 12
    assert "freelance_marketplace" in {row[0] for row in SOURCE_CLASSES}
    assert "public_order_aggregator" in {row[0] for row in SOURCE_CLASSES}


def test_quality_score_rewards_fresh_actionable_stream() -> None:
    row = {"signals_seen": 12, "qualified": 5, "actionable": 5, "actionable_rate": 1.0, "median_age": 1.0, "false_positive_rate": 0.0}
    assert _quality_score(row) >= 90
    assert _quality_decision(row) == "RETAIN_AND_EXPAND"


def test_quality_score_does_not_promote_unactivated_source() -> None:
    row = {"signals_seen": 0, "qualified": 0, "actionable": 0}
    assert _quality_score(row) == 0
    assert _quality_decision(row) == "NOT_ACTIVATED"
