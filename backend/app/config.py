from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_mode: str = "DRY_RUN"
    database_url: str = "postgresql+psycopg://lead_hunter:lead_hunter@localhost:5432/lead_hunter"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-a-secret-store"
    jwt_expire_minutes: int = 30
    telegram_real_send_enabled: bool = False
    telegram_operator_notifications_enabled: bool = False
    telegram_support_group_id: str | None = None
    telegram_support_profile_id: str | None = None
    telegram_real_connect_enabled: bool = False
    telegram_discovery_enabled: bool = False
    telegram_history_sync_enabled: bool = False
    telegram_api_id: str | None = None
    telegram_api_hash: str | None = None
    telegram_session_encryption_key: str | None = None
    telegram_health_check_interval_minutes: int = 15
    telegram_dialog_sync_interval_minutes: int = 60
    telegram_message_sync_interval_minutes: int = 10
    telegram_incoming_sync_interval_minutes: int = 5
    telegram_asmet_chat_id: str | None = None
    telegram_asmet_profile_id: str | None = None
    asmet_service_interval_seconds: int = 60
    telegram_session_root: str = ".telegram_sessions"
    telegram_live_read_enabled: bool = False
    telegram_proxy_host: str | None = None
    telegram_proxy_port: int | None = None
    max_api_base_url: str = "https://platform-api2.max.ru"
    max_asmet_access_token: str | None = None
    max_asmet_organization_id: str | None = None
    max_asmet_chat_id: str | None = None
    max_webhook_url: str | None = None
    max_webhook_secret: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.6-terra"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_enabled: bool = False
    ai_temperature: float = 0.2
    ai_max_tokens: int = 1200
    human_writing_llm_enabled: bool = True
    human_writing_min_naturalness: float = 90
    human_writing_similarity_threshold: float = 0.82
    publication_mode: str = "DRY_RUN"
    hunter_outbound_disabled: bool = True
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_safe_configuration(self) -> bool:
        return self.app_env != "production" or (
            self.jwt_secret != "change-me-in-a-secret-store"
            and not self.telegram_real_send_enabled
        )

    @property
    def is_hunter_safe_configuration(self) -> bool:
        """Hunter must never inherit the legacy publication capability."""
        return self.hunter_outbound_disabled and not self.telegram_real_send_enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()
