from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .client_protocol import TelegramDialogData, TelegramMessageData


class MockFloodWaitError(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("FLOOD_WAIT")
        self.retry_after = retry_after


def _now(hours_ago: int = 0) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours_ago)


def mock_dialog_fixtures() -> list[TelegramDialogData]:
    return [
        TelegramDialogData("balitravel_ru", "SUPERGROUP", "Бали — попутчики и путешествия", "balitravel_ru", "Русскоязычные путешественники на Бали", True, True, True, True, None, 4200, "Реклама запрещена. Поиск попутчиков разрешён. Ссылки только по теме.", "Закреп: уважайте участников", "Бали", "ru", "travel"),
        TelegramDialogData("bali_expats", "SUPERGROUP", "Bali Expats Community", "bali_expats", "English-speaking expat community", True, True, True, True, None, 6800, "Commercial offers require admin approval. Travel posts welcome.", "Pinned: weekly events", "Bali", "en", "travel"),
        TelegramDialogData("kras_city", "SUPERGROUP", "Красноярск — городской чат", "kras_city", "Городские новости и вопросы", True, True, True, True, 30, 12000, "Реклама запрещена. Slow mode 30 seconds.", "Правила чата", "Красноярск", "ru", "city"),
        TelegramDialogData("kras_events", "SUPERGROUP", "События Красноярска", "kras_events", "Афиша и мероприятия", True, True, True, True, None, 5200, "Разрешены анонсы событий и полезные ссылки.", "Афиша недели", "Красноярск", "ru", "events"),
        TelegramDialogData("kras_yachts", "SUPERGROUP", "Яхты и отдых — Красноярск", "kras_yachts", "Отдых на Красноярском море", True, True, True, True, None, 1900, "Поиск попутчиков разрешён. Коммерческие предложения — в рекламный день.", "Рекламный день: пятница", "Красноярск", "ru", "yachts"),
        TelegramDialogData("quiz_online", "CHANNEL", "Онлайн-квизы", "quiz_online", "Вопросы, викторины и мини-игры", True, True, False, True, None, 9100, "Разрешены тематические вопросы и приглашения в игру. Реклама запрещена.", "Вопрос дня", None, "ru", "quiz"),
        TelegramDialogData("digital_founders", "SUPERGROUP", "Digital предприниматели", "digital_founders", "Business and automation", True, True, True, True, None, 7300, "Разрешены полезные кейсы. Рекламные офферы требуют согласования.", "Правила публикаций", None, "ru", "digital"),
        TelegramDialogData("dev_chat", "GROUP", "Разработчики и продукты", "dev_chat", "Engineering discussions", True, True, True, True, None, 3400, "No unsolicited advertising. Partnership requests with context allowed.", "Технический чат", None, "ru", "digital"),
        TelegramDialogData("no_ads", "SUPERGROUP", "Чат без рекламы", "no_ads", "Community chat", True, True, False, True, None, 2400, "Любая реклама запрещена.", "Без рекламы", None, "ru", "general"),
        TelegramDialogData("private_trip", "SUPERGROUP", "Закрытый клуб попутчиков", None, "Private dialog already available to account", False, True, True, True, None, 300, "Только участники клуба. Поиск попутчиков разрешён.", "Закрытый клуб", "Бали", "ru", "travel"),
        TelegramDialogData("slow_mode", "SUPERGROUP", "Чат с slow mode", "slow_mode", "Slow mode community", True, True, True, True, 60, 1000, "Реклама только по пятницам. Slow mode 60 seconds.", "Правила", None, "ru", "general"),
        TelegramDialogData("no_history", "SUPERGROUP", "История недоступна", "no_history", "History unavailable", True, True, True, False, None, 700, "История для новых участников недоступна.", None, None, "ru", "general"),
        TelegramDialogData("read_only", "CHANNEL", "Только чтение", "read_only", "Account cannot post", True, True, False, True, None, 15000, "Публикации только администраторами.", None, None, "ru", "news"),
        TelegramDialogData("changed_rules", "SUPERGROUP", "Чат с изменившимися правилами", "changed_rules", "Rules changed since last sync", True, True, True, True, None, 2600, "НОВЫЕ ПРАВИЛА: реклама только после ручного согласования.", "Обновлённые правила", "Красноярск", "ru", "events"),
        TelegramDialogData("dm_initiated", "USER", "Алексей — входящий контакт", "alexey_contact", "User initiated contact", False, True, True, True, None, None, None, None, None, None, None),
    ]


def mock_message_fixtures() -> dict[str, list[TelegramMessageData]]:
    return {
        "balitravel_ru": [TelegramMessageData("m-bali-1", "balitravel_ru", "u-101", "maria_travel", "Мария", "Ищу попутчиков на Бали в Убуде на следующей неделе, кто готов присоединиться?", _now(4)), TelegramMessageData("m-bali-2", "balitravel_ru", "u-102", "ivan", "Иван", "Подскажите, где найти экскурсию?", _now(30))],
        "kras_yachts": [TelegramMessageData("m-yacht-1", "kras_yachts", "u-201", "oleg", "Олег", "Ищу прогулку на яхте по Красноярскому морю в эти выходные, есть места?", _now(3))],
        "digital_founders": [TelegramMessageData("m-digital-1", "digital_founders", "u-301", "anna", "Анна", "Нужен сайт для бизнеса, кто может порекомендовать разработчика?", _now(5))],
        "dev_chat": [TelegramMessageData("m-dev-1", "dev_chat", "u-302", "pavel", "Павел", "Нужен Telegram-бот для обработки заявок, есть рекомендации?", _now(8))],
        "kras_events": [TelegramMessageData("m-event-1", "kras_events", "u-401", "event_user", "Ирина", "Что интересного проходит в Красноярске на выходных?", _now(2))],
        "dm_initiated": [TelegramMessageData("dm-1", "dm_initiated", "u-501", "alexey_contact", "Алексей", "Здравствуйте, хочу узнать подробности и цены.", _now(1), initiated_contact=True)],
        "no_ads": [TelegramMessageData("m-noads-1", "no_ads", "u-601", "user", "User", "Классная группа, но реклама запрещена.", _now(2))],
    }


class MockTelegramClient:
    """Deterministic fixture-backed client with failure signals for safety tests."""

    def __init__(self) -> None:
        self.dialogs = mock_dialog_fixtures()
        self.messages = mock_message_fixtures()
        self.sent: dict[str, str] = {}
        self.revoked = False
        self.flood_wait_seconds: int | None = None
        self.spam_warning = False
        self.topics: dict[tuple[str, str], str] = {}

    async def create_forum_topic(self, dialog_external_id: str, title: str) -> str:
        if not any(item.external_id == dialog_external_id and item.dialog_type == "SUPERGROUP" for item in self.dialogs):
            raise ValueError("FORUM_GROUP_REQUIRED")
        topic_id = f"mock-topic-{uuid4().hex[:10]}"
        self.topics[(dialog_external_id, title)] = topic_id
        return topic_id

    async def request_code(self, phone: str) -> None:
        if self.revoked:
            raise RuntimeError("AUTH_REVOKED")

    async def sign_in(self, phone: str, code: str) -> tuple[bytes, dict[str, str]]:
        if code != "12345":
            raise ValueError("INVALID_CODE")
        return b"mock-session-v2", {"id": "mock-user-100", "username": "lead_hunter_demo", "first_name": "Lead", "last_name": "Hunter"}

    async def sign_in_password(self, phone: str, password: str) -> tuple[bytes, dict[str, str]]:
        if password != "123456":
            raise ValueError("INVALID_2FA_PASSWORD")
        return b"mock-session-v2", {"id": "mock-user-100", "username": "lead_hunter_demo", "first_name": "Lead", "last_name": "Hunter"}

    async def health_check(self) -> bool:
        return not self.revoked

    async def get_dialogs(self) -> list[TelegramDialogData]:
        if self.revoked:
            raise RuntimeError("AUTH_REVOKED")
        return list(self.dialogs)

    async def search_communities(self, query: str) -> list[TelegramDialogData]:
        needle = query.casefold()
        return [item for item in self.dialogs if needle in f"{item.title} {item.username or ''} {item.description or ''}".casefold()]

    async def search_global_messages(self, query: str, limit: int = 100) -> list[TelegramMessageData]:
        needle = query.casefold()
        rows = []
        for dialog in self.dialogs:
            if dialog.dialog_type not in {"GROUP", "SUPERGROUP", "CHANNEL"}:
                continue
            for message in self.messages.get(dialog.external_id, []):
                if needle in (message.text or "").casefold():
                    rows.append(TelegramMessageData(**message.__dict__, dialog_title=dialog.title, dialog_username=dialog.username, dialog_type=dialog.dialog_type, dialog_is_public=dialog.is_public))
        return rows[:limit]

    async def read_public_community_messages(self, usernames: list[str], limit: int = 20) -> list[TelegramMessageData]:
        normalized = {item.lstrip("@").casefold() for item in usernames if item}
        rows = []
        for dialog in self.dialogs:
            if (dialog.username or "").casefold() not in normalized:
                continue
            rows.extend(self.messages.get(dialog.external_id, [])[:limit])
        return rows

    async def search_global_communities_batch(self, queries: list[str], limit: int = 100) -> dict[str, list[TelegramDialogData]]:
        return {query: await self.search_communities(query) for query in queries}

    async def join_public_community(self, username: str) -> TelegramDialogData:
        normalized = username.lstrip("@").casefold()
        dialog = next((item for item in self.dialogs if (item.username or "").casefold() == normalized), None)
        if dialog is None:
            raise ValueError("PUBLIC_COMMUNITY_NOT_FOUND")
        return TelegramDialogData(**{**dialog.__dict__, "is_joined": True})

    async def update_dialog_folder(self, title: str, usernames: list[str]) -> int:
        return len({username.lstrip("@").casefold() for username in usernames if username})

    async def enrich_community_metadata(self, usernames: list[str]) -> dict[str, tuple[int, float]]:
        result = {}
        for item in self.dialogs:
            if item.username and item.username.casefold() in {u.lstrip('@').casefold() for u in usernames}:
                result[item.username.casefold()] = (item.member_count or 0, 1.0 if self.messages.get(item.external_id) else 0.0)
        return result

    async def get_messages(self, dialog_external_id: str, limit: int, since: datetime | None = None) -> list[TelegramMessageData]:
        if self.revoked:
            raise RuntimeError("AUTH_REVOKED")
        if dialog_external_id == "no_history":
            raise RuntimeError("HISTORY_UNAVAILABLE")
        messages = self.messages.get(dialog_external_id, [])
        return [item for item in messages if since is None or item.sent_at >= since][:limit]

    async def send_message(self, dialog_external_id: str, content: str, idempotency_key: str, thread_id: str | None = None) -> str:
        if self.revoked:
            raise RuntimeError("AUTH_REVOKED")
        if self.flood_wait_seconds is not None:
            raise MockFloodWaitError(self.flood_wait_seconds)
        dialog = next(item for item in self.dialogs if item.external_id == dialog_external_id)
        if not dialog.can_send_messages:
            raise PermissionError("FORBIDDEN_SEND")
        if self.spam_warning:
            raise RuntimeError("SPAM_WARNING")
        if idempotency_key in self.sent:
            return self.sent[idempotency_key]
        external_id = f"mock-sent-{uuid4().hex[:10]}"
        self.sent[idempotency_key] = external_id
        return external_id
