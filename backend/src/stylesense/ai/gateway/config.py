"""Task routing + prices, loaded from Postgres and hot-reloaded across every instance.

Each call does one cheap Redis GET of a version counter; admins bump it on every change, and
instances reload from the database when it moves. No restarts, no stale config.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select

from stylesense.ai.gateway.models import LlmModel, LlmTaskConfig
from stylesense.ai.gateway.pricing import ModelPrice
from stylesense.ai.gateway.types import ModelRef
from stylesense.infra.database import UnitOfWork

logger = structlog.get_logger(__name__)

VERSION_KEY = "llm:config:version"
_MAX_LOCAL_AGE_S = 300  # safety net if Redis was down when a change was published


@dataclass(frozen=True, slots=True)
class TaskConfig:
    task: str
    targets: tuple[ModelRef, ...]
    temperature: float | None
    max_input_tokens: int
    max_output_tokens: int
    timeout_s: float
    cache_ttl_s: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    tasks: dict[str, TaskConfig] = field(default_factory=dict)
    prices: dict[ModelRef, ModelPrice] = field(default_factory=dict)


class ConfigStore:
    def __init__(self, uow: Callable[[], UnitOfWork], redis: Redis) -> None:
        self._uow = uow
        self._redis = redis
        self._snapshot: ConfigSnapshot | None = None
        self._version: str | None = None
        self._loaded_at = 0.0

    async def snapshot(self) -> ConfigSnapshot:
        version = await self._current_version()
        stale = time.monotonic() - self._loaded_at > _MAX_LOCAL_AGE_S
        if self._snapshot is None or version != self._version or stale:
            self._snapshot = await self._load()
            self._version, self._loaded_at = version, time.monotonic()
        return self._snapshot

    async def invalidate(self) -> None:
        """Publish a change: every instance reloads on its next call."""
        try:
            await self._redis.incr(VERSION_KEY)
        except RedisError as exc:
            logger.warning("llm_config_publish_failed", error=type(exc).__name__)
        self._snapshot = None

    async def _current_version(self) -> str | None:
        try:
            raw = await self._redis.get(VERSION_KEY)
        except RedisError:
            return self._version  # keep serving the last good config
        return str(raw) if raw is not None else None

    async def _load(self) -> ConfigSnapshot:
        async with self._uow() as uow:
            configs = (await uow.session.scalars(select(LlmTaskConfig))).all()
            models = (await uow.session.scalars(select(LlmModel).where(LlmModel.active))).all()
        return ConfigSnapshot(
            tasks={c.task: _task_config(c) for c in configs},
            prices={
                ModelRef(m.provider, m.model): ModelPrice(
                    m.input_usd_per_mtok, m.cached_input_usd_per_mtok, m.output_usd_per_mtok
                )
                for m in models
            },
        )


def _task_config(row: LlmTaskConfig) -> TaskConfig:
    return TaskConfig(
        task=row.task,
        targets=tuple(ModelRef.parse(t) for t in row.targets),
        temperature=row.temperature,
        max_input_tokens=row.max_input_tokens,
        max_output_tokens=row.max_output_tokens,
        timeout_s=row.timeout_s,
        cache_ttl_s=row.cache_ttl_s,
        enabled=row.enabled,
    )
