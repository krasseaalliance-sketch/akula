from dataclasses import dataclass
from typing import Any, ClassVar, Protocol
from uuid import uuid4

from .services import normalize_text


@dataclass(frozen=True)
class PublishRequest:
    destination: str
    content: str
    idempotency_key: str


@dataclass(frozen=True)
class PublishResult:
    accepted: bool
    external_message_id: str | None
    simulated: bool
    error: str | None = None


class PlatformAdapter(Protocol):
    async def validate_credentials(self) -> bool: ...
    async def publish_message(self, request: PublishRequest) -> PublishResult: ...


class MockPlatformAdapter:
    def __init__(self) -> None:
        self.published: list[PublishRequest] = []

    async def validate_credentials(self) -> bool:
        return True

    async def publish_message(self, request: PublishRequest) -> PublishResult:
        if any(item.idempotency_key == request.idempotency_key for item in self.published):
            return PublishResult(
                True, f"mock-existing-{request.idempotency_key[:8]}", simulated=True
            )
        self.published.append(request)
        return PublishResult(True, f"mock-{uuid4().hex[:10]}", simulated=True)


class TelegramPlatformAdapter:
    def __init__(self, real_send_enabled: bool = False, live_client: Any | None = None) -> None:
        self.real_send_enabled = real_send_enabled
        self.live_client = live_client

    async def validate_credentials(self) -> bool:
        return self.real_send_enabled

    async def publish_message(self, request: PublishRequest) -> PublishResult:
        if not self.real_send_enabled:
            return PublishResult(False, None, simulated=False, error="TELEGRAM_REAL_SEND_DISABLED")
        if self.live_client is None:
            return PublishResult(False, None, simulated=False, error="TELEGRAM_LIVE_CLIENT_UNAVAILABLE")
        try:
            external_id = await self.live_client.send_message(
                request.destination, request.content, request.idempotency_key
            )
        except PermissionError as exc:
            return PublishResult(False, None, simulated=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - adapter converts provider errors to sanitized status
            return PublishResult(False, None, simulated=False, error=type(exc).__name__)
        return PublishResult(True, external_id, simulated=False)


@dataclass(frozen=True)
class GeneratedMessage:
    content: str
    facts_snapshot: dict
    generation_context: dict
    model_name: str = "mock-template-v1"
    prompt_version: str = "v1"
    similarity_score: float = 0.0


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reasons: list[str]
    normalized_content: str
    similarity_score: float


class MockMessageGenerationProvider:
    def generate(
        self, *, campaign_name: str, objective: str, facts: dict, language: str = "ru"
    ) -> GeneratedMessage:
        content = f"Здравствуйте! Видим задачу «{objective}». Можем предложить короткий разбор и следующий шаг без обязательств."
        return GeneratedMessage(
            content=content,
            facts_snapshot=facts,
            generation_context={
                "provider": "mock",
                "campaign": campaign_name,
                "language": language,
            },
            similarity_score=0.08,
        )


def validate_message(
    content: str, *, language: str = "ru", max_length: int = 4000, similarity_score: float = 0.0
) -> ValidationResult:
    normalized = normalize_text(content)
    reasons: list[str] = []
    if not normalized:
        reasons.append("EMPTY_CONTENT")
    if len(normalized) > max_length:
        reasons.append("CONTENT_TOO_LONG")
    if language not in {"ru", "en"}:
        reasons.append("UNSUPPORTED_LANGUAGE")
    if any(ord(char) < 32 and char not in "\n\t" for char in normalized):
        reasons.append("INVISIBLE_UNICODE")
    blocked = {"обман", "гарантированно заработаете", "scam", "guaranteed profit"}
    if any(word in normalized.lower() for word in blocked):
        reasons.append("PROHIBITED_WORD")
    if similarity_score >= 0.92:
        reasons.append("TOO_SIMILAR")
    return ValidationResult(not reasons, reasons, normalized, similarity_score)


@dataclass(frozen=True)
class MockLead:
    raw_text: str
    author_name: str
    author_username: str
    source_url: str
    scenario: str


class MockLeadSourceAdapter:
    scenarios: ClassVar[dict[str, MockLead]] = {
        "website": MockLead(
            "Нужен сайт для небольшой студии", "Илья", "ilya_site", "mock://website", "website"
        ),
        "telegram_bot": MockLead(
            "Кто может сделать Telegram-бота для команды?",
            "Анна",
            "anna_bot",
            "mock://telegram-bot",
            "telegram_bot",
        ),
        "application": MockLead(
            "Ищем команду для создания мобильного приложения",
            "Олег",
            "oleg_app",
            "mock://application",
            "application",
        ),
        "yacht": MockLead(
            "Ищем яхту на прогулку по Красноярскому морю",
            "Марина",
            "marina_yacht",
            "mock://yacht",
            "yacht",
        ),
        "bali": MockLead(
            "Ищу попутчиков на Бали в октябре", "Даша", "dasha_bali", "mock://bali", "bali"
        ),
        "irrelevant": MockLead(
            "Кто знает рецепт борща?",
            "Никита",
            "nikita_offtopic",
            "mock://irrelevant",
            "irrelevant",
        ),
        "spam": MockLead(
            "Заработок без вложений, переходите по ссылке",
            "Spam",
            "spam_bot",
            "mock://spam",
            "spam",
        ),
        "do_not_contact": MockLead(
            "Не пишите мне больше", "Privacy", "do_not_contact", "mock://dnc", "do_not_contact"
        ),
    }

    def discover(self, scenario: str) -> MockLead:
        return self.scenarios.get(scenario, self.scenarios["irrelevant"])
