from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TelegramDialogData:
    external_id: str
    dialog_type: str
    title: str
    username: str | None
    description: str | None
    is_public: bool
    is_joined: bool
    can_send_messages: bool
    can_view_history: bool
    slow_mode_seconds: int | None
    member_count: int | None
    rules_text: str | None
    pinned_message_text: str | None
    geography: str | None
    language: str | None
    category: str | None


@dataclass(frozen=True)
class TelegramMessageData:
    external_id: str
    dialog_external_id: str
    sender_external_id: str | None
    sender_username: str | None
    sender_display_name: str | None
    text: str | None
    sent_at: datetime
    direction: str = "INBOUND"
    reply_to_external_id: str | None = None
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    initiated_contact: bool = False
    dialog_title: str | None = None
    dialog_username: str | None = None
    dialog_type: str = "UNKNOWN"
    dialog_is_public: bool = False


class TelegramUserAdapter(Protocol):
    async def request_code(self, phone: str) -> None: ...

    async def sign_in(self, phone: str, code: str) -> tuple[bytes, dict[str, str]]: ...

    async def sign_in_password(self, phone: str, password: str) -> tuple[bytes, dict[str, str]]: ...

    async def health_check(self) -> bool: ...

    async def get_dialogs(self) -> list[TelegramDialogData]: ...

    async def search_communities(self, query: str) -> list[TelegramDialogData]: ...

    async def search_global_messages(self, query: str, limit: int = 100) -> list[TelegramMessageData]: ...

    async def read_public_community_messages(self, usernames: list[str], limit: int = 20) -> list[TelegramMessageData]: ...

    async def search_global_communities_batch(self, queries: list[str], limit: int = 100) -> dict[str, list[TelegramDialogData]]: ...

    async def join_public_community(self, username: str) -> TelegramDialogData: ...

    async def update_dialog_folder(self, title: str, usernames: list[str]) -> int: ...

    async def enrich_community_metadata(self, usernames: list[str]) -> dict[str, tuple[int, float]]: ...

    async def get_messages(self, dialog_external_id: str, limit: int, since: datetime | None = None) -> list[TelegramMessageData]: ...

    async def create_forum_topic(self, dialog_external_id: str, title: str) -> str: ...

    async def send_message(self, dialog_external_id: str, content: str, idempotency_key: str, thread_id: str | None = None) -> str: ...


class TelegramBotAdapter(Protocol):
    async def send_bot_message(self, destination: str, content: str) -> str: ...
