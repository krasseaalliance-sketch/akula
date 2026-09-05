"""Optional Telethon adapter.

The module is import-safe when live flags are disabled. No connection is made
until the engine explicitly selects this adapter behind the configured flags.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from urllib.request import getproxies

from .client_protocol import TelegramDialogData, TelegramMessageData

logger = logging.getLogger("telegram-live-client")


def _system_http_proxy() -> tuple[str | None, int | None]:
    """Resolve the configured Windows HTTP(S) proxy without exposing its value."""
    try:
        proxies = getproxies()
    except OSError:
        return None, None
    for key in ("https", "http"):
        raw = proxies.get(key)
        if not raw:
            continue
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        if parsed.hostname and parsed.port:
            return parsed.hostname, parsed.port
    return None, None


class TelethonUnavailableError(RuntimeError):
    pass


class TelethonUserClient:
    def __init__(self, *, api_id: str | None, api_hash: str | None, session_data: bytes | None = None,
                 proxy_host: str | None = None, proxy_port: int | None = None) -> None:
        if not api_id or not api_hash:
            raise RuntimeError("TELEGRAM_API_CREDENTIALS_REQUIRED")
        try:
            from telethon import TelegramClient  # type: ignore[import-untyped]
            from telethon.network.connection.tcpfull import (  # type: ignore[import-untyped]
                ConnectionTcpFull,
            )
            from telethon.sessions import StringSession  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        try:
            session = StringSession(session_data.decode("utf-8")) if session_data else StringSession()
        except UnicodeDecodeError as exc:
            raise RuntimeError("TELEGRAM_SESSION_FORMAT_INVALID") from exc
        if not (proxy_host and proxy_port):
            proxy_host, proxy_port = _system_http_proxy()
        connection = None
        if proxy_host and proxy_port:
            class ProxyConnectionTcpFull(ConnectionTcpFull):  # type: ignore[misc,valid-type]
                async def _connect(self, timeout=None, ssl=None):
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(proxy_host, proxy_port), timeout=timeout
                    )
                    target = f"{self._ip}:{self._port}"
                    writer.write(
                        f"CONNECT {target} HTTP/1.1\r\n"
                        f"Host: {target}\r\n"
                        "Connection: Keep-Alive\r\n\r\n"
                    .encode("ascii"))
                    await asyncio.wait_for(writer.drain(), timeout=timeout)
                    status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
                    while await asyncio.wait_for(reader.readline(), timeout=timeout) not in (b"\r\n", b"\n", b""):
                        pass
                    if b" 200 " not in status_line:
                        writer.close()
                        raise ConnectionError(f"HTTP proxy refused CONNECT to {target}")
                    self._reader = reader
                    self._writer = writer
                    self._codec = self.packet_codec(self)
                    self._init_conn()
                    await self._writer.drain()
            connection = ProxyConnectionTcpFull
        kwargs = {"connection": connection} if connection else {}
        self._client = TelegramClient(session, int(api_id), api_hash, **kwargs)
        self._phone: str | None = None
        self._phone_code_hash: str | None = None

    async def _connect(self) -> None:
        await self._client.connect()

    async def request_code(self, phone: str) -> None:
        self._phone = phone
        await self._connect()
        try:
            sent_code = await self._client.send_code_request(phone)
            self._phone_code_hash = getattr(sent_code, "phone_code_hash", None)
        finally:
            await self._client.disconnect()

    async def sign_in(self, phone: str, code: str) -> tuple[bytes, dict[str, str]]:
        await self._connect()
        try:
            if not self._phone_code_hash:
                sent_code = await self._client.send_code_request(phone)
                self._phone_code_hash = getattr(sent_code, "phone_code_hash", None)
            await self._client.sign_in(phone=phone, code=code, phone_code_hash=self._phone_code_hash)
            return self._session_bytes(), await self._identity()
        finally:
            await self._client.disconnect()

    async def sign_in_password(self, phone: str, password: str) -> tuple[bytes, dict[str, str]]:
        await self._connect()
        try:
            await self._client.sign_in(phone=phone, password=password)
            return self._session_bytes(), await self._identity()
        finally:
            await self._client.disconnect()

    def _session_bytes(self) -> bytes:
        return self._client.session.save().encode("utf-8")

    async def _identity(self) -> dict[str, str]:
        me = await self._client.get_me()
        return {
            "id": str(getattr(me, "id", "")),
            "username": getattr(me, "username", None) or "",
            "first_name": getattr(me, "first_name", None) or "",
            "last_name": getattr(me, "last_name", None) or "",
        }

    async def health_check(self) -> bool:
        await self._connect()
        try:
            return bool(await self._client.is_user_authorized())
        finally:
            await self._client.disconnect()

    @staticmethod
    def _dialog_type(entity: Any) -> str:
        name = entity.__class__.__name__.lower()
        if "channel" in name:
            return "CHANNEL" if getattr(entity, "broadcast", False) else "SUPERGROUP"
        if "chat" in name:
            return "GROUP"
        if "user" in name:
            return "BOT" if getattr(entity, "bot", False) else "USER"
        return "UNKNOWN"

    async def get_dialogs(self) -> list[TelegramDialogData]:
        await self._connect()
        try:
            dialogs = await self._client.get_dialogs(limit=500)
            result: list[TelegramDialogData] = []
            for dialog in dialogs:
                entity = dialog.entity
                result.append(TelegramDialogData(
                    external_id=str(getattr(entity, "id", dialog.id)),
                    dialog_type=self._dialog_type(entity),
                    title=dialog.name or str(getattr(entity, "title", "")),
                    username=getattr(entity, "username", None),
                    description=None,
                    is_public=bool(getattr(entity, "username", None)),
                    is_joined=bool(getattr(dialog, "is_group", False) or getattr(dialog, "is_channel", False)),
                    can_send_messages=bool(not getattr(entity, "broadcast", False)),
                    can_view_history=True,
                    slow_mode_seconds=None,
                    member_count=None,
                    rules_text=None,
                    pinned_message_text=None,
                    geography=None,
                    language=None,
                    category=None,
                ))
            return result
        finally:
            await self._client.disconnect()

    async def search_communities(self, query: str) -> list[TelegramDialogData]:
        # Public search is intentionally bounded; it never joins a result.
        try:
            from telethon import functions  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        await self._connect()
        try:
            found = await self._client(functions.contacts.SearchRequest(q=query, limit=100))
            entities = [*getattr(found, "chats", []), *getattr(found, "users", [])]
            return [TelegramDialogData(
                external_id=str(getattr(entity, "id", "")),
                dialog_type=self._dialog_type(entity),
                title=getattr(entity, "title", None) or " ".join(filter(None, [getattr(entity, "first_name", None), getattr(entity, "last_name", None)])),
                username=getattr(entity, "username", None),
                description=None,
                is_public=bool(getattr(entity, "username", None)),
                is_joined=False,
                can_send_messages=False,
                can_view_history=False,
                slow_mode_seconds=None,
                member_count=getattr(entity, "participants_count", None),
                rules_text=None,
                pinned_message_text=None,
                geography=None,
                language=None,
                category=None,
            ) for entity in entities]
        finally:
            await self._client.disconnect()

    async def search_global_messages(self, query: str, limit: int = 100) -> list[TelegramMessageData]:
        """Search public Telegram messages globally; do not restrict to account dialogs."""
        try:
            from telethon import functions, types  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        await self._connect()
        try:
            rows: list[TelegramMessageData] = []
            offset_rate = 0
            offset_id = 0
            offset_peer: Any = types.InputPeerEmpty()
            page_size = min(limit, 100)
            # Telegram commonly returns the operator's own dialogs first. Read
            # a bounded number of pages so the caller can discard local chats
            # and still receive genuinely external results.
            for _ in range(5):
                try:
                    result = await asyncio.wait_for(self._client(functions.messages.SearchGlobalRequest(
                        q=query,
                        filter=types.InputMessagesFilterEmpty(),
                        min_date=None,
                        max_date=None,
                        offset_rate=offset_rate,
                        offset_id=offset_id,
                        offset_peer=offset_peer,
                        limit=page_size,
                    )), timeout=8.0)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("global message search failed for %s: %s", query, type(exc).__name__)
                    break
                chats = {int(getattr(item, "id", 0)): item for item in getattr(result, "chats", [])}
                messages = getattr(result, "messages", [])
                for message in messages:
                    peer = getattr(message, "peer_id", None)
                    peer_id = getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None) or getattr(peer, "user_id", None)
                    entity = chats.get(int(peer_id)) if peer_id is not None else None
                    if entity is None or self._dialog_type(entity) not in {"GROUP", "SUPERGROUP", "CHANNEL"}:
                        continue
                    sent_at = message.date.replace(tzinfo=None) if message.date else datetime.utcnow()
                    sender = await message.get_sender() if message.sender_id else None
                    rows.append(TelegramMessageData(
                        external_id=str(message.id),
                        dialog_external_id=str(getattr(entity, "id", peer_id)),
                        sender_external_id=str(message.sender_id) if message.sender_id else None,
                        sender_username=getattr(sender, "username", None),
                        sender_display_name=" ".join(filter(None, [getattr(sender, "first_name", None), getattr(sender, "last_name", None)])) or None,
                        text=message.message,
                        sent_at=sent_at,
                        direction="OUTBOUND" if bool(message.out) else "INBOUND",
                        dialog_title=getattr(entity, "title", None),
                        dialog_username=getattr(entity, "username", None),
                        dialog_type=self._dialog_type(entity),
                        dialog_is_public=bool(getattr(entity, "username", None)),
                    ))
                if len(rows) >= limit or not messages or getattr(result, "next_rate", None) is None:
                    break
                last_message = messages[-1]
                peer = getattr(last_message, "peer_id", None)
                raw_peer_id = getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None) or getattr(peer, "user_id", None)
                entity = chats.get(int(raw_peer_id)) if raw_peer_id is not None else None
                if entity is None:
                    break
                offset_rate = int(result.next_rate)
                offset_id = int(last_message.id)
                offset_peer = await self._client.get_input_entity(entity)
            return rows
        finally:
            await self._client.disconnect()

    async def read_public_community_messages(self, usernames: list[str], limit: int = 20) -> list[TelegramMessageData]:
        """Read recent messages from public peers without joining them."""
        await self._connect()
        try:
            rows: list[TelegramMessageData] = []
            for username in dict.fromkeys(u.strip().lstrip("@") for u in usernames if u and u.strip()):
                try:
                    entity = await asyncio.wait_for(self._client.get_entity(username), timeout=8.0)
                    if self._dialog_type(entity) not in {"GROUP", "SUPERGROUP", "CHANNEL"}:
                        continue
                    messages = await asyncio.wait_for(
                        self._client.get_messages(entity, limit=min(limit, 50)), timeout=8.0
                    )
                    for message in reversed(messages):
                        sender = await message.get_sender() if message.sender_id else None
                        rows.append(TelegramMessageData(
                            external_id=str(message.id),
                            dialog_external_id=str(getattr(entity, "id", "")),
                            sender_external_id=str(message.sender_id) if message.sender_id else None,
                            sender_username=getattr(sender, "username", None),
                            sender_display_name=" ".join(filter(None, [getattr(sender, "first_name", None), getattr(sender, "last_name", None)])) or None,
                            text=message.message,
                            sent_at=message.date.replace(tzinfo=None) if message.date else datetime.utcnow(),
                            direction="OUTBOUND" if bool(message.out) else "INBOUND",
                            reply_to_external_id=str(message.reply_to_msg_id) if message.reply_to_msg_id else None,
                            edited_at=message.edit_date.replace(tzinfo=None) if message.edit_date else None,
                            initiated_contact=False,
                            dialog_title=getattr(entity, "title", None),
                            dialog_username=getattr(entity, "username", None) or username,
                            dialog_type=self._dialog_type(entity),
                            dialog_is_public=bool(getattr(entity, "username", None)),
                        ))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("public community read skipped %s: %s", username, type(exc).__name__)
            return rows
        finally:
            await self._client.disconnect()

    async def search_global_communities(self, query: str, limit: int = 100) -> list[TelegramDialogData]:
        """Return public communities surfaced by Telegram's global search."""
        try:
            from telethon import functions, types  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        await self._connect()
        try:
            communities_by_id: dict[str, TelegramDialogData] = {}
            offset_rate = 0
            offset_id = 0
            offset_peer: Any = types.InputPeerEmpty()
            for _ in range(1):
                try:
                    result = await asyncio.wait_for(self._client(functions.messages.SearchGlobalRequest(
                        q=query,
                        filter=types.InputMessagesFilterEmpty(),
                        min_date=None,
                        max_date=None,
                        offset_rate=offset_rate,
                        offset_id=offset_id,
                        offset_peer=offset_peer,
                        limit=min(limit, 100),
                    )), timeout=8.0)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("global message search failed for %s: %s", query, type(exc).__name__)
                    break
                chats = {int(getattr(item, "id", 0)): item for item in getattr(result, "chats", [])}
                matched_peer_ids = {
                    int(peer_id)
                    for message in getattr(result, "messages", [])
                    if (peer_id := (
                        getattr(getattr(message, "peer_id", None), "channel_id", None)
                        or getattr(getattr(message, "peer_id", None), "chat_id", None)
                        or getattr(getattr(message, "peer_id", None), "user_id", None)
                    )) is not None
                }
                for entity in chats.values():
                    if int(getattr(entity, "id", 0)) not in matched_peer_ids:
                        continue
                    dialog_type = self._dialog_type(entity)
                    if dialog_type not in {"GROUP", "SUPERGROUP"}:
                        continue
                    username = getattr(entity, "username", None)
                    external_id = str(getattr(entity, "id", ""))
                    communities_by_id[external_id] = TelegramDialogData(
                        external_id=external_id,
                        dialog_type=dialog_type,
                        title=getattr(entity, "title", None) or username or "Telegram community",
                        username=username,
                        description=None,
                        is_public=bool(username),
                        is_joined=False,
                        can_send_messages=not bool(getattr(entity, "broadcast", False)),
                        can_view_history=True,
                        slow_mode_seconds=None,
                        member_count=getattr(entity, "participants_count", None),
                        rules_text=None,
                        pinned_message_text=None,
                        geography=None,
                        language=None,
                        category=None,
                    )
                messages = getattr(result, "messages", [])
                next_rate = getattr(result, "next_rate", None)
                if not messages or next_rate is None:
                    break
                last_message = messages[-1]
                peer_id = getattr(last_message, "peer_id", None)
                raw_peer_id = (
                    getattr(peer_id, "channel_id", None)
                    or getattr(peer_id, "chat_id", None)
                    or getattr(peer_id, "user_id", None)
                )
                entity = chats.get(int(raw_peer_id)) if raw_peer_id is not None else None
                if entity is None:
                    break
                offset_rate = int(next_rate)
                offset_id = int(last_message.id)
                offset_peer = await self._client.get_input_entity(entity)
            return list(communities_by_id.values())
        finally:
            await self._client.disconnect()

    async def search_global_communities_batch(self, queries: list[str], limit: int = 100) -> dict[str, list[TelegramDialogData]]:
        """Run multiple global community searches over one Telegram connection."""
        try:
            from telethon import functions, types  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        await self._connect()
        try:
            result_by_query: dict[str, list[TelegramDialogData]] = {}
            for query in queries:
                communities_by_id: dict[str, TelegramDialogData] = {}
                offset_rate = 0
                offset_id = 0
                offset_peer: Any = types.InputPeerEmpty()
                # One page per query keeps the global discovery tick bounded;
                # subsequent scheduled ticks rotate through the query set.
                for _ in range(1):
                    try:
                        result = await asyncio.wait_for(self._client(functions.messages.SearchGlobalRequest(
                            q=query,
                            filter=types.InputMessagesFilterEmpty(),
                            min_date=None,
                            max_date=None,
                            offset_rate=offset_rate,
                            offset_id=offset_id,
                            offset_peer=offset_peer,
                            limit=min(limit, 100),
                        )), timeout=8.0)
                    except TimeoutError:
                        logger.warning("global community search timed out: %s", query)
                        result_by_query[query] = []
                        break
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("global community search failed for %s: %s", query, type(exc).__name__)
                        result_by_query[query] = []
                        break
                    chats = {int(getattr(item, "id", 0)): item for item in getattr(result, "chats", [])}
                    matched_peer_ids = {
                        int(peer_id)
                        for message in getattr(result, "messages", [])
                        if (peer_id := (
                            getattr(getattr(message, "peer_id", None), "channel_id", None)
                            or getattr(getattr(message, "peer_id", None), "chat_id", None)
                            or getattr(getattr(message, "peer_id", None), "user_id", None)
                        )) is not None
                    }
                    for entity in chats.values():
                        if int(getattr(entity, "id", 0)) not in matched_peer_ids:
                            continue
                        dialog_type = self._dialog_type(entity)
                        if dialog_type not in {"GROUP", "SUPERGROUP"}:
                            continue
                        username = getattr(entity, "username", None)
                        external_id = str(getattr(entity, "id", ""))
                        communities_by_id[external_id] = TelegramDialogData(
                            external_id=external_id,
                            dialog_type=dialog_type,
                            title=getattr(entity, "title", None) or username or "Telegram community",
                            username=username,
                            description=None,
                            is_public=bool(username),
                            is_joined=False,
                            can_send_messages=not bool(getattr(entity, "broadcast", False)),
                            can_view_history=True,
                            slow_mode_seconds=None,
                            member_count=getattr(entity, "participants_count", None),
                            rules_text=None,
                            pinned_message_text=None,
                            geography=None,
                            language=None,
                            category=None,
                        )
                    messages = getattr(result, "messages", [])
                    next_rate = getattr(result, "next_rate", None)
                    if not messages or next_rate is None:
                        break
                    last_message = messages[-1]
                    peer_id = getattr(last_message, "peer_id", None)
                    raw_peer_id = (
                        getattr(peer_id, "channel_id", None)
                        or getattr(peer_id, "chat_id", None)
                        or getattr(peer_id, "user_id", None)
                    )
                    entity = chats.get(int(raw_peer_id)) if raw_peer_id is not None else None
                    if entity is None:
                        break
                    offset_rate = int(next_rate)
                    offset_id = int(last_message.id)
                    offset_peer = await self._client.get_input_entity(entity)
                result_by_query[query] = list(communities_by_id.values())
            return result_by_query
        finally:
            await self._client.disconnect()

    async def update_dialog_folder(self, title: str, usernames: list[str]) -> int:
        """Create/update a Telegram dialog folder with confirmed joined peers."""
        try:
            from telethon import functions, types  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        await self._connect()
        try:
            # Resolve peers from the already synchronized dialog list in one
            # read. Re-resolving every username separately can trigger a
            # Telegram FloodWait and leave the folder with an empty peer list.
            dialogs = await self._client.get_dialogs(limit=None)
            entities_by_username = {
                (getattr(dialog.entity, "username", None) or "").casefold(): dialog.entity
                for dialog in dialogs
                if getattr(dialog, "entity", None) is not None
                and getattr(dialog.entity, "username", None)
            }
            peers = []
            for username in dict.fromkeys(u.strip().lstrip("@") for u in usernames if u and u.strip()):
                try:
                    entity = entities_by_username.get(username.casefold())
                    if entity is None:
                        continue
                    if self._dialog_type(entity) not in {"GROUP", "SUPERGROUP", "CHANNEL"}:
                        continue
                    if isinstance(entity, types.Channel):
                        access_hash = getattr(entity, "access_hash", None)
                        if access_hash is None:
                            continue
                        peers.append(types.InputPeerChannel(channel_id=int(entity.id), access_hash=int(access_hash)))
                    elif isinstance(entity, types.Chat):
                        peers.append(types.InputPeerChat(chat_id=int(entity.id)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("folder peer skipped %s: %s", username, type(exc).__name__)

            filters = await self._client(functions.messages.GetDialogFiltersRequest())
            existing = None
            used_ids: set[int] = set()
            duplicate_ids: list[int] = []
            for item in getattr(filters, "filters", []):
                item_id = getattr(item, "id", None)
                if item_id is not None:
                    used_ids.add(int(item_id))
                item_title = getattr(getattr(item, "title", None), "text", None) or ""
                if item_title == title:
                    existing = item
                elif item_title == "\u0418\u0422-\u043b\u0438\u0434\u044b" and title == "IT-\u043b\u0438\u0434\u044b" and item_id is not None:
                    duplicate_ids.append(int(item_id))
            folder_id = int(getattr(existing, "id", 0)) if existing is not None else next(
                item_id for item_id in range(2, 100) if item_id not in used_ids
            )
            folder = types.DialogFilter(
                id=folder_id,
                title=types.TextWithEntities(text=title, entities=[]),
                pinned_peers=[],
                include_peers=peers,
                exclude_peers=[],
                contacts=False,
                non_contacts=False,
                groups=False,
                broadcasts=False,
                bots=False,
                exclude_muted=False,
                exclude_read=False,
                exclude_archived=False,
            )
            await self._client(functions.messages.UpdateDialogFilterRequest(id=folder_id, filter=folder))
            for duplicate_id in duplicate_ids:
                await self._client(functions.messages.UpdateDialogFilterRequest(id=duplicate_id, filter=None))
            return len(peers)
        finally:
            await self._client.disconnect()

    async def enrich_community_metadata(self, usernames: list[str]) -> dict[str, tuple[int, float]]:
        """Read participant counts and recent-message activity for public chats."""
        try:
            from telethon import functions  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        await self._connect()
        try:
            result: dict[str, tuple[int, float]] = {}
            cutoff = datetime.now(UTC) - timedelta(days=7)
            for username in dict.fromkeys(u.strip().lstrip("@") for u in usernames if u and u.strip()):
                try:
                    entity = await asyncio.wait_for(self._client.get_entity(username), timeout=6.0)
                    if self._dialog_type(entity) not in {"GROUP", "SUPERGROUP"}:
                        continue
                    full = await asyncio.wait_for(
                        self._client(functions.channels.GetFullChannelRequest(channel=entity)), timeout=6.0
                    )
                    member_count = int(getattr(full.full_chat, "participants_count", 0) or 0)
                    messages = await asyncio.wait_for(self._client.get_messages(entity, limit=20), timeout=6.0)
                    recent = sum(1 for message in messages if message.date and message.date >= cutoff)
                    result[username.casefold()] = (member_count, min(1.0, recent / 20.0))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("community metadata skipped %s: %s", username, type(exc).__name__)
            return result
        finally:
            await self._client.disconnect()

    async def join_public_community(self, username: str) -> TelegramDialogData:
        """Join one explicitly selected public community and return its metadata."""
        try:
            from telethon import functions  # type: ignore[import-untyped]
        except ImportError as exc:
            raise TelethonUnavailableError("TELETHON_DEPENDENCY_UNAVAILABLE") from exc
        normalized = username.strip().lstrip("@")
        if not normalized:
            raise ValueError("PUBLIC_USERNAME_REQUIRED")
        await self._connect()
        try:
            entity = await self._client.get_entity(normalized)
            if self._dialog_type(entity) not in {"GROUP", "SUPERGROUP"}:
                raise ValueError("CHANNEL_JOIN_DISABLED")
            await self._client(functions.channels.JoinChannelRequest(channel=entity))
            entity = await self._client.get_entity(normalized)
            dialog_type = self._dialog_type(entity)
            if dialog_type not in {"GROUP", "SUPERGROUP"}:
                raise ValueError("TARGET_IS_NOT_A_COMMUNITY")
            permissions = await self._client.get_permissions(entity, "me")
            default_banned_rights = getattr(entity, "default_banned_rights", None)
            member_banned_rights = getattr(permissions, "banned_rights", None)
            is_admin = bool(getattr(permissions, "is_admin", False))
            can_send_messages = is_admin or (
                not bool(getattr(entity, "broadcast", False))
                and not bool(getattr(default_banned_rights, "send_messages", False))
                and not bool(getattr(member_banned_rights, "send_messages", False))
            )
            return TelegramDialogData(
                external_id=str(getattr(entity, "id", "")),
                dialog_type=dialog_type,
                title=getattr(entity, "title", None) or normalized,
                username=getattr(entity, "username", None) or normalized,
                description=None,
                is_public=True,
                is_joined=True,
                can_send_messages=can_send_messages,
                can_view_history=True,
                slow_mode_seconds=None,
                member_count=getattr(entity, "participants_count", None),
                rules_text=None,
                pinned_message_text=None,
                geography=None,
                language=None,
                category=None,
            )
        finally:
            await self._client.disconnect()

    async def get_messages(self, dialog_external_id: str, limit: int, since: datetime | None = None) -> list[TelegramMessageData]:
        await self._connect()
        try:
            entity = await self._client.get_entity(int(dialog_external_id) if dialog_external_id.lstrip("-").isdigit() else dialog_external_id)
            messages = await self._client.get_messages(entity, limit=min(limit, 1000))
            result: list[TelegramMessageData] = []
            for message in reversed(messages):
                sent_at = message.date.replace(tzinfo=None) if message.date else datetime.utcnow()
                if since and sent_at < since:
                    continue
                sender = await message.get_sender() if message.sender_id else None
                result.append(TelegramMessageData(
                    external_id=str(message.id),
                    dialog_external_id=dialog_external_id,
                    sender_external_id=str(message.sender_id) if message.sender_id else None,
                    sender_username=getattr(sender, "username", None),
                    sender_display_name=" ".join(filter(None, [getattr(sender, "first_name", None), getattr(sender, "last_name", None)])) or None,
                    text=message.message,
                    sent_at=sent_at,
                    direction="OUTBOUND" if bool(message.out) else "INBOUND",
                    reply_to_external_id=str(message.reply_to_msg_id) if message.reply_to_msg_id else None,
                    edited_at=message.edit_date.replace(tzinfo=None) if message.edit_date else None,
                    initiated_contact=False,
                ))
            return result
        finally:
            await self._client.disconnect()

    async def create_forum_topic(self, dialog_external_id: str, title: str) -> str:
        from telethon import functions, types  # type: ignore[import-untyped]
        await self._connect()
        try:
            entity = await self._client.get_entity(int(dialog_external_id) if dialog_external_id.lstrip("-").isdigit() else dialog_external_id)
            result = await self._client(functions.channels.CreateForumTopicRequest(channel=entity, title=title))
            for update in getattr(result, "updates", []):
                message = getattr(update, "message", None)
                if message is not None and getattr(message, "id", None) is not None:
                    return str(message.id)
            raise RuntimeError("TELEGRAM_TOPIC_ID_NOT_RETURNED")
        finally:
            await self._client.disconnect()

    async def send_message(self, dialog_external_id: str, content: str, idempotency_key: str, thread_id: str | None = None) -> str:
        await self._connect()
        try:
            entity = await self._client.get_entity(int(dialog_external_id) if dialog_external_id.lstrip("-").isdigit() else dialog_external_id)
            permissions = await self._client.get_permissions(entity, "me")
            default_banned_rights = getattr(entity, "default_banned_rights", None)
            member_banned_rights = getattr(permissions, "banned_rights", None)
            is_admin = bool(getattr(permissions, "is_admin", False))
            send_blocked = (
                bool(getattr(entity, "broadcast", False))
                or bool(getattr(default_banned_rights, "send_messages", False))
                or bool(getattr(member_banned_rights, "send_messages", False))
            )
            if send_blocked and not is_admin:
                raise PermissionError("CHAT_POSTING_PERMISSION_DENIED")
            message = await self._client.send_message(entity, content, reply_to=int(thread_id) if thread_id and thread_id.isdigit() else None)
            return str(message.id)
        finally:
            await self._client.disconnect()

    async def verify_message(self, dialog_external_id: str, external_message_id: str) -> bool:
        """Verify that a sent message exists on Telegram after publishing."""
        await self._connect()
        try:
            entity = await self._client.get_entity(
                int(dialog_external_id) if dialog_external_id.lstrip("-").isdigit() else dialog_external_id
            )
            message = await self._client.get_messages(entity, ids=int(external_message_id))
            return message is not None and str(getattr(message, "id", "")) == str(external_message_id)
        finally:
            await self._client.disconnect()

    async def send_self_message(self, content: str) -> str:
        await self._connect()
        try:
            message = await self._client.send_message("me", content)
            return str(message.id)
        finally:
            await self._client.disconnect()
