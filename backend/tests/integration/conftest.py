from collections.abc import AsyncIterator, Iterator

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from stylesense.infra.database import create_engine
from stylesense.infra.redis import create_redis
from stylesense.platform.config import Settings
from tests.factories import make_settings

POSTGRES_IMAGE = "pgvector/pgvector:pg18"
REDIS_IMAGE = "redis:8-alpine"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer(REDIS_IMAGE) as rc:
        yield f"redis://{rc.get_container_host_ip()}:{rc.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def settings(postgres_url: str, redis_url: str) -> Settings:
    return make_settings(database_url=postgres_url, redis_url=redis_url)


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(settings)
    yield eng
    await eng.dispose()


@pytest.fixture
async def redis(settings: Settings) -> AsyncIterator[Redis]:
    client = create_redis(settings)
    yield client
    await client.aclose()
