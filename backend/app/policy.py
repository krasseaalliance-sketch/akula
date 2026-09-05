from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

POLICY_VERSION = "stage1-policy-v2"
POLICIES = (
    "WORKSPACE_ACTIVE",
    "COMPANY_ACTIVE",
    "BRAND_ACTIVE",
    "CAMPAIGN_ACTIVE",
    "OFFER_ACTIVE",
    "COMMUNITY_APPROVED",
    "COMMUNITY_PERMISSION_ACTIVE",
    "MESSAGE_APPROVED",
    "CAMPAIGN_DAILY_LIMIT",
    "COMMUNITY_INTERVAL",
    "INTEGRATION_HEALTHY",
    "NO_EMERGENCY_STOP",
    "NO_SAFETY_LOCK",
    "CONTENT_TYPE_ALLOWED",
    "PUBLICATION_DATE_ALLOWED",
    "PUBLICATION_NOT_DUPLICATE",
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    reason: str
    decision: str = field(init=False)
    checked_policies: list[str] = field(default_factory=list)
    denied_policies: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    policy_version: str = POLICY_VERSION
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", "ALLOW" if self.allowed else "DENY")


class PolicyEngine:
    """The only decision boundary allowed to approve outbound publication."""

    def __init__(self, *, safety_lock: bool = False, publication_mode: str = "DRY_RUN"):
        self.safety_lock = safety_lock
        self.publication_mode = publication_mode

    def can_activate_campaign(self, *, role: str, status: str) -> PolicyDecision:
        checked = ["NO_SAFETY_LOCK", "CAMPAIGN_ACTIVE"]
        if self.safety_lock:
            return self._deny(
                "SAFETY_LOCK", "System safety lock is enabled", checked, ["NO_SAFETY_LOCK"]
            )
        if role not in {"OWNER", "ADMIN", "MANAGER"}:
            return self._deny("FORBIDDEN", "campaign.activate permission is required", checked, [])
        if status in {"ARCHIVED", "COMPLETED"}:
            return self._deny(
                "INVALID_STATE",
                "Archived or completed campaigns cannot be activated",
                checked,
                ["CAMPAIGN_ACTIVE"],
            )
        return self._allow(checked)

    def can_publish(
        self,
        *,
        safety_lock: bool,
        campaign_status: str,
        message_approved: bool,
        community_status: str,
        sent_today: int,
        daily_limit: int,
        workspace_status: str = "ACTIVE",
        company_status: str = "ACTIVE",
        brand_status: str = "ACTIVE",
        offer_status: str = "ACTIVE",
        permission_active: bool = True,
        integration_healthy: bool = True,
        content_type_allowed: bool = True,
        publication_date_allowed: bool = True,
        duplicate: bool = False,
        community_interval_ok: bool = True,
    ) -> PolicyDecision:
        checks: list[tuple[str, bool, str, str]] = [
            (
                "WORKSPACE_ACTIVE",
                workspace_status == "ACTIVE",
                "WORKSPACE_INACTIVE",
                "Workspace is not active",
            ),
            (
                "COMPANY_ACTIVE",
                company_status == "ACTIVE",
                "COMPANY_INACTIVE",
                "Company is not active",
            ),
            ("BRAND_ACTIVE", brand_status == "ACTIVE", "BRAND_INACTIVE", "Brand is not active"),
            (
                "CAMPAIGN_ACTIVE",
                campaign_status not in {"ARCHIVED", "COMPLETED", "PAUSED", "DRAFT"},
                "CAMPAIGN_INACTIVE",
                "Campaign is not publishable",
            ),
            ("OFFER_ACTIVE", offer_status == "ACTIVE", "OFFER_INACTIVE", "Offer is not active"),
            (
                "COMMUNITY_APPROVED",
                community_status in {"APPROVED", "APPROVED_WITH_CONDITIONS"},
                "COMMUNITY_NOT_APPROVED",
                "Community is not approved for posting",
            ),
            (
                "COMMUNITY_PERMISSION_ACTIVE",
                permission_active,
                "COMMUNITY_PERMISSION_INACTIVE",
                "Community posting permission is not active",
            ),
            (
                "MESSAGE_APPROVED",
                message_approved,
                "MESSAGE_NOT_APPROVED",
                "Message draft requires approval",
            ),
            (
                "CAMPAIGN_DAILY_LIMIT",
                sent_today < daily_limit,
                "DAILY_LIMIT_REACHED",
                "Campaign daily limit has been reached",
            ),
            (
                "COMMUNITY_INTERVAL",
                community_interval_ok,
                "COMMUNITY_INTERVAL_BLOCKED",
                "Community posting interval has not elapsed",
            ),
            (
                "INTEGRATION_HEALTHY",
                integration_healthy,
                "INTEGRATION_UNHEALTHY",
                "Integration is not healthy",
            ),
            (
                "NO_EMERGENCY_STOP",
                not safety_lock and not self.safety_lock,
                "SAFETY_LOCK",
                "Publication is blocked by Emergency Stop",
            ),
            (
                "NO_SAFETY_LOCK",
                not self.safety_lock,
                "SAFETY_LOCK",
                "Publication is blocked by safety lock",
            ),
            (
                "CONTENT_TYPE_ALLOWED",
                content_type_allowed,
                "CONTENT_TYPE_NOT_ALLOWED",
                "Message content type is not allowed",
            ),
            (
                "PUBLICATION_DATE_ALLOWED",
                publication_date_allowed,
                "PUBLICATION_DATE_BLOCKED",
                "Publication date is not allowed",
            ),
            (
                "PUBLICATION_NOT_DUPLICATE",
                not duplicate,
                "PUBLICATION_DUPLICATE",
                "Publication idempotency key already exists",
            ),
        ]
        checked = [name for name, *_ in checks]
        denied = [name for name, allowed, *_ in checks if not allowed]
        if denied:
            _, _, code, reason = next(item for item in checks if not item[1])
            return self._deny(code, reason, checked, denied)
        return self._allow(checked)

    def evaluate(self, context: dict[str, Any]) -> PolicyDecision:
        return self.can_publish(**context)

    @staticmethod
    def _allow(checked: list[str]) -> PolicyDecision:
        return PolicyDecision(
            True, "ALLOW", "All publication policies passed", checked_policies=checked
        )

    @staticmethod
    def _deny(code: str, reason: str, checked: list[str], denied: list[str]) -> PolicyDecision:
        return PolicyDecision(
            False, code, reason, checked_policies=checked, denied_policies=denied, reasons=[reason]
        )
