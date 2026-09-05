from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DialogType = Literal[
    "PERSON",
    "GROUP",
    "SUPERGROUP",
    "CHANNEL",
    "BOT",
    "SAVED_MESSAGES",
    "SERVICE",
    "UNKNOWN",
]
Eligibility = Literal["ELIGIBLE", "READ_ONLY", "NOT_ELIGIBLE", "MANUAL_REVIEW"]
ReviewStatus = Literal[
    "UNREVIEWED",
    "IN_REVIEW",
    "REVIEWED",
    "SKIPPED",
    "NEEDS_CONTEXT",
    "ARCHIVED_FROM_TRIAGE",
]


class TriageDecisionInput(BaseModel):
    dialog_id: str
    expected_version: int | None = Field(default=None, ge=1)
    review_status: ReviewStatus = "REVIEWED"
    manual_dialog_type: DialogType = "UNKNOWN"
    manual_eligibility: Eligibility = "MANUAL_REVIEW"
    operator_notes: str | None = Field(default=None, max_length=4000)
    needs_context_reason: str | None = Field(default=None, max_length=2000)
    collection_slugs: list[str] = Field(default_factory=list, max_length=30)
    tag_slugs: list[str] = Field(default_factory=list, max_length=30)


class BatchSaveRequest(BaseModel):
    decisions: list[TriageDecisionInput] = Field(min_length=1, max_length=100)
    advance: bool = True


class DecisionPatchRequest(BaseModel):
    expected_version: int = Field(ge=1)
    review_status: ReviewStatus | None = None
    manual_dialog_type: DialogType | None = None
    manual_eligibility: Eligibility | None = None
    operator_notes: str | None = Field(default=None, max_length=4000)
    needs_context_reason: str | None = Field(default=None, max_length=2000)
    collection_slugs: list[str] | None = Field(default=None, max_length=30)
    tag_slugs: list[str] | None = Field(default=None, max_length=30)


class BulkActionRequest(BaseModel):
    dialog_ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal[
        "MARK_PERSONAL",
        "MARK_BOT",
        "EXCLUDE_CAMPAIGNS",
        "ADD_COLLECTION",
        "REMOVE_COLLECTION",
        "ADD_TAG",
        "REMOVE_TAG",
        "SKIP",
        "NEEDS_CONTEXT",
    ]
    collection_slug: str | None = Field(default=None, max_length=180)
    tag_slug: str | None = Field(default=None, max_length=140)
    needs_context_reason: str | None = Field(default=None, max_length=2000)
    confirm_overwrite: bool = False


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, max_length=180)


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=140)


class ReturnToQueueRequest(BaseModel):
    expected_version: int = Field(ge=1)
