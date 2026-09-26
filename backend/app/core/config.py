from functools import lru_cache
from typing import Annotated, Literal

from pydantic import PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # Resolved relative to the working directory (backend/); the repo-root .env is shared with
    # docker compose. Real environment variables take precedence over both files.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: PostgresDsn
    db_pool_size: int = 10
    db_max_overflow: int = 10

    redis_url: RedisDsn

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    firebase_project_id: str | None = None
    firebase_client_email: str | None = None
    firebase_private_key: SecretStr | None = None

    # Where the browser is sent after OAuth callbacks.
    frontend_url: str = "http://localhost:5173"

    # Instagram API with Instagram Login. App ID/secret are the *Instagram* app credentials
    # shown under "API setup with Instagram login" in the Meta App Dashboard. Endpoints,
    # version, scopes and webhook fields are configurable because Meta changes them.
    meta_app_id: str | None = None
    meta_app_secret: SecretStr | None = None
    meta_redirect_uri: str | None = None
    meta_webhook_verify_token: SecretStr | None = None
    meta_api_version: str = "v23.0"
    meta_authorize_url: str = "https://www.instagram.com/oauth/authorize"
    meta_token_url: str = "https://api.instagram.com/oauth/access_token"  # noqa: S105 (a URL)
    meta_graph_url: str = "https://graph.instagram.com"
    meta_scopes: Annotated[list[str], NoDecode] = [
        "instagram_business_basic",
        "instagram_business_manage_messages",
        "instagram_business_manage_comments",
    ]
    meta_webhook_fields: Annotated[list[str], NoDecode] = ["comments", "messages"]

    # Comma-separated Fernet keys; the first encrypts, all decrypt (for rotation).
    token_encryption_keys: SecretStr | None = None

    # AI. The API key stays on the server. "mock" is deterministic and makes no network calls.
    # "gemini" without a key leaves AI endpoints unavailable; the rest of the app still starts.
    ai_provider: Literal["mock", "gemini"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    ai_temperature: float = 0.4
    ai_max_output_tokens: int = 256
    ai_timeout_seconds: float = 20
    ai_max_context_messages: int = 20
    ai_memory_top_k: int = 5
    ai_requests_per_minute: int = 30
    ai_max_retries: int = 1

    @field_validator(
        "firebase_project_id",
        "firebase_client_email",
        "firebase_private_key",
        "meta_app_id",
        "meta_app_secret",
        "meta_redirect_uri",
        "meta_webhook_verify_token",
        "token_encryption_keys",
        "gemini_api_key",
        mode="before",
    )
    @classmethod
    def blank_as_unset(cls, value: object) -> object:
        # `KEY=` in .env must mean "not configured": an empty webhook secret would let anyone
        # compute valid signatures.
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("database_url", mode="before")
    @classmethod
    def use_asyncpg_driver(cls, value: str) -> str:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("cors_origins", "meta_scopes", "meta_webhook_fields", mode="before")
    @classmethod
    def split_comma_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def instagram_oauth_configured(self) -> bool:
        return bool(
            self.meta_app_id
            and self.meta_app_secret
            and self.meta_redirect_uri
            and self.token_encryption_keys
        )

    @property
    def ai_configured(self) -> bool:
        if self.ai_provider == "mock":
            return True
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
