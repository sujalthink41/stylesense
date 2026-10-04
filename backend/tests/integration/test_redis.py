import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from stylesense.infra.health import RedisHealthCheck
from stylesense.infra.redis import create_redis
from tests.factories import UNREACHABLE_REDIS, make_settings


async def test_round_trips_values_as_strings(redis: Redis) -> None:
    await redis.set("probe", "ok", ex=10)

    assert await redis.get("probe") == "ok"


async def test_redis_health_check_passes_when_up(redis: Redis) -> None:
    await RedisHealthCheck(redis).check()


async def test_redis_health_check_raises_when_down() -> None:
    client = create_redis(make_settings(redis_url=UNREACHABLE_REDIS, redis_timeout_s=0.5))
    try:
        # Refused on Linux, timed out on Windows: both mean "down".
        with pytest.raises((RedisConnectionError, RedisTimeoutError)):
            await RedisHealthCheck(client).check()
    finally:
        await client.aclose()
