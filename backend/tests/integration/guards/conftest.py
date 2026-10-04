from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from stylesense.infra.redis import create_redis
from stylesense.platform.config import Settings


@pytest.fixture
async def redis(settings: Settings) -> AsyncIterator[Redis]:
    """A clean Redis per test, so keys from one test never leak into another."""
    client = create_redis(settings)
    await client.flushdb()
    yield client
    await client.aclose()


@pytest.fixture
async def other_redis(settings: Settings) -> AsyncIterator[Redis]:
    """A second, independent connection: stands in for another API/worker instance."""
    client = create_redis(settings)
    yield client
    await client.aclose()
