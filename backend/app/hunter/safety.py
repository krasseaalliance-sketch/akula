from __future__ import annotations

import os


class HunterOutboundViolation(RuntimeError):
    pass


def assert_hunter_outbound_disabled() -> None:
    """Fail closed before a Hunter run if any outbound switch is enabled."""
    value = os.getenv("HUNTER_OUTBOUND_DISABLED", "true").strip().lower()
    if value not in {"1", "true", "yes", "on"}:
        raise HunterOutboundViolation("HUNTER_OUTBOUND_DISABLED must remain true")
    telegram_send = os.getenv("TELEGRAM_REAL_SEND_ENABLED", "false").strip().lower()
    if telegram_send in {"1", "true", "yes", "on"}:
        raise HunterOutboundViolation("TELEGRAM_REAL_SEND_ENABLED must remain false for Hunter")


def hunter_runtime_capabilities() -> dict[str, bool]:
    return {
        "read_public_sources": True,
        "write_hunter_reports": True,
        "telegram_send": False,
        "publication": False,
        "direct_message": False,
        "webhook": False,
        "phone_or_email_outreach": False,
    }
