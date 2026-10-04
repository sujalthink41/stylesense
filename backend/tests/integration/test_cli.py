import pytest
from sqlalchemy import text

from stylesense.cli import seed_catalog
from stylesense.infra.database import create_engine
from stylesense.platform.config import Settings


async def test_seed_loads_and_embeds_the_mock_catalog(settings: Settings, migrated: None) -> None:
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE products, users CASCADE"))
    await engine.dispose()

    first = await seed_catalog(settings, seed=2026)
    second = await seed_catalog(settings, seed=2026)

    assert (first["products_created"], first["embedded"]) == (300, 300)
    assert (second["products_created"], second["embedded"], second["price_changes"]) == (0, 0, 0)


async def test_seed_refuses_to_touch_production(settings: Settings) -> None:
    production = settings.model_copy(update={"env": "production"})

    with pytest.raises(SystemExit, match="production"):
        await seed_catalog(production, seed=1)
