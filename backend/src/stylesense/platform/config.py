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
    account_purge_delay_days: int = Field(default=30, ge=1, le=90)
    min_supported_app_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    latest_app_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, url: PostgresDsn) -> PostgresDsn:
        if url.scheme != "postgresql+asyncpg":
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return url

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
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.env is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required values come from env
