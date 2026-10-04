from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator, model_validator
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

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, url: PostgresDsn) -> PostgresDsn:
        if url.scheme != "postgresql+asyncpg":
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return url

    @model_validator(mode="after")
    def _guard_production(self) -> Self:
        if self.env is Environment.PRODUCTION and self.debug:
            raise ValueError("debug must be disabled in production")
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.env is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required values come from env
