from __future__ import annotations

import json

import pytest

from app.hunter.sources import ManualJsonSourceAdapter


def _payload(status: str = "APPROVED_FOR_READ_ONLY_CAPTURE") -> dict[str, object]:
    return {
        "source_policy": {
            "source": "fixture public listing",
            "access_mode": "PUBLIC_HTTP_READ_CAPTURE",
            "public_scope": "PUBLIC_LISTING",
            "rate_limit": "ONE_PAGE_PER_RUN",
            "terms_risk": "REVIEW_REQUIRED",
            "automation_allowed": False,
            "data_retention_rule": "retain_public_url_and_minimal_excerpt_only",
            "status": status,
        },
        "signals": [
            {
                "id": "listing-1",
                "source": "fixture",
                "source_url": "https://example.test/listing/1",
                "external_id": "listing-1",
                "title": "Public request",
                "text": "Нужен сайт",
                "published_at": "2026-08-11T10:00:00+00:00",
                "detected_at": "2026-08-11T10:01:00+00:00",
                "metadata": {"verification_status": "PUBLIC_LISTING"},
            }
        ],
    }


def test_current_source_adapter_preserves_public_url_and_verification_provenance(tmp_path) -> None:
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")

    policy, signals = ManualJsonSourceAdapter(path).read()

    assert policy.status == "APPROVED_FOR_READ_ONLY_CAPTURE"
    assert signals[0].source_url == "https://example.test/listing/1"
    assert signals[0].metadata["verification_status"] == "PUBLIC_LISTING"


def test_unapproved_source_capture_is_rejected(tmp_path) -> None:
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(_payload("REJECTED"), ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="source policy is not approved"):
        ManualJsonSourceAdapter(path).read()
