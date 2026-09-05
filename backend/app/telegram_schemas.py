from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TelegramORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TelegramAccountCreate(BaseModel):
    workspace_id: str
    display_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    api_credential_reference: str | None = Field(default=None, max_length=500)


class TelegramAccountResponse(TelegramORM):
    id: str
    workspace_id: str
    integration_account_id: str
    display_name: str
    username: str | None
    phone_masked: str | None
    authorization_status: str
    safety_status: str
    connection_status: str
    last_successful_sync_at: datetime | None
    flood_wait_until: datetime | None
    manual_unlock_required: bool
    safety_lock: bool


class AuthorizationStartRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=40)


class AuthorizationCodeRequest(BaseModel):
    attempt_id: str
    code: str = Field(min_length=1, max_length=32)


class AuthorizationPasswordRequest(BaseModel):
    attempt_id: str
    password: str = Field(min_length=1, max_length=256)


class TelegramDialogResponse(TelegramORM):
    id: str
    workspace_id: str
    integration_account_id: str
    community_id: str | None
    external_dialog_id: str
    dialog_type: str
    title: str
    username: str | None
    is_public: bool
    is_joined: bool
    can_send_messages: bool
    can_view_history: bool
    has_slow_mode: bool
    slow_mode_seconds: int | None
    member_count: int | None
    last_synced_at: datetime | None


class SyncRequest(BaseModel):
    account_id: str
    dialog_id: str | None = None
    max_messages: int = Field(default=100, ge=1, le=1000)
    since: datetime | None = None


class ImportCommunityRequest(BaseModel):
    account_id: str | None = None
    title: str
    username: str | None = None
    url: str | None = None
    external_id: str
    language: str = "ru"
    geography: str | None = None
    category: str | None = None
    rules_text: str | None = None
    rules_url: str | None = None
    evidence: str | None = None
    evidence_url: str | None = None
    allowed_content_types: list[str] = Field(default_factory=list)
    allowed_days: list[str] = Field(default_factory=list)
    min_interval_hours: int | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = False


class DiscoveryRequest(BaseModel):
    account_id: str
    query: str = Field(min_length=2, max_length=300)
    profile_id: str | None = None


class CandidateDecision(BaseModel):
    review_status: Literal["ACCEPTED", "REJECTED"]


class RulesReviewRequest(BaseModel):
    approved: bool
    permission_type: Literal["POST"] = "POST"
    allowed_content_types: list[str] = Field(default_factory=list)
    allowed_days: list[str] = Field(default_factory=list)
    min_interval_hours: int = Field(default=24, ge=0, le=8760)
    expires_at: datetime | None = None


class LeadDiscoveryRequestV2(BaseModel):
    account_id: str
    dialog_id: str | None = None
    campaign_id: str | None = None
    max_messages: int = Field(default=100, ge=1, le=1000)


class IncidentResolveRequest(BaseModel):
    resolution_notes: str = Field(min_length=1, max_length=2000)


class SafetyLockRequest(BaseModel):
    reason: str = Field(default="Manual Telegram account safety lock", min_length=1, max_length=500)


class ImportRowsRequest(BaseModel):
    account_id: str | None = None
    rows: list[dict[str, Any]]
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = True
