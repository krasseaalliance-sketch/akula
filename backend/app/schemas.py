from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WorkspaceStatus = Literal["ACTIVE", "INACTIVE", "ARCHIVED"]
MemberRole = Literal["OWNER", "ADMIN", "MANAGER", "OPERATOR", "ANALYST", "VIEWER"]
MemberStatus = Literal["ACTIVE", "INVITED", "INACTIVE"]
OfferType = Literal["TRAVEL", "YACHT_TRIP", "WEBSITE", "TELEGRAM_BOT", "MOBILE_APP", "OTHER"]
CampaignStatus = Literal["DRAFT", "READY", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"]
Platform = Literal["TELEGRAM", "MOCK"]
CommunityStatus = Literal["NEEDS_REVIEW", "APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED"]
PermissionType = Literal["POST"]
CommunityPermissionStatus = Literal["ACTIVE", "INACTIVE", "REVIEW_REQUIRED", "EXPIRED"]
PublicationType = Literal["COMPANION_SEARCH", "EVENT", "SERVICE", "CONTENT", "OTHER"]
SourcePlatform = Literal["TELEGRAM", "MOCK"]
LeadStatus = Literal[
    "NEW", "REVIEW", "QUALIFIED", "REJECTED_IRRELEVANT", "REJECTED_SPAM",
    "DO_NOT_CONTACT", "CONVERTED", "LOST",
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(ORMModel):
    id: str
    email: str
    name: str
    status: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=160)
    timezone: str = "Asia/Krasnoyarsk"
    default_language: str = "ru"


class WorkspacePatch(BaseModel):
    name: str | None = None
    timezone: str | None = None
    default_language: str | None = None
    status: WorkspaceStatus | None = None


class WorkspaceResponse(ORMModel):
    id: str
    name: str
    slug: str
    owner_id: str
    status: str
    timezone: str
    default_language: str


class CompanyIn(BaseModel):
    workspace_id: str
    legal_name: str
    public_name: str
    description: str | None = None
    website: str | None = None
    country: str | None = None
    city: str | None = None


class CompanyPatch(BaseModel):
    legal_name: str | None = None
    public_name: str | None = None
    description: str | None = None
    website: str | None = None
    country: str | None = None
    city: str | None = None
    status: WorkspaceStatus | None = None


class CompanyResponse(ORMModel):
    id: str
    workspace_id: str
    legal_name: str
    public_name: str
    description: str | None
    website: str | None
    country: str | None
    city: str | None
    status: str


class BrandIn(BaseModel):
    company_id: str
    name: str
    description: str | None = None
    positioning: str | None = None
    tone_of_voice: str | None = None
    default_language: str = "ru"


class BrandPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    positioning: str | None = None
    tone_of_voice: str | None = None
    status: WorkspaceStatus | None = None


class BrandResponse(ORMModel):
    id: str
    company_id: str
    name: str
    description: str | None
    positioning: str | None
    tone_of_voice: str | None
    default_language: str
    status: str


class OfferIn(BaseModel):
    brand_id: str
    name: str
    type: OfferType = "OTHER"
    description: str | None = None
    geography: str | None = None
    price: float | None = None
    currency: str = "RUB"
    facts: dict[str, Any] | None = None


class OfferResponse(ORMModel):
    id: str
    brand_id: str
    name: str
    type: str
    description: str | None
    geography: str | None
    price: float | None
    currency: str
    status: str


class CampaignIn(BaseModel):
    brand_id: str
    offer_id: str | None = None
    name: str
    objective: str = "Lead discovery"
    geography: str | None = None
    language: str = "ru"
    daily_limit: int = Field(default=50, ge=1, le=10000)
    campaign_type: Literal["LEAD_DISCOVERY"] = "LEAD_DISCOVERY"


class CampaignPatch(BaseModel):
    name: str | None = None
    objective: str | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=10000)
    status: CampaignStatus | None = None


class CampaignResponse(ORMModel):
    id: str
    brand_id: str
    offer_id: str | None
    name: str
    objective: str
    geography: str | None
    language: str
    daily_limit: int
    status: str
    campaign_type: str


class AudienceIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    criteria: dict[str, Any] | None = None


class AudienceResponse(ORMModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    criteria: dict[str, Any] | None
    status: str


class CommunityIn(BaseModel):
    workspace_id: str
    platform: Platform = "TELEGRAM"
    external_id: str
    title: str
    username: str | None = None
    url: str | None = None
    description: str | None = None
    geography: str | None = None
    category: str | None = None


class CommunityPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    rules_text: str | None = None
    posting_status: CommunityStatus | None = None


class CommunityResponse(ORMModel):
    id: str
    workspace_id: str
    platform: str
    external_id: str
    title: str
    username: str | None
    url: str | None
    description: str | None
    geography: str | None
    category: str | None
    member_count: int
    relevance_score: float
    posting_status: str


class CommunityPermissionIn(BaseModel):
    community_id: str
    permission_type: PermissionType = "POST"
    status: CommunityPermissionStatus = "ACTIVE"


class CommunityPermissionResponse(ORMModel):
    id: str
    workspace_id: str
    community_id: str
    permission_type: str
    status: str
    approved_by: str | None
    expires_at: Any | None


class LeadResponse(ORMModel):
    id: str
    workspace_id: str
    campaign_id: str | None
    source_platform: str
    source_url: str | None
    source_message_id: str | None
    source_dialog_external_id: str | None
    source_message_url: str | None
    author_name: str | None
    author_username: str | None
    raw_text: str
    detected_need: str | None
    score: float
    confidence: float
    status: str
    assigned_to: str | None
    normalized_text: str | None
    dedupe_key: str | None
    intent: str | None
    pain: str | None
    need: str | None
    intent_confidence: float
    pain_confidence: float
    need_confidence: float
    offer_match_id: str | None
    offer_match_score: float
    first_contact_recommendation: str | None
    recommendation_reason: str | None
    ai_provider: str | None
    ai_model: str | None


class LeadPatch(BaseModel):
    status: LeadStatus | None = None
    detected_need: str | None = None


class GenerateMessageRequest(BaseModel):
    campaign_id: str
    lead_id: str | None = None
    community_id: str | None = None
    audience_id: str | None = None
    publication_type: PublicationType = "OTHER"


class MessageResponse(ORMModel):
    id: str
    campaign_id: str | None
    community_id: str | None
    lead_id: str | None
    audience_id: str | None
    message_type: str
    language: str
    content: str
    model_name: str
    validation_status: str
    approval_status: str
    facts_snapshot: dict[str, Any] | None
    generation_context: dict[str, Any] | None
    prompt_version: str
    similarity_score: float | None
    human_writing_run_id: str | None = None
    human_variant_id: str | None = None
    naturalness_score: float | None = None
    human_similarity_score: float | None = None
    human_critic: dict[str, Any] | None = None


class PublicationIn(BaseModel):
    message_draft_id: str
    campaign_id: str | None = None
    community_id: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=200)


class PublicationResponse(ORMModel):
    id: str
    message_draft_id: str
    campaign_id: str | None
    community_id: str | None
    status: str
    external_message_id: str | None
    error_code: str | None
    error_message: str | None
    retry_count: int
    queued_at: Any | None
    sent_at: Any | None
    dry_run: bool


class LeadDiscoveryRequest(BaseModel):
    workspace_id: str
    campaign_id: str | None = None
    scenario: str = Field(min_length=2, max_length=64)
    raw_text: str | None = None
    source_platform: SourcePlatform = "MOCK"


class QueueJobResponse(ORMModel):
    id: str
    publication_id: str
    status: str
    attempts: int
    max_attempts: int
    correlation_id: str
    trace_id: str
    idempotency_key: str
    error_code: str | None
    error_message: str | None


class SafetyStateResponse(BaseModel):
    emergency_stop: bool
    safety_lock: bool


class PermissionCheckRequest(BaseModel):
    permission: str


class PermissionCheckResponse(BaseModel):
    allowed: bool
    role: str
    permission: str


class ConversationResponse(ORMModel):
    id: str
    workspace_id: str
    external_chat_id: str
    lead_id: str | None
    campaign_id: str | None
    status: str


class ReplyRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
