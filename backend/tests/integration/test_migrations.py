import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from stylesense.infra.database import create_engine
from stylesense.platform.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_config(settings: Settings) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # ConfigParser treats % as interpolation.
    cfg.set_main_option("sqlalchemy.url", str(settings.database_url).replace("%", "%%"))
    return cfg


def _extensions(settings: Settings) -> set[str]:
    async def fetch() -> set[str]:
        engine = create_engine(settings)
        try:
            async with engine.connect() as conn:
                return set((await conn.execute(text("SELECT extname FROM pg_extension"))).scalars())
        finally:
            await engine.dispose()

    return asyncio.run(fetch())


def test_upgrade_and_downgrade_round_trip(alembic_config: Config, settings: Settings) -> None:
    command.upgrade(alembic_config, "head")
    assert {"vector", "citext"} <= _extensions(settings)

    command.downgrade(alembic_config, "base")
    assert not {"vector", "citext"} & _extensions(settings)

    command.upgrade(alembic_config, "head")


def test_single_head(alembic_config: Config) -> None:
    assert len(ScriptDirectory.from_config(alembic_config).get_heads()) == 1
