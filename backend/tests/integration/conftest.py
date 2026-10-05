import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from stylesense.infra.database import UnitOfWork, create_engine, create_session_factory
from stylesense.infra.redis import create_redis
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.integrations.sources.mock import MockSource
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.users.models import User
from stylesense.platform.config import Settings
from tests.factories import make_settings
from tests.fakes.clock import FixedClock

BACKEND_DIR = Path(__file__).resolve().parents[2]
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


@pytest.fixture(scope="session")
def migrated(settings: Settings) -> None:
    """Apply all migrations once per test session."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", str(settings.database_url).replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module")
async def catalog_sessions(
    settings: Settings, migrated: None
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """One seeded, embedded catalog per module: ingesting 300 products per test is wasteful."""
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, products CASCADE"))
    factory = create_session_factory(engine)
    catalog = CatalogService(
        lambda: UnitOfWork(factory), clock=FixedClock(), embedder=HashingEmbedder()
    )
    await catalog.ingest(MockSource())
    while await catalog.embed_pending(batch_size=300):
        pass
    yield factory
    await engine.dispose()


@pytest.fixture
async def user_id(catalog_sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with catalog_sessions() as s, s.begin():
        user = User(email=f"{uuid.uuid4().hex}@example.com")
        s.add(user)
    return user.id
