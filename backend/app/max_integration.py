from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


MAX_API_BASE_URL = "https://platform-api2.max.ru"
MAX_MESSAGE_UPDATE_TYPES = ["message_created", "message_edited", "bot_started"]


class MaxApiError(RuntimeError):
    """Sanitized MAX API failure without credentials or response content."""


@dataclass(frozen=True)
class MaxMessageUpdate:
    chat_id: str
    message_id: str
    text: str
    sender_id: str | None
    sent_at: datetime | None
    edited_at: datetime | None


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_max_message_update(payload: dict[str, Any]) -> MaxMessageUpdate | None:
    """Extract only supported message events from a MAX webhook update."""
    if payload.get("update_type") not in {"message_created", "message_edited"}:
        return None
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    body = message.get("body") if isinstance(message.get("body"), dict) else {}
    recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
    sender = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    if not sender and isinstance(message.get("sender"), dict):
        sender = message["sender"]
    chat_id = payload.get("chat_id") or recipient.get("chat_id")
    message_id = body.get("mid") or body.get("message_id") or message.get("message_id")
    text = body.get("text")
    if chat_id is None or message_id is None or not isinstance(text, str) or not text.strip():
        return None
    timestamp = message.get("timestamp") or payload.get("timestamp")
    return MaxMessageUpdate(
        chat_id=str(chat_id),
        message_id=str(message_id),
        text=text,
        sender_id=str(sender["user_id"]) if sender.get("user_id") is not None else None,
        sent_at=_timestamp(timestamp),
        edited_at=_timestamp(timestamp) if payload.get("update_type") == "message_edited" else None,
    )


class MaxBotClient:
    """Small synchronous client for the MAX bot API used by FastAPI services."""

    def __init__(
        self,
        access_token: str,
        *,
        base_url: str = MAX_API_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not access_token or not access_token.strip():
            raise ValueError("MAX_ACCESS_TOKEN_NOT_CONFIGURED")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": access_token, "Content-Type": "application/json"},
            transport=transport,
            timeout=timeout,
        )
        self._sent_by_key: dict[str, str] = {}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", "UNKNOWN")
            raise MaxApiError(f"MAX_API_REQUEST_FAILED_{status}") from exc
        if not isinstance(data, dict):
            raise MaxApiError("MAX_API_INVALID_RESPONSE")
        return data

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/me")

    def send_message(self, chat_id: str, text: str, *, idempotency_key: str) -> str:
        if idempotency_key in self._sent_by_key:
            return self._sent_by_key[idempotency_key]
        data = self._request("POST", "/messages", params={"chat_id": str(chat_id)}, json={"text": text})
        message = data.get("message") if isinstance(data.get("message"), dict) else data
        message_id = message.get("message_id") or message.get("id")
        if message_id is None:
            raise MaxApiError("MAX_API_MESSAGE_ID_MISSING")
        result = str(message_id)
        self._sent_by_key[idempotency_key] = result
        return result

    def subscribe_webhook(self, url: str, secret: str) -> dict[str, Any]:
        if not url.startswith("https://"):
            raise ValueError("MAX_WEBHOOK_HTTPS_REQUIRED")
        if not secret or len(secret) < 5:
            raise ValueError("MAX_WEBHOOK_SECRET_REQUIRED")
        return self._request(
            "POST",
            "/subscriptions",
            json={"url": url, "update_types": MAX_MESSAGE_UPDATE_TYPES, "secret": secret},
        )

    def close(self) -> None:
        self._client.close()
