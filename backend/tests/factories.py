from typing import Any

from stylesense.platform.config import Settings

# Lazy clients never connect, so unit tests can build real engines/clients offline.
UNREACHABLE_DB = "postgresql+asyncpg://app:app@127.0.0.1:1/stylesense"
UNREACHABLE_REDIS = "redis://127.0.0.1:1/0"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "env": "test",
        "database_url": UNREACHABLE_DB,
        "redis_url": UNREACHABLE_REDIS,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)
