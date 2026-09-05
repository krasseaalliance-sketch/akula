from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ModelVersion:
    model_type: str
    version: str
    created_at: datetime
    supersedes: str | None
    change_reason: str
    input_evidence: tuple[str, ...]
    model_provider: str
    model_provider_version: str
    manual_override: bool = False


@dataclass(frozen=True)
class OperatorOverride:
    business_id: str
    field: str
    value: Any
    actor_id: str
    reason: str
    created_at: datetime
    supersedes_version: str


@dataclass(frozen=True)
class CampaignScope:
    campaign_id: str
    business_id: str
    offer_ids: tuple[str, ...]
    purpose: str
    billing_boundary: str = "EXTERNAL_COMMERCIAL_POLICY"


@dataclass(frozen=True)
class FeedbackEvent:
    business_id: str
    demand_id: str
    label: str
    actor_id: str
    created_at: datetime | None = None
    note: str | None = None


def new_model_version(model_type: str, version: str, evidence: tuple[str, ...], *, supersedes: str | None = None, reason: str = "initial generation", manual_override: bool = False) -> ModelVersion:
    return ModelVersion(model_type, version, datetime.now(UTC), supersedes, reason, evidence, "RULES", version, manual_override)


FEEDBACK_LABELS = frozenset({"TAKE", "SKIP", "GOOD_LEAD", "BAD_LEAD", "LOW_VALUE", "WRONG_SERVICE", "WRONG_GEO", "STALE", "CONTACTED", "REPLIED", "DISCUSSION", "WON", "LOST"})


def validate_feedback(event: FeedbackEvent) -> None:
    if event.label not in FEEDBACK_LABELS:
        raise ValueError(f"unsupported feedback label: {event.label}")
