"""Controlled values shared by API, domain validation and database checks."""

from typing import Final

USER_STATUS: Final = ("ACTIVE", "INACTIVE", "SUSPENDED")
WORKSPACE_STATUS: Final = ("ACTIVE", "INACTIVE", "ARCHIVED")
MEMBER_ROLE: Final = ("OWNER", "ADMIN", "MANAGER", "OPERATOR", "ANALYST", "VIEWER")
MEMBER_STATUS: Final = ("ACTIVE", "INVITED", "INACTIVE")
OFFER_TYPE: Final = ("TRAVEL", "YACHT_TRIP", "WEBSITE", "TELEGRAM_BOT", "MOBILE_APP", "OTHER")
CAMPAIGN_STATUS: Final = ("DRAFT", "READY", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED")
CAMPAIGN_TYPE: Final = ("LEAD_DISCOVERY",)
PUBLICATION_POLICY: Final = ("APPROVAL_REQUIRED",)
PLATFORM: Final = ("TELEGRAM", "AVITO", "MOCK")
COMMUNITY_STATUS: Final = ("NEEDS_REVIEW", "APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED")
COMMUNITY_PERMISSION_STATUS: Final = ("ACTIVE", "INACTIVE", "REVIEW_REQUIRED", "EXPIRED")
PERMISSION_TYPE: Final = ("POST",)
SOURCE_PLATFORM: Final = ("TELEGRAM", "AVITO", "MOCK")
LEAD_TYPE: Final = ("INBOUND",)
LEAD_STATUS: Final = (
    "NEW",
    "REVIEW",
    "QUALIFIED",
    "REJECTED_IRRELEVANT",
    "REJECTED_SPAM",
    "DO_NOT_CONTACT",
    "CONVERTED",
    "LOST",
)
MESSAGE_TYPE: Final = ("DIRECT_RESPONSE",)
VALIDATION_STATUS: Final = ("VALID", "INVALID")
APPROVAL_STATUS: Final = ("PENDING", "APPROVED", "REJECTED")
PUBLICATION_STATUS: Final = (
    "DRAFT",
    "QUEUED",
    "RUNNING",
    "BLOCKED_BY_POLICY",
    "PAUSED_BY_SAFETY",
    "DRY_RUN",
    "SENT",
    "FAILED",
    "CANCELLED",
    "PAUSED",
)
JOB_STATUS: Final = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "DEAD", "PAUSED", "CANCELLED")
CONVERSATION_STATUS: Final = ("OPEN", "CLOSED", "PAUSED")
MESSAGE_DIRECTION: Final = ("INBOUND", "OUTBOUND")
INTEGRATION_STATUS: Final = ("DISCONNECTED", "CONNECTED", "ERROR")
HEALTH_STATUS: Final = ("UNKNOWN", "HEALTHY", "UNHEALTHY")

TELEGRAM_ACCOUNT_TYPE: Final = ("USER", "BOT")
TELEGRAM_AUTHORIZATION_STATUS: Final = (
    "NOT_CONFIGURED", "CREDENTIALS_REQUIRED", "CODE_REQUIRED", "PASSWORD_REQUIRED",
    "AUTHORIZED", "REVOKED", "FAILED",
)
TELEGRAM_SAFETY_STATUS: Final = (
    "HEALTHY", "DEGRADED", "FLOOD_WAIT", "RATE_LIMITED", "SPAM_WARNING",
    "RESTRICTED", "SAFETY_LOCK", "DISCONNECTED", "REVOKED",
)
TELEGRAM_CONNECTION_STATUS: Final = ("DISCONNECTED", "CONNECTING", "CONNECTED", "ERROR")
TELEGRAM_ATTEMPT_STATUS: Final = ("PENDING", "CODE_SENT", "PASSWORD_REQUIRED", "COMPLETED", "FAILED", "EXPIRED")
TELEGRAM_DIALOG_TYPE: Final = ("USER", "GROUP", "SUPERGROUP", "CHANNEL", "BOT", "SAVED_MESSAGES", "UNKNOWN")
TELEGRAM_SYNC_TYPE: Final = ("DIALOGS", "RULES", "MESSAGES", "INCOMING", "HEALTH")
TELEGRAM_SYNC_STATUS: Final = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "PAUSED")
TELEGRAM_INCIDENT_TYPE: Final = (
    "FLOOD_WAIT", "SPAM_WARNING", "AUTH_REVOKED", "SESSION_ERROR", "ACCOUNT_RESTRICTED",
    "CONNECTION_FAILURE", "RATE_LIMIT", "UNEXPECTED_API_ERROR", "POLICY_BYPASS_ATTEMPT",
    "SECRET_EXPOSURE", "OTHER",
)
TELEGRAM_SEVERITY: Final = ("INFO", "WARNING", "HIGH", "CRITICAL")
TELEGRAM_INCIDENT_STATUS: Final = ("OPEN", "RESOLVED")
TELEGRAM_CANDIDATE_STATUS: Final = ("NEW", "ACCEPTED", "REJECTED")
TELEGRAM_RULE_REVIEW_STATUS: Final = ("PENDING", "APPROVED", "REJECTED", "REVIEW_REQUIRED")
TELEGRAM_IMPORT_STATUS: Final = ("PREVIEW", "DRY_RUN", "IMPORTED", "FAILED")
TELEGRAM_PUBLICATION_RESULT_STATUS: Final = ("ACCEPTED", "DRY_RUN", "FAILED", "BLOCKED")
DISCOVERY_PROFILE_STATUS: Final = ("ACTIVE", "PAUSED", "ARCHIVED")
PUBLICATION_TYPE: Final = (
    "COMPANION_SEARCH", "COMMERCIAL_OFFER", "YACHT_GROUP_TRIP", "YACHT_PRIVATE_BOOKING",
    "QUIZ_QUESTION", "QUIZ_MINIGAME", "QUIZ_DUEL", "GIVEAWAY", "EVENT_ANNOUNCEMENT",
    "DIGITAL_SERVICE_OFFER", "PARTNERSHIP_REQUEST", "USEFUL_CONTENT", "OTHER",
)
AI_PROFILE_STATUS: Final = ("DRAFT", "ACTIVE", "PAUSED", "ARCHIVED")
AI_RUN_STATUS: Final = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL")
RECOMMENDATION_STATUS: Final = ("DRAFT", "APPROVED", "REJECTED", "USED", "EXPIRED")


CHECKS: Final = (
    ("users", "status", "ck_users_status", USER_STATUS),
    ("workspaces", "status", "ck_workspaces_status", WORKSPACE_STATUS),
    ("workspace_members", "role", "ck_workspace_members_role", MEMBER_ROLE),
    ("workspace_members", "status", "ck_workspace_members_status", MEMBER_STATUS),
    ("companies", "status", "ck_companies_status", WORKSPACE_STATUS),
    ("brands", "status", "ck_brands_status", WORKSPACE_STATUS),
    ("offers", "type", "ck_offers_type", OFFER_TYPE),
    ("offers", "status", "ck_offers_status", WORKSPACE_STATUS),
    ("campaigns", "status", "ck_campaigns_status", CAMPAIGN_STATUS),
    ("campaigns", "campaign_type", "ck_campaigns_type", CAMPAIGN_TYPE),
    ("campaigns", "publication_policy", "ck_campaigns_publication_policy", PUBLICATION_POLICY),
    ("audiences", "status", "ck_audiences_status", WORKSPACE_STATUS),
    ("communities", "platform", "ck_communities_platform", PLATFORM),
    ("communities", "posting_status", "ck_communities_posting_status", COMMUNITY_STATUS),
    ("community_permissions", "permission_type", "ck_community_permissions_type", PERMISSION_TYPE),
    ("community_permissions", "status", "ck_community_permissions_status", COMMUNITY_PERMISSION_STATUS),
    ("leads", "source_platform", "ck_leads_source_platform", SOURCE_PLATFORM),
    ("leads", "lead_type", "ck_leads_type", LEAD_TYPE),
    ("leads", "status", "ck_leads_status", LEAD_STATUS),
    ("message_drafts", "message_type", "ck_message_drafts_type", MESSAGE_TYPE),
    ("message_drafts", "validation_status", "ck_message_drafts_validation", VALIDATION_STATUS),
    ("message_drafts", "approval_status", "ck_message_drafts_approval", APPROVAL_STATUS),
    ("publications", "status", "ck_publications_status", PUBLICATION_STATUS),
    ("publication_jobs", "status", "ck_publication_jobs_status", JOB_STATUS),
    ("conversations", "status", "ck_conversations_status", CONVERSATION_STATUS),
    ("conversation_messages", "direction", "ck_conversation_messages_direction", MESSAGE_DIRECTION),
    ("integration_accounts", "platform", "ck_integrations_platform", PLATFORM),
    ("integration_accounts", "status", "ck_integrations_status", INTEGRATION_STATUS),
    ("integration_accounts", "health_status", "ck_integrations_health", HEALTH_STATUS),
    ("telegram_account_profiles", "account_type", "ck_telegram_profiles_account_type", TELEGRAM_ACCOUNT_TYPE),
    ("telegram_account_profiles", "authorization_status", "ck_telegram_profiles_auth_status", TELEGRAM_AUTHORIZATION_STATUS),
    ("telegram_account_profiles", "safety_status", "ck_telegram_profiles_safety_status", TELEGRAM_SAFETY_STATUS),
    ("telegram_account_profiles", "connection_status", "ck_telegram_profiles_connection_status", TELEGRAM_CONNECTION_STATUS),
    ("telegram_authorization_attempts", "status", "ck_telegram_attempts_status", TELEGRAM_ATTEMPT_STATUS),
    ("telegram_dialogs", "dialog_type", "ck_telegram_dialogs_type", TELEGRAM_DIALOG_TYPE),
    ("telegram_sync_cursors", "sync_type", "ck_telegram_cursors_type", TELEGRAM_SYNC_TYPE),
    ("telegram_sync_cursors", "status", "ck_telegram_cursors_status", TELEGRAM_SYNC_STATUS),
    ("telegram_account_incidents", "incident_type", "ck_telegram_incidents_type", TELEGRAM_INCIDENT_TYPE),
    ("telegram_account_incidents", "severity", "ck_telegram_incidents_severity", TELEGRAM_SEVERITY),
    ("telegram_account_incidents", "status", "ck_telegram_incidents_status", TELEGRAM_INCIDENT_STATUS),
    ("telegram_community_candidates", "review_status", "ck_telegram_candidates_status", TELEGRAM_CANDIDATE_STATUS),
    ("telegram_rule_analyses", "review_status", "ck_telegram_rules_status", TELEGRAM_RULE_REVIEW_STATUS),
    ("telegram_import_runs", "status", "ck_telegram_imports_status", TELEGRAM_IMPORT_STATUS),
    ("telegram_publication_results", "result_status", "ck_telegram_publication_results_status", TELEGRAM_PUBLICATION_RESULT_STATUS),
    ("discovery_profiles", "status", "ck_discovery_profiles_status", DISCOVERY_PROFILE_STATUS),
    ("message_drafts", "publication_type", "ck_message_drafts_publication_type", PUBLICATION_TYPE),
    ("ai_search_profiles", "status", "ck_ai_search_profiles_status", AI_PROFILE_STATUS),
    ("lead_intelligence_runs", "status", "ck_lead_intelligence_runs_status", AI_RUN_STATUS),
    ("message_recommendations", "status", "ck_message_recommendations_status", RECOMMENDATION_STATUS),
)


def sql_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
    return f'"{column}" IN ({quoted})'
