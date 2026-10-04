from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.infra.database import create_engine, create_session_factory
from stylesense.infra.health import PostgresHealthCheck, RedisHealthCheck
from stylesense.infra.redis import create_redis
from stylesense.platform.clock import Clock, SystemClock
from stylesense.platform.config import Settings
from stylesense.platform.health import HealthCheck


@dataclass(slots=True)
class Container:
    """App-wide singletons. The only place concrete implementations are chosen."""

    settings: Settings
    clock: Clock
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    health_checks: tuple[HealthCheck, ...]
    closed: bool = field(default=False, init=False)

    async def aclose(self) -> None:
        if self.closed:
            return
        try:
            await self.redis.aclose()
        finally:
            await self.engine.dispose()
            self.closed = True


def build_container(settings: Settings) -> Container:
    # Clients are lazy: nothing connects until first use.
    engine = create_engine(settings)
    redis = create_redis(settings)
    return Container(
        settings=settings,
        clock=SystemClock(),
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=redis,
        health_checks=(PostgresHealthCheck(engine), RedisHealthCheck(redis)),
    )
