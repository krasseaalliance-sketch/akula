from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ...telegram_engine.vault import EncryptedLocalSessionVault

REQUIRED_REFS = (
    "HUNTER_TELEGRAM_API_ID",
    "HUNTER_TELEGRAM_API_HASH",
    "HUNTER_TELEGRAM_SESSION",
)
SAFE_FLAGS = (
    "HUNTER_TELEGRAM_READ_ONLY",
    "HUNTER_TELEGRAM_SEND_DISABLED",
    "HUNTER_SOURCE_HUB_SHADOW_MODE",
)
USER_ENV_REFS = REQUIRED_REFS + SAFE_FLAGS + ("TELEGRAM_SESSION_ENCRYPTION_KEY",)


@dataclass(frozen=True)
class SessionInspection:
    status: str
    reason: str
    refs_present: dict[str, bool]
    persistent_session_present: bool
    session_root_present: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_user_scoped_environment() -> None:
    """Load local Windows user refs into this process without printing values."""
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in USER_ENV_REFS:
                if os.getenv(name):
                    continue
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except OSError:
                    continue
                if isinstance(value, str) and value:
                    os.environ[name] = value
    except OSError:
        return


def effective_flags() -> dict[str, bool]:
    return {name: os.getenv(name, "true").strip().lower() == "true" for name in SAFE_FLAGS}


def _session_candidate() -> tuple[Path | None, bool]:
    session_ref = os.getenv("HUNTER_TELEGRAM_SESSION", "").strip()
    root = Path(os.getenv("HUNTER_TELEGRAM_SESSION_ROOT", ".telegram_sessions"))
    if not session_ref:
        return None, root.is_dir()
    direct = Path(session_ref)
    if direct.is_file():
        return direct, root.is_dir()
    if session_ref.startswith("local:"):
        digest = hashlib.sha256(session_ref.encode("utf-8")).hexdigest()
        encrypted = root / f"{digest}.session"
        if encrypted.is_file():
            return encrypted, root.is_dir()
    return None, root.is_dir()


def inspect_session() -> SessionInspection:
    refs = {name: bool(os.getenv(name, "").strip()) for name in REQUIRED_REFS}
    candidate, root_present = _session_candidate()
    if not all(refs.values()):
        return SessionInspection("MISSING", "SECRET_REFS_MISSING", refs, False, root_present)
    if candidate is None:
        return SessionInspection("MISSING", "PERSISTENT_SESSION_NOT_FOUND", refs, False, root_present)
    return SessionInspection("PRESENT", "PERSISTENT_SESSION_REFERENCE_RESOLVED", refs, True, root_present)


def load_persistent_session() -> bytes:
    inspection = inspect_session()
    if inspection.status != "PRESENT":
        raise RuntimeError(inspection.reason)
    session_ref = os.getenv("HUNTER_TELEGRAM_SESSION", "").strip()
    candidate, _ = _session_candidate()
    if session_ref.startswith("local:"):
        key = os.getenv("TELEGRAM_SESSION_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("SESSION_ENCRYPTION_KEY_REQUIRED")
        vault = EncryptedLocalSessionVault(
            key=key,
            root=os.getenv("HUNTER_TELEGRAM_SESSION_ROOT", ".telegram_sessions"),
        )
        return vault.load_session(session_ref)
    if candidate is None:
        raise RuntimeError("PERSISTENT_SESSION_NOT_FOUND")
    return candidate.read_bytes()
