from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class PostgresHealthCheck:
    name = "postgres"

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))


class RedisHealthCheck:
    name = "redis"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def check(self) -> None:
        await self._redis.ping()
