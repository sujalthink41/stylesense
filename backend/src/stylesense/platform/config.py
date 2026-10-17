from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Typed app config from `APP_*` env vars; invalid config fails at startup."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    env: Environment = Environment.LOCAL
    name: str = "stylesense"
    version: str = "0.1.0"
    debug: bool = False
    log_level: LogLevel = "INFO"

    database_url: PostgresDsn
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout_s: float = Field(default=5.0, gt=0, le=60)
    db_statement_timeout_ms: int = Field(default=5_000, ge=100, le=600_000)

    redis_url: RedisDsn
    redis_timeout_s: float = Field(default=2.0, gt=0, le=30)

    readiness_timeout_s: float = Field(default=2.0, gt=0, le=10)
    cors_origins: list[str] = Field(default_factory=list)
    # Public site (share and poll pages, App Links host); links we hand out point here.
    public_web_url: str = Field(default="http://localhost:3000", pattern=r"^https?://")

    metrics_enabled: bool = True
    otel_enabled: bool = False
    otel_endpoint: AnyHttpUrl | None = None  # OTLP/HTTP collector base URL
    otel_sample_ratio: float = Field(default=1.0, ge=0, le=1)
    sentry_dsn: str | None = None  # GlitchTip speaks the Sentry protocol

    max_in_flight: int = Field(default=256, ge=1, le=10_000)  # per instance; excess is shed
    max_queued: int = Field(default=64, ge=0, le=10_000)
    rate_limit_fail_open: bool = True
    idempotency_lock_ttl_s: float = Field(default=60, gt=0, le=600)
    idempotency_ttl_s: float = Field(default=86_400, gt=0, le=7 * 86_400)

    outbox_batch_size: int = Field(default=50, ge=1, le=1_000)
    outbox_max_attempts: int = Field(default=10, ge=1, le=100)
    outbox_poll_interval_s: float = Field(default=1.0, gt=0, le=60)
    worker_heartbeat_file: str = "/tmp/stylesense-worker.heartbeat"  # noqa: S108  # container-local
    worker_metrics_port: int = Field(default=9100, ge=1, le=65_535)

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_previous_secrets: list[SecretStr] = Field(
        default_factory=list
    )  # still verify during rotation
    jwt_issuer: str = "stylesense"
    access_token_ttl_s: int = Field(default=900, ge=60, le=3_600)
    refresh_token_ttl_s: int = Field(default=30 * 86_400, ge=3_600, le=90 * 86_400)
    refresh_reuse_grace_s: int = Field(default=30, ge=0, le=120)
    google_client_ids: list[str] = Field(default_factory=list)  # Android, iOS and web OAuth clients
    admin_emails: list[str] = Field(default_factory=list)
    # Local only: lets the app sign in by email without Google (Expo Go has no native
    # Google sign-in). Refused in production.
    dev_sign_in_enabled: bool = False
    account_purge_delay_days: int = Field(default=30, ge=1, le=90)
    min_supported_app_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    latest_app_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")

    # AI gateway. A provider is enabled only when its key is set.
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None  # OpenAI-compatible; routes say groq:<model>
    # Card reasons from the model cost tokens on every deck; rule-based reasons are free.
    stylist_ai_reasons: bool = False
    llm_daily_budget_usd: Decimal = Field(default=Decimal("2.00"), ge=0, le=10_000)
    llm_budget_alert_ratio: float = Field(default=0.8, gt=0, le=1)
    llm_max_attempts: int = Field(default=3, ge=1, le=5)
    llm_breaker_threshold: int = Field(default=5, ge=1, le=100)
    llm_breaker_window_s: float = Field(default=30, gt=0, le=600)
    llm_breaker_cooldown_s: float = Field(default=60, gt=0, le=3_600)
    llm_max_concurrency: int = Field(default=16, ge=1, le=1_000)
    llm_max_queued: int = Field(default=32, ge=0, le=10_000)
    # "hashing" (offline) or "provider:model"; changing it re-embeds the whole catalog.
    embedding_model: str = Field(default="hashing", pattern=r"^(hashing|[a-z0-9_-]+:\S+)$")

    # Media (Cloudinary). Photo search and try-on are enabled only when all three are set.
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: SecretStr | None = None
    cloudinary_upload_preset: str = "stylesense_user_uploads"
    media_ttl_hours: int = Field(default=24, ge=1, le=168)  # user photos are deleted after this
    upload_daily_limit: int = Field(default=30, ge=1, le=1_000)  # per user
    photo_search_daily_limit: int = Field(default=10, ge=1, le=1_000)  # per user
    # Live product search (DuckDuckGo → Amazon.in, Flipkart, Myntra) when the catalog has too
    # little for a request. Interim until the stores' affiliate APIs; prices are never estimated.
    web_search_enabled: bool = False
    # Shown on the privacy, terms and account-deletion pages (Play Store requires them).
    support_email: str = Field(default="support@stylesense.app", max_length=120)
    # Virtual try-on. "fake" returns the garment image (local testing only); "none" = off;
    # "openai" = image editing with the OpenAI key (model and per-image cost from settings).
    tryon_provider: Literal["none", "fake", "openai"] = "none"
    tryon_openai_model: str | None = None
    tryon_openai_quality: Literal["low", "medium", "high"] = "medium"
    # Only some image models accept input_fidelity; leave unset for those that don't.
    tryon_openai_input_fidelity: Literal["low", "high"] | None = None
    tryon_cost_micro_usd: int = Field(default=0, ge=0)  # flat fallback per image
    # USD per 1M tokens from the provider's price list; set all three for exact per-job cost.
    tryon_price_image_input: float | None = Field(default=None, ge=0)
    tryon_price_text_input: float | None = Field(default=None, ge=0)
    tryon_price_output: float | None = Field(default=None, ge=0)
    tryon_daily_limit: int = Field(default=3, ge=0, le=100)  # per user
    tryon_global_daily_limit: int = Field(default=200, ge=0, le=100_000)  # paid: hard cap

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, url: PostgresDsn) -> PostgresDsn:
        if url.scheme != "postgresql+asyncpg":
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return url

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "groq_api_key",
        "cloudinary_cloud_name",
        "cloudinary_api_key",
        "cloudinary_api_secret",
        "tryon_openai_model",
        "tryon_openai_input_fidelity",
        mode="before",
    )
    @classmethod
    def _blank_key_is_unset(cls, value: object) -> object:
        # Compose passes unset variables as "", which must mean "no provider", not a blank key.
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("admin_emails")
    @classmethod
    def _normalize_emails(cls, emails: list[str]) -> list[str]:
        return [e.strip().lower() for e in emails]

    @model_validator(mode="after")
    def _guard_production(self) -> Self:
        if self.env is Environment.PRODUCTION and self.debug:
            raise ValueError("debug must be disabled in production")
        if self.env is Environment.PRODUCTION and not self.google_client_ids:
            raise ValueError("google_client_ids is required in production")
        if self.env is Environment.PRODUCTION and self.dev_sign_in_enabled:
            raise ValueError("developer sign-in must never be enabled in production")
        if self.env is Environment.PRODUCTION and self.tryon_provider == "fake":
            raise ValueError("the fake try-on provider must never serve real users")
        if self.tryon_provider == "openai" and not (
            self.openai_api_key and self.tryon_openai_model
        ):
            raise ValueError("tryon_provider=openai needs openai_api_key and tryon_openai_model")
        return self

    @property
    def media_configured(self) -> bool:
        return bool(
            self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret
        )

    @property
    def docs_enabled(self) -> bool:
        return self.env is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required values come from env
