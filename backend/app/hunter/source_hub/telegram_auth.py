from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ...telegram_engine.live_client import TelethonUserClient
from ...telegram_engine.vault import SessionVault
from .security import block_outbound


@dataclass(frozen=True)
class TelegramAuthConfig:
    api_id_ref: str = "HUNTER_TELEGRAM_API_ID"
    api_hash_ref: str = "HUNTER_TELEGRAM_API_HASH"
    session_ref: str = "HUNTER_TELEGRAM_SESSION"
    session_root_ref: str = "HUNTER_TELEGRAM_SESSION_ROOT"

    @classmethod
    def from_environment(cls) -> TelegramAuthConfig:
        return cls()

    def setup_status(self) -> str:
        required = (self.api_id_ref, self.api_hash_ref, self.session_ref)
        return "READY" if all(os.getenv(name) for name in required) else "AUTH_SETUP_REQUIRED"


class TelegramReadOnlyClient:
    """Read-only facade; write method names are deliberately unavailable."""

    _WRITE_METHODS = frozenset({
        "send_message", "send_file", "reply", "forward", "forward_messages", "edit", "edit_message",
        "delete", "delete_message", "join", "join_chat", "invite", "invite_user", "reaction",
        "vote", "comment", "dm", "auto_reply", "upload",
    })

    def __init__(self, client: Any, *, audit_sink=None, account_id: str | None = None, endpoint_id: str | None = None):
        self._client = client
        self._audit_sink = audit_sink
        self._account_id = account_id
        self._endpoint_id = endpoint_id

    def __getattr__(self, name: str) -> Any:
        if name in self._WRITE_METHODS:
            block_outbound(name, source_account_id=self._account_id, endpoint_id=self._endpoint_id, audit_sink=self._audit_sink)
        if name.startswith("_"):
            raise AttributeError(name)
        attribute = getattr(self._client, name)
        if name.startswith(("send", "forward", "edit", "delete", "join", "invite", "react", "vote", "comment", "upload")):
            block_outbound(name, source_account_id=self._account_id, endpoint_id=self._endpoint_id, audit_sink=self._audit_sink)
        return attribute

    async def health_check(self) -> bool:
        return bool(await self._client.health_check())

    async def get_dialogs(self):
        return await self._client.get_dialogs()

    async def get_messages(self, dialog_external_id: str, limit: int, since=None):
        return await self._client.get_messages(dialog_external_id, limit, since)

    async def read_public_community_messages(self, usernames: list[str], limit: int = 20):
        return await self._client.read_public_community_messages(usernames, limit)


class TelegramAuthAdapter:
    """Manual user authorization with local-only phone/code/password handling."""

    def __init__(self, config: TelegramAuthConfig | None = None, vault: SessionVault | None = None, client_factory=None):
        self.config = config or TelegramAuthConfig.from_environment()
        self.vault = vault
        self.client_factory = client_factory or self._default_client

    def _default_client(self) -> TelethonUserClient:
        api_id = os.getenv(self.config.api_id_ref)
        api_hash = os.getenv(self.config.api_hash_ref)
        return TelethonUserClient(api_id=api_id, api_hash=api_hash)

    def status(self) -> dict[str, str]:
        setup = self.config.setup_status()
        return {"status": "AUTH_REQUIRED" if setup == "READY" else "AUTH_SETUP_REQUIRED", "setup": setup, "api_id_ref": self.config.api_id_ref, "api_hash_ref": self.config.api_hash_ref, "session_ref": self.config.session_ref}

    async def request_code(self, phone: str) -> dict[str, str]:
        if self.config.setup_status() != "READY":
            return {"status": "AUTH_SETUP_REQUIRED"}
        if not phone or "\n" in phone:
            raise ValueError("local phone entry required")
        client = self.client_factory()
        await client.request_code(phone)
        return {"status": "CODE_REQUIRED"}

    async def complete_authorization(self, phone: str, code: str, *, password: str | None = None, account_id: str = "telegram") -> dict[str, str]:
        if self.config.setup_status() != "READY":
            return {"status": "AUTH_SETUP_REQUIRED"}
        if not code or "\n" in code or (password is not None and "\n" in password):
            raise ValueError("credentials must be entered locally")
        client = self.client_factory()
        try:
            session_body, _identity = await client.sign_in_password(phone, password) if password else await client.sign_in(phone, code)
        except Exception as exc:  # noqa: BLE001
            return {"status": "AUTH_REQUIRED", "error_type": type(exc).__name__}
        if self.vault is None:
            return {"status": "AUTHORIZED", "session_ref": self.config.session_ref}
        session_ref = self.vault.store_session(account_id, session_body)
        return {"status": "AUTHORIZED", "session_ref": session_ref}

    def read_only_client(self, client: Any, *, audit_sink=None, account_id: str | None = None, endpoint_id: str | None = None) -> TelegramReadOnlyClient:
        return TelegramReadOnlyClient(client, audit_sink=audit_sink, account_id=account_id, endpoint_id=endpoint_id)

    @staticmethod
    def revoke_session(vault: SessionVault, session_ref: str) -> None:
        vault.delete_session(session_ref)
